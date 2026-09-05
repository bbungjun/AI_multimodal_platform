"""Read-only operational snapshot. No lifecycle writes or profile data in output."""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.credit_policy import cycle_bounds, plan_policy
from app.master_admin import REASONS
from app.personal_usage import METER_UNITS

MODELS = frozenset({"imagen-4.0-fast-generate-001", "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001", "veo-3.0-fast-generate-001", "veo-3.0-generate-001"})
ERRORS = frozenset({"provider_failed", "provider_timeout", "provider_rate_limited",
    "generation_failed", "delivery_failed", "user_suspended", "ownership_mismatch"})
PLANS = frozenset({"free", "pro", "max"})
_COHORT = """SELECT u.id,u.data_origin,u.status,
 COALESCE(a.plan,CASE WHEN u.role='master' THEN 'max' ELSE 'free' END) AS plan
 FROM users u LEFT JOIN credit_accounts a ON a.user_id=u.id
 WHERE (:origin='all' OR u.data_origin::text=:origin)"""


class MasterReadError(ValueError):
    def __init__(self, code="master_unavailable"):
        self.code = code
        super().__init__(code)


def integer(value):
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        value = int(value)
    if type(value) is not int or value < 0:
        raise MasterReadError()
    return value


def amount(value):
    return str(integer(value))


def safe_values(value):
    if not isinstance(value, dict):
        raise MasterReadError()
    result = {}
    for key, item in value.items():
        allowed = {"role": {"user", "master"}, "status": {"active", "suspended"},
                   "plan": PLANS | {None}, "pending_plan": PLANS | {None}}
        if key in allowed:
            if item is not None and type(item) is not str or item not in allowed[key]:
                raise MasterReadError()
            result[key] = item
        elif key in {"bonus_microcredits", "revoked_sessions", "cancelled_jobs"}:
            result[key] = amount(item) if key == "bonus_microcredits" else integer(item)
        else:
            raise MasterReadError()
    return result


def project_user(row, grants, held, charged, now):
    bounds = cycle_bounds(signed_up_at=row["signed_up_at"], now=now)
    plan = row["account_plan"] or ("max" if row["role"] == "master" else "free")
    pending = row["pending_plan"]
    materialized = row["cycle_index"] == bounds.index
    if row["account_plan"] is not None and (row["cycle_index"] is None
            or row["cycle_index"] > bounds.index or row["cycle_anchor_at"] != row["signed_up_at"]):
        raise MasterReadError()
    if not materialized and pending is not None:
        plan, pending = pending, None
    if plan not in PLANS or pending not in PLANS | {None} or (row["role"] == "master" and plan != "max"):
        raise MasterReadError()
    available = 0 if materialized else plan_policy(plan).allowance_microcredits
    grant_held, base_count = 0, 0
    for grant in grants:
        total, reserved, used, expired = (integer(grant[k]) for k in
            ("granted_microcredits", "reserved_microcredits", "consumed_microcredits", "expired_microcredits"))
        if reserved + used + expired > total:
            raise MasterReadError()
        grant_held += reserved
        if grant["kind"] == "base" and grant["cycle_id"] == row["cycle_id"] and materialized:
            base_count += 1
        if grant["expires_at"] is None or grant["expires_at"] > now:
            if grant["kind"] == "bonus" or (materialized and grant["cycle_id"] == row["cycle_id"]):
                available += total - reserved - used - expired
    if grant_held != integer(held) or materialized and base_count != 1:
        raise MasterReadError()
    return dict(id=row["id"], role=row["role"], status=row["status"], origin=row["data_origin"],
        signed_up_at=row["signed_up_at"], plan=plan, pending_plan=pending,
        cycle_starts_at=bounds.starts_at, renews_at=bounds.ends_at,
        available_microcredits=amount(available), held_microcredits=amount(held),
        charged_microcredits=amount(charged), balance_materialized=materialized)


async def rows(session, sql, params):
    return list((await session.execute(text(sql), params)).mappings())


