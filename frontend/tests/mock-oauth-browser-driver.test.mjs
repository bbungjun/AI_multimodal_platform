import assert from "node:assert/strict";
import test from "node:test";

import { GROUPS, validateStart } from "./mock-oauth-browser-driver.mjs";

test("mock OAuth driver accepts only the fixed loopback contract", () => {
  const value = { type: "start", backend_url: "http://127.0.0.1:49152",
    frontend_origin: "http://127.0.0.1:18156" };
  assert.equal(validateStart(value), value);
  assert.throws(() => validateStart({ ...value, backend_url: "https://example.com" }), /start_invalid/);
  assert.throws(() => validateStart({ ...value, secret: "not-allowed" }), /start_invalid/);
});

test("mock OAuth driver keeps the fixed journey groups", () => {
  assert.deepEqual(GROUPS, ["login_start", "callback_session", "profile", "logout", "replay_refusal", "relogin"]);
});
