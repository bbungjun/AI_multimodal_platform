import { test, expect } from "@playwright/test";
import { createSession as makeSession, safeReturnPath, validUser, RETURN_KEY, AUTH_ERROR_CODES, type SessionDeps, type AuthReply } from "../src/auth/session";
import { createAuthHttp, bindSessionGuard, listGenerations } from "../src/api/client";

const user = { id: "10000000-0000-4000-8000-000000000001", role: "user", status: "active",
  email: "fixture@example.test", display_name: "Fixture", picture: null };
function createSession(overrides: Partial<SessionDeps> = {}) {
  return makeSession({ me: async () => ({ status: 200, body: user }), signOut: async () => ({ status: 204 }),
    now: () => 0, path: () => "/generate", replace() {}, navigate() {}, broadcast() {}, ...overrides });
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((r) => { resolve = r; }); return { promise, resolve }; }

test("safe return preserves allowed history path", () => {
  expect(safeReturnPath("/history")).toBe("/history");
});
test("bootstrap resolves anonymous from unauthorized response", async () => {
  const session = createSession({ me: async () => ({ status: 401 }), now: () => 0 });
  await session.retry();
  expect(session.getSnapshot().kind).toBe("anonymous");
});
test("late me cannot revive session after logout", async () => {
  let resolve!: (value: AuthReply) => void;
  const session = createSession({ me: () => new Promise((r) => { resolve = r; }), now: () => 0 });
  const pending = session.retry();
  await session.logout();
  resolve?.({ status: 200, body: user });
  await pending;
  expect(session.getSnapshot().kind).toBe("anonymous");
});

