/** Console boundary: explicit fields, integer Credit and replayable commands. */
const fail = (): never => { throw new Error("master_response_invalid"); };
const object = (v: unknown): Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : fail();
const list = (v: unknown): unknown[] => Array.isArray(v) && v.length <= 1000 ? v : fail();
const text = (v: unknown): string => typeof v === "string" && v.length <= 128 ? v : fail();
const choice = <T extends string>(v: unknown, options: readonly T[]): T => options.includes(v as T) ? v as T : fail();
const count = (v: unknown): number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 ? v : fail();
const real = (v: unknown): number => typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : fail();
const bool = (v: unknown): boolean => typeof v === "boolean" ? v : fail();
const decimal = (v: unknown): string => /^(0|[1-9]\d*)$/.test(text(v)) ? v as string : fail();
const uuid = (v: unknown): string => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(text(v)) ? v as string : fail();
const instant = (v: unknown): string => /^\d{4}-\d\d-\d\dT/.test(text(v)) && Number.isFinite(Date.parse(v as string)) ? v as string : fail();
export const PLANS = ["free", "pro", "max"] as const;
export const ACTIONS = ["plan_change", "bonus_grant", "suspend", "reactivate"] as const;
export const REASONS = ["entitlement_change", "support_adjustment", "service_recovery", "account_policy", "account_reactivated", "operator_bootstrap"] as const;
const STATES = ["pending", "enhancing", "queued", "generating", "polling", "downloading", "completed", "failed", "cancelled"] as const;
const MODELS = ["imagen-4.0-fast-generate-001", "imagen-4.0-generate-001", "imagen-4.0-ultra-generate-001", "veo-3.0-fast-generate-001", "veo-3.0-generate-001", "unknown"] as const;
const ERRORS = ["provider_failed", "provider_timeout", "provider_rate_limited", "generation_failed", "delivery_failed", "user_suspended", "ownership_mismatch", "other"] as const;
const METERS = ["gemini_input_token", "gemini_output_token", "imagen_fast_image", "imagen_standard_image", "imagen_ultra_image", "veo_fast_ms", "veo_standard_ms"] as const;
export type Plan = typeof PLANS[number];
export type Action = typeof ACTIONS[number];
export type Origin = "all" | "oauth" | "synthetic";

export function formatCredit(value: string): string {
  const n = BigInt(decimal(value));
  const fraction = (n % 1_000_000n).toString().padStart(6, "0").replace(/0+$/, "");
  return (n / 1_000_000n).toLocaleString("en-US") + (fraction ? "."+fraction : "");
}
export const formatTime = (value: string): string => new Date(instant(value)).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false });

