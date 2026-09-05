"""Transactional audited account administration. Caller owns commit/rollback."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.credit_lifecycle import CreditLifecycleError, change_plan, ensure_cycle, grant_bonus
from app.credit_models import CreditAccount
from app.identity_models import User, UserOrigin, UserRole, UserStatus
from app.master_models import MasterAudit


REASONS = frozenset({"operator_bootstrap", "entitlement_change", "support_adjustment",
                     "service_recovery", "account_policy", "account_reactivated"})
_ADMIN_LOCK = 74100301


class MasterError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MasterCommand:
    target_id: UUID
    request_id: UUID
    action: str
    reason_code: str
    target_plan: str | None = None
    amount_microcredits: int | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class MasterReceipt:
    request_id: UUID
    action: str
    before: dict
    after: dict
    created_at: datetime
    replayed: bool


def validate_command(command, *, source, now):
    if (not isinstance(command, MasterCommand) or not isinstance(command.target_id, UUID)
            or not isinstance(command.request_id, UUID) or type(command.reason_code) is not str
            or command.reason_code not in REASONS or type(command.action) is not str
            or not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
            or type(source) is not str or source not in {"browser", "operator_cli"}):
        raise MasterError("master_input_invalid")
    if command.action not in {"promote", "plan_change", "bonus_grant"}:
        raise MasterError("master_input_invalid")
    if (source == "operator_cli") != (command.action == "promote"):
        raise MasterError("master_input_invalid")
    if command.action == "plan_change":
        if (type(command.target_plan) is not str or command.target_plan not in {"free", "pro", "max"}
                or command.amount_microcredits is not None or command.expires_at is not None):
            raise MasterError("master_input_invalid")
    elif command.action == "bonus_grant":
        if (command.target_plan is not None or type(command.amount_microcredits) is not int
                or not 0 < command.amount_microcredits <= 9_000_000_000_000_000):
            raise MasterError("master_input_invalid")
        if command.expires_at is not None and (
                not isinstance(command.expires_at, datetime) or command.expires_at.tzinfo is None
                or command.expires_at.utcoffset() is None):
            raise MasterError("master_input_invalid")
    elif any(value is not None for value in (command.target_plan, command.amount_microcredits, command.expires_at)):
        raise MasterError("master_input_invalid")


def _fingerprint(command, actor_id, source):
    value = dict(actor_id=str(actor_id), target_id=str(command.target_id), source=source,
                 action=command.action, reason=command.reason_code, plan=command.target_plan,
                 amount=command.amount_microcredits,
                 expiry=command.expires_at.astimezone(timezone.utc).isoformat() if command.expires_at else None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _receipt(row, replayed):
    return MasterReceipt(row.request_id, row.action, dict(row.before_value), dict(row.after_value),
                         row.created_at, replayed)


def _snapshot(user, account):
    return dict(role=str(user.role), status=str(user.status), plan=account.plan,
                pending_plan=account.pending_plan)


async def administer(session, *, actor_id: UUID, command: MasterCommand, now: datetime,
                     source: str = "browser") -> MasterReceipt:
    """Recheck authority and persist exactly one mutation+Audit under a savepoint.

    `operator_cli` is a trusted in-process seam, never an HTTP request field.
    The privileged CLI must validate its execution environment before calling it.
    """
    validate_command(command, source=source, now=now)
    if not isinstance(actor_id, UUID) or (source == "operator_cli" and actor_id != command.target_id):
        raise MasterError("master_input_invalid")
    if not session.in_transaction():
        raise MasterError("master_transaction_required")
    fingerprint = _fingerprint(command, actor_id, source)
    try:
        async with session.begin_nested():
            await session.execute(text("SELECT set_config('lock_timeout', '5s', true)"))
            await session.execute(text("SELECT set_config('statement_timeout', '10s', true)"))
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMIN_LOCK})
            users = list((await session.scalars(select(User).where(
                User.id.in_({actor_id, command.target_id})).order_by(User.id).with_for_update()
                .execution_options(populate_existing=True))).all())
            indexed = {user.id: user for user in users}
            actor, target = indexed.get(actor_id), indexed.get(command.target_id)
            if source == "browser" and (actor is None or actor.role != UserRole.MASTER
                    or actor.status != UserStatus.ACTIVE or actor.data_origin != UserOrigin.OAUTH):
                raise MasterError("master_required")
            if target is None:
                raise MasterError("master_target_missing")
            previous = await session.get(MasterAudit, command.request_id)
            if previous is not None:
                if previous.payload_fingerprint != fingerprint:
                    raise MasterError("master_conflict")
                return _receipt(previous, True)
            if target.status != UserStatus.ACTIVE or now < target.signed_up_at:
                raise MasterError("master_conflict")
            if command.action == "promote" and target.data_origin != UserOrigin.OAUTH:
                raise MasterError("master_conflict")
            await ensure_cycle(session, user_id=target.id, now=now)
            account = await session.get(CreditAccount, target.id)
            before = _snapshot(target, account)
            key = "master_" + command.request_id.hex
            if command.action in {"promote", "plan_change"}:
                # Upgrade before changing role: lifecycle rejects incoherent Master/Free state.
                await change_plan(session, user_id=target.id,
                    target_plan="max" if command.action == "promote" else command.target_plan,
                    operation_key=key, now=now)
                if command.action == "promote":
                    target.role = UserRole.MASTER
                    target.updated_at = now
            else:
                await grant_bonus(session, user_id=target.id, amount_microcredits=command.amount_microcredits,
                    expires_at=command.expires_at, reason_code=command.reason_code,
                    operation_key=key, now=now)
            after = _snapshot(target, account)
            if command.action == "bonus_grant":
                before["bonus_microcredits"] = 0
                after["bonus_microcredits"] = command.amount_microcredits
            row = MasterAudit(request_id=command.request_id, actor_id=actor_id, target_id=target.id,
                action=command.action, source=source, reason_code=command.reason_code,
                payload_fingerprint=fingerprint, before_value=before, after_value=after, created_at=now)
            session.add(row)
            await session.flush()
            return _receipt(row, False)
    except CreditLifecycleError as error:
        code = {"credit_busy": "master_busy", "credit_input_invalid": "master_input_invalid",
                "credit_plan_refused": "master_conflict", "credit_idempotency_conflict": "master_conflict"}.get(
                    error.code, "master_unavailable")
        raise MasterError(code) from None
    except DBAPIError as error:
        state = getattr(error.orig, "sqlstate", None)
        raise MasterError("master_busy" if state in {"55P03", "40P01", "40001", "57014"}
                          else "master_unavailable") from None
