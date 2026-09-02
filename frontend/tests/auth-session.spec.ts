import { test, expect } from "@playwright/test";
import { createSession, safeReturnPath } from "../src/auth/session";

test("safe return preserves allowed history path", () => {
  expect(safeReturnPath("/history")).toBe("/history");
});
test("bootstrap resolves anonymous from unauthorized response", async () => {
  const session = createSession({ me: async () => ({ status: 401 }), now: () => 0 });
  await session.retry();
  expect(session.getSnapshot().kind).toBe("anonymous");
});
test("late me cannot revive session after logout", async () => {
  let resolve!: (value: unknown) => void;
  const session = createSession({ me: () => new Promise((r) => { resolve = r; }), now: () => 0 });
  const pending = session.retry();
  await session.logout();
  resolve?.({ status: 200 });
  await pending;
  expect(session.getSnapshot().kind).toBe("anonymous");
});
test("idle clock does not request me; visible activity checks after five minutes", async () => {
  let now = 0;
  let calls = 0;
  const session = createSession({ me: async () => { calls++; return { status: 401 }; }, now: () => now });
  await session.retry();
  now = 12 * 60 * 60 * 1000;
  expect(calls).toBe(1);
  await session.activity(true);
  expect(calls).toBe(2);
});