for (const value of ["https://evil.test", "//evil.test", "/\\evil", "/%5cevil", "/%252525252fevil", "/history%0a", "/login", "/api/auth/me", "/jobs/no-id", "/" + "a".repeat(513), "/%ZZ"]) {
  test(`unsafe return case ${["https://evil.test", "//evil.test", "/\\evil", "/%5cevil", "/%252525252fevil", "/history%0a", "/login", "/api/auth/me", "/jobs/no-id", "/" + "a".repeat(513), "/%ZZ"].indexOf(value)}`, () => {
    expect(safeReturnPath(value)).toBe("/generate");
  });
}
test("return query allowlist and UUID detail", () => {
  expect(safeReturnPath(`/generate?mode=i2v&source_asset_id=${user.id}&prompt=discard#fragment`)).toBe(`/generate?mode=i2v&source_asset_id=${user.id}`);
  expect(safeReturnPath("/history?prompt=discard#fragment")).toBe("/history");
  expect(safeReturnPath(`/jobs/${user.id}`)).toBe(`/jobs/${user.id}`);
  expect(safeReturnPath("/generate?mode=t2i&mode=i2v")).toBe("/generate");
});
for (const status of [401, 403, 503]) test(`me status ${status}`, async () => {
  const s = createSession({ me: async () => ({ status }) }); await s.retry();
  expect(s.getSnapshot().kind).toBe(status === 401 ? "anonymous" : "unavailable");
});
for (const invalid of [{}, { ...user, role: "admin" }, { ...user, status: "suspended" }, { ...user, id: "bad" }, { ...user, email: 4 }, { ...user, display_name: {} }]) {
  test(`invalid profile ${Object.keys(invalid).length}-${JSON.stringify(invalid).length}`, async () => {
    expect(validUser(invalid)).toBeNull();
    const s = createSession({ me: async () => ({ status: 200, body: invalid }) }); await s.retry();
    expect(s.getSnapshot().kind).toBe("unavailable");
  });
}
test("same identity retains epoch; change replaces it and ignores old unauthorized", async () => {
  let profile = user;
  const s = createSession({ me: async () => ({ status: 200, body: profile }) });
  await s.retry(); const a = s.getEpoch(); await s.retry(); expect(s.getEpoch()).toBe(a);
  profile = { ...user, id: "10000000-0000-4000-8000-000000000002" };
  await s.retry(); expect(s.getEpoch()).toBeGreaterThan(a);
  s.unauthorized(a); expect(s.getSnapshot().kind).toBe("authenticated");
  s.unauthorized(s.getEpoch()); expect(s.getSnapshot().kind).toBe("anonymous");
});
test("activity threshold, hidden tab and burst coalescing", async () => {
  let now = 0; let calls = 0; const pending = deferred<AuthReply>();
  const s = createSession({ now: () => now, me: async () => { calls++; return calls === 1 ? { status: 200, body: user } : pending.promise; } });
  await s.retry(); now = 299_999; await s.activity(true); expect(calls).toBe(1);
  now++; await s.activity(false); expect(calls).toBe(1);
  const first = s.activity(true); const second = s.retry(); const third = s.activity(true);
  expect(calls).toBe(2); pending.resolve({ status: 200, body: user }); await Promise.all([first, second, third]);
});
for (const status of [204, 403, 503]) test(`logout ${status} is truthful and deduplicated`, async () => {
  let calls = 0; let broadcasts = 0; const pending = deferred<AuthReply>();
  const s = createSession({ signOut: async () => { calls++; return pending.promise; }, broadcast: () => { broadcasts++; } });
  await s.retry(); const first = s.logout(); const second = s.logout();
  expect(s.getSnapshot().kind).toBe("signing-out"); expect(calls).toBe(1);
  pending.resolve({ status }); await Promise.all([first, second]);
  expect(s.getSnapshot().kind).toBe(status === 204 ? "anonymous" : "logout-unconfirmed");
  expect(broadcasts).toBe(status === 204 ? 1 : 0);
});
test("network error locks check and leaves logout unconfirmed", async () => {
  const s = createSession({ me: async () => { throw Error("network"); }, signOut: async () => { throw Error("network"); } });
  await s.retry(); expect(s.getSnapshot().kind).toBe("unavailable");
  await s.logout(); expect(s.getSnapshot().kind).toBe("logout-unconfirmed");
});
for (const code of [...AUTH_ERROR_CODES, "unknown"]) test(`callback error scrub ${code}`, async () => {
  let path = `/?auth_error=${code}&code=discard&state=discard`;
  const s = createSession({ path: () => path, replace: (p) => { path = p; }, me: async () => ({ status: 401 }) });
  expect(path).toBe("/login"); await s.retry();
  expect(s.getSnapshot()).toEqual({ kind: "anonymous", reason: "login-error" });
});
test("native start once with safe return, storage expiry and blocked storage fallback", async () => {
  for (const age of [0, 600_000, -1]) {
    let navigations = 0; let destination = "";
    const storage = { getItem: () => JSON.stringify({ returnTo: "/history", createdAt: 600_000 - age }), setItem() {}, removeItem() {} };
    const s = createSession({ now: () => 600_000, path: () => "/login", storage,
      me: async () => ({ status: 401 }), navigate: (p) => { navigations++; destination = p; } });
    await s.retry(); s.beginLogin(); s.beginLogin(); expect(navigations).toBe(1);
    expect(new URL(destination, "https://local.test").searchParams.get("return_to")).toBe(age === 0 ? "/history" : "/generate");
  }
  let destination = "";
  const fail = () => { throw Error("blocked"); };
  const s = createSession({ storage: { getItem: fail, setItem: fail, removeItem: fail }, path: () => "/history",
    me: async () => ({ status: 401 }), navigate: (p) => { destination = p; } });
  await s.retry(); s.beginLogin(); expect(destination).toContain("return_to=%2Fhistory");
});
test("return storage is consumed on success and logout", async () => {
  const removed: string[] = [];
  const s = createSession({ storage: { getItem: () => null, setItem() {}, removeItem: (k) => removed.push(k) } });
  await s.retry(); await s.logout(); expect(removed.filter((k) => k === RETURN_KEY).length).toBe(3);
});
test("HTTP adapter uses same-origin no-store and rejects redirects and unsafe configuration", async () => {
  let calls = 0;
  const fetcher: typeof fetch = async (_input, init) => { calls++;
    expect(init?.credentials).toBe("same-origin"); expect(init?.cache).toBe("no-store"); expect(init?.redirect).toBe("error");
    return new Response(JSON.stringify(user), { status: 200 }); };
  const signal = new AbortController().signal;
  for (const base of ["", "https://local.test", "https://local.test/"]) await createAuthHttp("https://local.test", base, fetcher).me(signal);
  for (const base of ["https://evil.test", "/prefix", "https://local.test/prefix"]) await expect(createAuthHttp("https://local.test", base, fetcher).me(signal)).rejects.toThrow("same-origin");
  expect(calls).toBe(3);
});
test("HTTP timeout aborts pending transport", async () => {
  const fetcher: typeof fetch = (_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))); });
  await expect(createAuthHttp("https://local.test", "", fetcher, 5).me(new AbortController().signal)).rejects.toThrow("aborted");
});
test("late product response and 401 cannot cross account epoch", async () => {
  const originalFetch = globalThis.fetch;
  for (const status of [200, 401]) {
    const pending = deferred<Response>();
    const s = createSession(); await s.retry(); const unbind = bindSessionGuard(s);
    globalThis.fetch = () => pending.promise;
    try {
      const request = listGenerations(); const rejected = expect(request).rejects.toThrow("previous session");
      await s.logout(); await s.retry(); pending.resolve(new Response("[]", { status }));
      await rejected; expect(s.getSnapshot().kind).toBe("authenticated");
    } finally { unbind(); globalThis.fetch = originalFetch; }
  }
});

for (const status of [401, 403, 503]) test(`current product status ${status} has bounded session effect`, async () => {
  const previous = globalThis.fetch;
  const s = createSession(); await s.retry(); const unbind = bindSessionGuard(s);
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "fixture-error" }), { status });
  try {
    await expect(listGenerations()).rejects.toMatchObject({ status });
    expect(s.getSnapshot().kind).toBe(status === 401 ? "anonymous" : "authenticated");
  } finally { unbind(); globalThis.fetch = previous; }
});
test("signal burst coalesces while locked and dispose rejects late check", async () => {
  const pending = deferred<AuthReply>(); let calls = 0;
  const s = createSession({ me: async () => { calls++; return pending.promise; } });
  const first = s.sessionChanged(); const second = s.sessionChanged(); expect(calls).toBe(1);
  s.dispose(); pending.resolve({ status: 200, body: user }); await Promise.all([first, second]);
  expect(s.getSnapshot().kind).toBe("checking");
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
