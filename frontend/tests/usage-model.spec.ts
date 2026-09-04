import { test, expect } from "@playwright/test";

import { buildPersonalUsageView, formatMicrocredits, parsePersonalUsage } from "../src/ui/usage";
import type { PersonalUsageResponse } from "../src/api/types";

const raw: PersonalUsageResponse = {
  plan: "pro", pending_plan: "free", rate_card_version: "v1",
  cycle: { index: 3, starts_at: "2026-09-01T00:00:00Z", renews_at: "2026-10-01T00:00:00Z",
    allowance_microcredits: 1_000_000_000, charged_microcredits: 250_000_000 },
  credit: { available_microcredits: 1_234_567_890, held_microcredits: 2_000_000 },
  concurrency: { active_requests: 2, limit: 3 },
  usage: [
    { meter: "gemini_input_token", unit: "token", observed_units: 10, charged_microcredits: 1_000 },
    { meter: "gemini_output_token", unit: "token", observed_units: 20, charged_microcredits: 2_000 },
    { meter: "imagen_fast_image", unit: "image", observed_units: 3, charged_microcredits: 3_000 },
    { meter: "imagen_standard_image", unit: "image", observed_units: 4, charged_microcredits: 4_000 },
    { meter: "imagen_ultra_image", unit: "image", observed_units: 5, charged_microcredits: 5_000 },
    { meter: "veo_fast_ms", unit: "millisecond", observed_units: 6_000, charged_microcredits: 6_000 },
    { meter: "veo_standard_ms", unit: "millisecond", observed_units: 7_000, charged_microcredits: 7_000 },
  ],
};

test("exact response becomes a bounded presentation model", () => {
  const parsed = parsePersonalUsage(raw);
  const view = buildPersonalUsageView(parsed, new Date("2026-09-16T00:00:00Z"));
  expect(view.planLabel).toBe("Pro");
  expect(view.pendingPlanLabel).toBe("Free");
  expect(view.cycleProgressPercent).toBe(50);
  expect(view.allowanceProgressPercent).toBe(25);
  expect(view.concurrencyPercent).toBeCloseTo(66.67, 1);
  expect(view.credit.available).toBe("1,234.568");
  expect(view.meters.map((item) => item.label)).toEqual([
    "Gemini 입력", "Gemini 출력", "Imagen Fast", "Imagen Standard",
    "Imagen Ultra", "Veo Fast", "Veo Standard",
  ]);
  expect(view.meters.at(-1)?.observed).toBe("7,000 ms");
});

test("microcredit formatting is integer based and bounded", () => {
  expect(formatMicrocredits(0)).toBe("0");
  expect(formatMicrocredits(1)).toBe("0.000001");
  expect(formatMicrocredits(1_000_000)).toBe("1");
  expect(formatMicrocredits(9_223_000_000)).toBe("9,223");
});

for (const mutation of [
  (value: any) => { value.extra = true; },
  (value: any) => { value.plan = "master"; },
  (value: any) => { value.cycle.index = -1; },
  (value: any) => { value.credit.available_microcredits = 0.5; },
  (value: any) => { value.credit.held_microcredits = Number.MAX_SAFE_INTEGER + 1; },
  (value: any) => { value.cycle.renews_at = value.cycle.starts_at; },
  (value: any) => { value.usage.reverse(); },
  (value: any) => { value.usage[0].unit = "image"; },
  (value: any) => { value.usage[0].prompt = "discard"; },
]) test("malformed or expanded payload fails closed", () => {
  const value = structuredClone(raw) as any;
  mutation(value);
  expect(() => parsePersonalUsage(value)).toThrow("usage_response_invalid");
});

test("ratios clamp without changing truthful integer values", () => {
  const value = structuredClone(raw);
  value.cycle.charged_microcredits = 2_000_000_000;
  value.concurrency.active_requests = 5;
  const view = buildPersonalUsageView(parsePersonalUsage(value), new Date("2027-01-01T00:00:00Z"));
  expect(view.cycleProgressPercent).toBe(100);
  expect(view.allowanceProgressPercent).toBe(100);
  expect(view.concurrencyPercent).toBe(100);
  expect(view.credit.charged).toBe("2,000");
});