async def _users(session, p):
    found = await rows(session, """SELECT u.id,u.role::text,u.status::text,u.data_origin::text,
      u.signed_up_at,a.plan AS account_plan,a.pending_plan,a.cycle_anchor_at,
      c.id AS cycle_id,c.cycle_index FROM users u
      LEFT JOIN credit_accounts a ON a.user_id=u.id
      LEFT JOIN LATERAL (SELECT id,cycle_index FROM credit_cycles WHERE user_id=u.id
        ORDER BY cycle_index DESC LIMIT 1) c ON true
      WHERE (:origin='all' OR u.data_origin::text=:origin)
        AND (:status='all' OR u.status::text=:status)
        AND (CAST(:after AS uuid) IS NULL OR u.id>CAST(:after AS uuid))
      ORDER BY u.id LIMIT :fetch""", p)
    page = found[:p["limit"]]
    ids = [r["id"] for r in page]
    grants = await rows(session, """SELECT user_id,cycle_id,kind,expires_at,granted_microcredits,
      reserved_microcredits,consumed_microcredits,expired_microcredits FROM credit_grants
      WHERE user_id=ANY(CAST(:ids AS uuid[]))""", {"ids": ids})
    held = await rows(session, """SELECT user_id,sum(reserved_microcredits) AS total FROM credit_reservations
      WHERE user_id=ANY(CAST(:ids AS uuid[])) AND status='held' GROUP BY user_id""", {"ids": ids})
    charged = await rows(session, """SELECT r.user_id,sum(r.charged_microcredits) AS total
      FROM credit_usage_records r JOIN users u ON u.id=r.user_id
      WHERE r.user_id=ANY(CAST(:ids AS uuid[])) AND r.recorded_at<=:now
      AND r.recorded_at>=u.signed_up_at +
        floor(extract(epoch FROM (CAST(:now AS timestamptz)-u.signed_up_at))/2592000)*interval '30 days'
      GROUP BY r.user_id""", {"ids": ids, "now": p["now"]})
    by_user = {uid: [] for uid in ids}
    for grant in grants:
        by_user[grant["user_id"]].append(grant)
    held_map = {r["user_id"]: r["total"] for r in held}
    charged_map = {r["user_id"]: r["total"] for r in charged}
    return dict(items=[project_user(r, by_user[r["id"]], held_map.get(r["id"], 0),
        charged_map.get(r["id"], 0), p["now"]) for r in page],
        next_cursor=page[-1]["id"] if len(found)>p["limit"] else None)


async def _audit(session, p):
    when = None
    if p["after"] is not None:
        cursor = await rows(session, "SELECT created_at FROM master_audit WHERE request_id=:after", p)
        if not cursor:
            raise MasterReadError("master_input_invalid")
        when = cursor[0]["created_at"]
    found = await rows(session, """SELECT request_id,actor_id,target_id,action,source,reason_code,
      before_value,after_value,created_at FROM master_audit
      WHERE (CAST(:when AS timestamptz) IS NULL OR
        (created_at,request_id)<(CAST(:when AS timestamptz),CAST(:after AS uuid)))
      ORDER BY created_at DESC,request_id DESC LIMIT :fetch""", dict(p, when=when))
    result = []
    for row in found[:p["limit"]]:
        if (row["action"] not in {"promote", "plan_change", "bonus_grant", "suspend", "reactivate"}
                or row["source"] not in {"operator_cli", "browser"} or row["reason_code"] not in REASONS):
            raise MasterReadError()
        result.append({k: v for k, v in row.items() if k not in {"before_value", "after_value"}}
            | {"before": safe_values(row["before_value"]), "after": safe_values(row["after_value"])})
    return dict(items=result, next_cursor=result[-1]["request_id"] if len(found)>p["limit"] else None)