export function parseUser(value: unknown) {
  const r = object(value);
  return { id: uuid(r.id), role: choice(r.role, ["user", "master"]), status: choice(r.status, ["active", "suspended"]),
    origin: choice(r.origin, ["oauth", "synthetic"]), signed_up_at: instant(r.signed_up_at),
    plan: choice(r.plan, PLANS), pending_plan: r.pending_plan === null ? null : choice(r.pending_plan, PLANS),
    cycle_starts_at: instant(r.cycle_starts_at), renews_at: instant(r.renews_at),
    available_microcredits: decimal(r.available_microcredits), held_microcredits: decimal(r.held_microcredits),
    charged_microcredits: decimal(r.charged_microcredits), balance_materialized: bool(r.balance_materialized) };
}
export type MasterUser = ReturnType<typeof parseUser>;
export function parseUsers(value: unknown) {
  const r = object(value), items = list(r.items).map(parseUser);
  if (items.length > 50) fail();
  return { items, next_cursor: r.next_cursor === null ? null : uuid(r.next_cursor) };
}
function auditValues(value: unknown) {
  const r = object(value), result: Record<string, string | number | null> = {};
  for (const [key, v] of Object.entries(r)) {
    if (key === "role") result[key] = choice(v, ["user", "master"]);
    else if (key === "status") result[key] = choice(v, ["active", "suspended"]);
    else if (key === "plan" || key === "pending_plan") result[key] = v === null ? null : choice(v, PLANS);
    else if (key === "bonus_microcredits") result[key] = typeof v === "number" ? String(count(v)) : decimal(v);
    else if (key === "revoked_sessions" || key === "cancelled_jobs") result[key] = count(v);
    else fail();
  }
  return result;
}
export function parseReceipt(value: unknown) {
  const r = object(value);
  return { request_id: uuid(r.request_id), action: choice(r.action, ACTIONS), before: auditValues(r.before),
    after: auditValues(r.after), created_at: instant(r.created_at), replayed: bool(r.replayed) };
}
export function parseAudit(value: unknown) {
  const r = object(value), items = list(r.items).map(value => {
    const a = object(value);
    return { request_id: uuid(a.request_id), actor_id: uuid(a.actor_id), target_id: uuid(a.target_id),
      action: choice(a.action, [...ACTIONS, "promote"]), source: choice(a.source, ["browser", "operator_cli"]),
      reason_code: choice(a.reason_code, REASONS), created_at: instant(a.created_at),
      before: auditValues(a.before), after: auditValues(a.after) };
  });
  if (items.length > 50) fail();
  return { items, next_cursor: r.next_cursor === null ? null : uuid(r.next_cursor) };
}
export function parseOverview(value: unknown) {
  const r = object(value), w = object(r.window);
  const usage = list(r.usage).map(value => { const a = object(value); return {
    meter: choice(a.meter, METERS), unit: choice(a.unit, ["token", "image", "millisecond"]),
    observed_units: decimal(a.observed_units), charged_microcredits: decimal(a.charged_microcredits) }; });
  if (usage.length !== 7 || new Set(usage.map(a => a.meter)).size !== 7) fail();
  const rate = r.success_rate === null ? null : real(r.success_rate);
  if (rate !== null && rate > 1) fail();
  return { window: { days: count(w.days), starts_at: instant(w.starts_at), ends_at: instant(w.ends_at) },
    plan_attribution: choice(r.plan_attribution, ["current_persisted_account_plan"]),
    duration_definition: choice(r.duration_definition, ["queue_inclusive_updated_minus_created"]),
    counts: list(r.counts).map(value => { const a = object(value); return { origin: choice(a.origin, ["oauth", "synthetic"]),
      status: choice(a.status, ["active", "suspended"]), plan: choice(a.plan, PLANS), count: count(a.count) }; }),
    credits: list(r.credits).map(value => { const a = object(value); return { plan: choice(a.plan, PLANS),
      reserved_microcredits: decimal(a.reserved_microcredits), held_microcredits: decimal(a.held_microcredits),
      charged_microcredits: decimal(a.charged_microcredits), released_microcredits: decimal(a.released_microcredits) }; }),
    usage, daily: list(r.daily).map(value => { const a = object(value); const day = text(a.day);
      if (!/^\d{4}-\d\d-\d\d$/.test(day)) fail(); return { day, charged_microcredits: decimal(a.charged_microcredits) }; }),
    jobs: list(r.jobs).map(value => { const a = object(value); return { model: choice(a.model, MODELS),
      state: choice(a.state, STATES), count: count(a.count), p95_seconds: a.p95_seconds === null ? null : real(a.p95_seconds) }; }),
    terminal_count: count(r.terminal_count), success_rate: rate,
    recent_failures: list(r.recent_failures).map(value => { const a = object(value); return { id: uuid(a.id),
      model: choice(a.model, MODELS), code: choice(a.code, ERRORS), created_at: instant(a.created_at) }; }),
    errors: list(r.errors).map(value => { const a = object(value); return { code: choice(a.code, ERRORS), count: count(a.count) }; }) };
}
export type Overview = ReturnType<typeof parseOverview>;
export type AuditPage = ReturnType<typeof parseAudit>;
export type MasterCommand = { request_id: string; action: Action; reason_code: typeof REASONS[number];
  target_plan?: Plan; amount_microcredits?: number; expires_at?: string | null };

export function createCommand(action: Action, reason: string, plan: Plan, credit: string, expiry: string, requestId: string, now = Date.now()): MasterCommand {
  const result: MasterCommand = { request_id: uuid(requestId), action: choice(action, ACTIONS), reason_code: choice(reason, REASONS) };
  if (action === "plan_change") result.target_plan = choice(plan, PLANS);
  if (action === "bonus_grant") {
    if (!/^(0|[1-9]\d{0,9})(\.\d{1,6})?$/.test(credit)) throw new Error("master_amount_invalid");
    const [whole, fraction = ""] = credit.split(".");
    const micro = BigInt(whole)*1_000_000n + BigInt(fraction.padEnd(6, "0"));
    if (micro <= 0n || micro > 9_000_000_000_000_000n) throw new Error("master_amount_invalid");
    result.amount_microcredits = Number(micro);
    if (expiry && (!Number.isFinite(Date.parse(expiry)) || Date.parse(expiry) <= now)) throw new Error("master_expiry_invalid");
    result.expires_at = expiry ? new Date(expiry).toISOString() : null;
  }
  return Object.freeze(result);
}
