import assert from "node:assert/strict";
import test from "node:test";

import { GROUPS, validateRecovery, validateStart } from "./browser-acceptance-driver.mjs";

test("start protocol accepts only fixed loopback configuration", () => {
  const value = { type: "start", backend_url: "http://127.0.0.1:49152",
    frontend_origin: "http://127.0.0.1:18155", secrets: { a: "a".repeat(32), b: "b".repeat(32), master: "m".repeat(32) } };
  assert.equal(validateStart(value), value);
  assert.throws(() => validateStart({ ...value, backend_url: "https://example.com" }), /start_invalid/);
});

test("recovery protocol accepts only A and Master secrets", () => {
  const value = { type: "recovery_done", secrets: { a: "a".repeat(32), master: "m".repeat(32) } };
  assert.equal(validateRecovery(value), value);
  assert.throws(() => validateRecovery({ ...value, secrets: { ...value.secrets, b: "b".repeat(32) } }), /recovery_invalid/);
  assert.deepEqual(GROUPS, ["anonymous_proxy", "user_usage", "generation_ownership", "master_commands",
    "suspension", "logout", "emergency", "mock_recovery"]);
});