async def _overview(session, p):
    prefix = "WITH cohort AS (" + _COHORT + ") "
    counts = await rows(session, prefix + """SELECT data_origin::text AS origin,status::text,plan,count(*) AS count
      FROM cohort GROUP BY data_origin,status,plan ORDER BY data_origin,status,plan""", p)
    credits = await rows(session, prefix + """, charge AS (
      SELECT reservation_id,sum(charged_microcredits) AS charged FROM credit_usage_records GROUP BY reservation_id)
      SELECT c.plan,
      COALESCE(sum(r.reserved_microcredits) FILTER(WHERE r.created_at>=:start AND r.created_at<=:now),0) AS reserved,
      COALESCE(sum(COALESCE(x.charged,0)) FILTER(WHERE r.terminal_at>=:start AND r.terminal_at<=:now),0) AS charged,
      COALESCE(sum(r.reserved_microcredits-COALESCE(x.charged,0))
        FILTER(WHERE r.terminal_at>=:start AND r.terminal_at<=:now),0) AS released,
      COALESCE(sum(r.reserved_microcredits) FILTER(WHERE r.status='held'),0) AS held
      FROM cohort c LEFT JOIN credit_reservations r ON r.user_id=c.id
      LEFT JOIN charge x ON x.reservation_id=r.id GROUP BY c.plan ORDER BY c.plan""", p)
    usage = await rows(session, prefix + """SELECT r.meter,sum(r.actual_units) AS observed,
      sum(r.charged_microcredits) AS charged FROM credit_usage_records r JOIN cohort c ON c.id=r.user_id
      WHERE r.recorded_at>=:start AND r.recorded_at<=:now GROUP BY r.meter""", p)
    meters = dict((r["meter"], r) for r in usage)
    if set(meters) - {m for m, _ in METER_UNITS}:
        raise MasterReadError()
    daily = await rows(session, prefix + """SELECT (r.recorded_at AT TIME ZONE 'UTC')::date AS day,
      sum(r.charged_microcredits) AS charged FROM credit_usage_records r JOIN cohort c ON c.id=r.user_id
      WHERE r.recorded_at>=:start AND r.recorded_at<=:now GROUP BY day ORDER BY day""", p)
    jobs = await rows(session, prefix + """SELECT j.state::text,
      CASE WHEN j.model=ANY(CAST(:models AS text[])) THEN j.model ELSE 'unknown' END AS model,
      count(*) AS count,
      percentile_cont(0.95) WITHIN GROUP(ORDER BY greatest(0,extract(epoch FROM (j.updated_at-j.created_at))))
        FILTER(WHERE j.state IN ('completed','failed')) AS p95_seconds
      FROM jobs j JOIN cohort c ON c.id=j.owner_user_id
      WHERE j.created_at>=:start AND j.created_at<=:now GROUP BY j.state,2 ORDER BY j.state,2""", p)
    failed = await rows(session, prefix + """SELECT j.id,j.created_at,
      CASE WHEN j.model=ANY(CAST(:models AS text[])) THEN j.model ELSE 'unknown' END AS model,
      CASE WHEN j.error->>'code'=ANY(CAST(:errors AS text[])) THEN j.error->>'code' ELSE 'other' END AS code
      FROM jobs j JOIN cohort c ON c.id=j.owner_user_id
      WHERE j.state='failed' AND j.created_at>=:start AND j.created_at<=:now
      ORDER BY j.created_at DESC,j.id DESC LIMIT 20""", p)
    errors = await rows(session, prefix + """SELECT
      CASE WHEN j.error->>'code'=ANY(CAST(:errors AS text[])) THEN j.error->>'code' ELSE 'other' END AS code,
      count(*) AS count FROM jobs j JOIN cohort c ON c.id=j.owner_user_id
      WHERE j.state='failed' AND j.created_at>=:start AND j.created_at<=:now GROUP BY 1 ORDER BY 1""", p)
    terminal = sum(r["count"] for r in jobs if r["state"] in {"completed", "failed"})
    successes = sum(r["count"] for r in jobs if r["state"] == "completed")
    return dict(window=dict(starts_at=p["start"], ends_at=p["now"], days=p["days"]),
        plan_attribution="current_persisted_account_plan", duration_definition="queue_inclusive_updated_minus_created",
        counts=[dict(r) for r in counts], credits=[dict(plan=r["plan"], **{
            k+"_microcredits": amount(r[k]) for k in ("reserved", "charged", "released", "held")}) for r in credits],
        usage=[dict(meter=m, unit=u, observed_units=amount(meters.get(m, {}).get("observed", 0)),
            charged_microcredits=amount(meters.get(m, {}).get("charged", 0))) for m, u in METER_UNITS],
        daily=[dict(day=r["day"], charged_microcredits=amount(r["charged"])) for r in daily],
        jobs=[dict(r) for r in jobs], terminal_count=terminal,
        success_rate=successes/terminal if terminal else None,
        recent_failures=[dict(r) for r in failed], errors=[dict(r) for r in errors])


async def read_master(session, *, actor_id, view, now, days=30, origin="all", status="all", limit=25, after=None):
    if (not isinstance(actor_id, UUID) or view not in {"users", "audit", "overview"}
            or not isinstance(now, datetime) or now.utcoffset() is None
            or type(days) is not int or not 1<=days<=90 or type(limit) is not int or not 1<=limit<=50
            or origin not in {"all", "oauth", "synthetic"} or status not in {"all", "active", "suspended"}
            or after is not None and not isinstance(after, UUID)):
        raise MasterReadError("master_input_invalid")
    if session.in_transaction():
        raise MasterReadError("master_transaction_required")
    try:
        async with session.begin():
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout='5s'"))
            actor = await rows(session, """SELECT id FROM users WHERE id=:actor
              AND role='master' AND status='active' AND data_origin='oauth'""", {"actor": actor_id})
            if not actor:
                raise MasterReadError("master_required")
            p = dict(now=now, start=now-timedelta(days=days), days=days, origin=origin,
                     status=status, limit=limit, fetch=limit+1, after=after,
                     models=sorted(MODELS), errors=sorted(ERRORS))
            return await {"users": _users, "audit": _audit, "overview": _overview}[view](session, p)
    except DBAPIError as error:
        raise MasterReadError("master_busy" if getattr(error.orig, "sqlstate", None)
            in {"57014", "55P03", "40001"} else "master_unavailable") from None
    except (ValueError, TypeError, OverflowError) as error:
        if isinstance(error, MasterReadError):
            raise
        raise MasterReadError() from None
