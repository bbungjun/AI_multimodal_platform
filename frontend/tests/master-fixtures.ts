import { test as base, expect, user, installHttp } from "./auth-fixtures";

export const target = "20000000-0000-4000-8000-000000000002";
export const member = { id: target, role: "user", status: "active", origin: "synthetic", signed_up_at: "2025-01-01T00:00:00Z",
  plan: "pro", pending_plan: "free", cycle_starts_at: "2025-01-31T00:00:00Z", renews_at: "2025-03-02T00:00:00Z",
  available_microcredits: "123456000001", held_microcredits: "50000000", charged_microcredits: "100000000", balance_materialized: false };
export const overview = { window: { days: 30, starts_at: "2025-01-01T00:00:00Z", ends_at: "2025-01-31T00:00:00Z" },
  plan_attribution: "current_persisted_account_plan", duration_definition: "queue_inclusive_updated_minus_created",
  counts: [{ origin: "synthetic", status: "active", plan: "pro", count: 30 }],
  credits: [{ plan: "pro", reserved_microcredits: "12345000000", charged_microcredits: "10000000000", released_microcredits: "2000000000", held_microcredits: "345000000" }],
  usage: ["gemini_input_token", "gemini_output_token", "imagen_fast_image", "imagen_standard_image", "imagen_ultra_image", "veo_fast_ms", "veo_standard_ms"].map(meter => ({ meter,
    unit: meter.startsWith("gemini") ? "token" : meter.startsWith("veo") ? "millisecond" : "image", observed_units: "10", charged_microcredits: "1000000" })),
  daily: [{ day: "2025-01-30", charged_microcredits: "10000000000" }],
  jobs: [{ model: "imagen-4.0-fast-generate-001", state: "completed", count: 10, p95_seconds: 4.5 }],
  terminal_count: 10, success_rate: 1, recent_failures: [], errors: [] };

export const test = base.extend<{ master: {
  reads: string[]; bodies: Record<string, unknown>[]; status: number; commandStatus: number;
  hold: Promise<void> | null; readHold: Promise<void> | null; overview: unknown; items: unknown[]; cursor: string | null; audit: unknown[];
} }>({
  master: [async ({ context, http }, use) => {
    http.profile = { ...user, role: "master", display_name: "Operator" };
    const state = { reads: [] as string[], bodies: [] as Record<string, unknown>[], status: 200, commandStatus: 200,
      hold: null as Promise<void> | null, readHold: null as Promise<void> | null,
      overview: overview as unknown, items: [member] as unknown[], cursor: null as string | null, audit: [] as unknown[] };
    await context.route("**/api/master/**", async route => {
      const url = new URL(route.request().url());
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON(); state.bodies.push(body); await state.hold;
        if (state.commandStatus !== 200) { await route.fulfill({ status: state.commandStatus, json: { detail: "untrusted_raw_error" } }); return; }
        await route.fulfill({ json: { request_id: body.request_id, action: body.action, before: {}, after: {}, created_at: "2025-01-31T00:00:00Z", replayed: state.bodies.length > 1 } }); return;
      }
      state.reads.push(url.pathname+url.search); await state.readHold;
      if (state.status !== 200) { await route.fulfill({ status: state.status, json: { detail: "untrusted_raw_error" } }); return; }
      await route.fulfill({ json: url.pathname.endsWith("overview") ? state.overview : url.pathname.endsWith("users") ?
        { items: state.items, next_cursor: url.searchParams.has("after") ? null : state.cursor } : { items: state.audit, next_cursor: null } });
    });
    await use(state);
  }, { auto: true }],
});
export { expect, user, installHttp };
