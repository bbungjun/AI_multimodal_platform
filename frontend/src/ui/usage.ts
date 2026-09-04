import type {
  PersonalPlan,
  PersonalUsageMeter,
  PersonalUsageResponse,
  PersonalUsageUnit,
} from "../api/types";

const meterContract: ReadonlyArray<{
  meter: PersonalUsageMeter;
  unit: PersonalUsageUnit;
  label: string;
}> = [
  { meter: "gemini_input_token", unit: "token", label: "Gemini 입력" },
  { meter: "gemini_output_token", unit: "token", label: "Gemini 출력" },
  { meter: "imagen_fast_image", unit: "image", label: "Imagen Fast" },
  { meter: "imagen_standard_image", unit: "image", label: "Imagen Standard" },
  { meter: "imagen_ultra_image", unit: "image", label: "Imagen Ultra" },
  { meter: "veo_fast_ms", unit: "millisecond", label: "Veo Fast" },
  { meter: "veo_standard_ms", unit: "millisecond", label: "Veo Standard" },
];

const plans: ReadonlyArray<PersonalPlan> = ["free", "pro", "max"];
const planLabels: Record<PersonalPlan, string> = { free: "Free", pro: "Pro", max: "Max" };
const integer = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
const dateTime = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
});

export type PersonalUsageView = {
  planLabel: string;
  pendingPlanLabel: string | null;
  cycleIndex: number;
  startsAt: string;
  renewsAt: string;
  updatedAt: string;
  cycleProgressPercent: number;
  allowanceProgressPercent: number;
  credit: { available: string; held: string; charged: string; allowance: string };
  concurrency: { active: number; limit: number };
  concurrencyPercent: number;
  meters: Array<{
    meter: PersonalUsageMeter;
    label: string;
    observed: string;
    charged: string;
  }>;
};

function invalid(): never {
  throw new Error("usage_response_invalid");
}

function record(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  const result = value as Record<string, unknown>;
  const actual = Object.keys(result).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) invalid();
  return result;
}

function safeInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) invalid();
  return value;
}

function instant(value: unknown): string {
  if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) invalid();
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) invalid();
  return value;
}

export function parsePersonalUsage(value: unknown): PersonalUsageResponse {
  const root = record(value, ["plan", "pending_plan", "rate_card_version", "cycle", "credit", "concurrency", "usage"]);
  if (!plans.includes(root.plan as PersonalPlan)) invalid();
  if (!(root.pending_plan === null || root.pending_plan === "free" || root.pending_plan === "pro")) invalid();
  if (root.rate_card_version !== "v1") invalid();

  const cycle = record(root.cycle, ["index", "starts_at", "renews_at", "allowance_microcredits", "charged_microcredits"]);
  const startsAt = instant(cycle.starts_at);
  const renewsAt = instant(cycle.renews_at);
  if (Date.parse(startsAt) >= Date.parse(renewsAt)) invalid();
  const credit = record(root.credit, ["available_microcredits", "held_microcredits"]);
  const concurrency = record(root.concurrency, ["active_requests", "limit"]);
  if (!Array.isArray(root.usage) || root.usage.length !== meterContract.length) invalid();

  const usage = root.usage.map((entry, index) => {
    const item = record(entry, ["meter", "unit", "observed_units", "charged_microcredits"]);
    const contract = meterContract[index];
    if (item.meter !== contract.meter || item.unit !== contract.unit) invalid();
    return {
      meter: contract.meter,
      unit: contract.unit,
      observed_units: safeInteger(item.observed_units),
      charged_microcredits: safeInteger(item.charged_microcredits),
    };
  });

  const limit = safeInteger(concurrency.limit);
  if (limit < 1) invalid();
  return {
    plan: root.plan as PersonalPlan,
    pending_plan: root.pending_plan as "free" | "pro" | null,
    rate_card_version: "v1",
    cycle: {
      index: safeInteger(cycle.index), starts_at: startsAt, renews_at: renewsAt,
      allowance_microcredits: safeInteger(cycle.allowance_microcredits),
      charged_microcredits: safeInteger(cycle.charged_microcredits),
    },
    credit: {
      available_microcredits: safeInteger(credit.available_microcredits),
      held_microcredits: safeInteger(credit.held_microcredits),
    },
    concurrency: { active_requests: safeInteger(concurrency.active_requests), limit },
    usage,
  };
}

function percent(numerator: number, denominator: number): number {
  if (denominator <= 0) return numerator > 0 ? 100 : 0;
  return Math.round(Math.min(100, Math.max(0, numerator / denominator * 100)) * 100) / 100;
}

export function formatMicrocredits(value: number): string {
  if (!Number.isSafeInteger(value) || value < 0) invalid();
  const credits = value / 1_000_000;
  return new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: credits < 1 && credits > 0 ? 6 : 3,
  }).format(credits);
}

export function buildPersonalUsageView(snapshot: PersonalUsageResponse, now: Date): PersonalUsageView {
  const starts = Date.parse(snapshot.cycle.starts_at);
  const renews = Date.parse(snapshot.cycle.renews_at);
  const current = now.getTime();
  if (!Number.isFinite(current)) invalid();
  const unitLabels: Record<PersonalUsageUnit, string> = {
    token: "토큰", image: "장", millisecond: "ms",
  };
  return {
    planLabel: planLabels[snapshot.plan],
    pendingPlanLabel: snapshot.pending_plan ? planLabels[snapshot.pending_plan] : null,
    cycleIndex: snapshot.cycle.index,
    startsAt: dateTime.format(new Date(starts)),
    renewsAt: dateTime.format(new Date(renews)),
    updatedAt: dateTime.format(now),
    cycleProgressPercent: percent(current - starts, renews - starts),
    allowanceProgressPercent: percent(
      snapshot.cycle.charged_microcredits, snapshot.cycle.allowance_microcredits,
    ),
    credit: {
      available: formatMicrocredits(snapshot.credit.available_microcredits),
      held: formatMicrocredits(snapshot.credit.held_microcredits),
      charged: formatMicrocredits(snapshot.cycle.charged_microcredits),
      allowance: formatMicrocredits(snapshot.cycle.allowance_microcredits),
    },
    concurrency: {
      active: snapshot.concurrency.active_requests,
      limit: snapshot.concurrency.limit,
    },
    concurrencyPercent: percent(snapshot.concurrency.active_requests, snapshot.concurrency.limit),
    meters: snapshot.usage.map((item, index) => ({
      meter: item.meter,
      label: meterContract[index].label,
      observed: `${integer.format(item.observed_units)} ${unitLabels[item.unit]}`,
      charged: formatMicrocredits(item.charged_microcredits),
    })),
  };
}
