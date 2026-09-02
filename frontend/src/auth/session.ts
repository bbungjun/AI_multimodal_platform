export type SafeUser = { id: string; role: "user" | "master"; status: "active";
  email: string; display_name: string | null; picture: string | null };
export type SessionView =
  | { kind: "checking" }
  | { kind: "anonymous"; reason?: "required" | "expired" | "signed-out" | "login-error" }
  | { kind: "authenticated"; user: SafeUser }
  | { kind: "unavailable" }
  | { kind: "signing-out" }
  | { kind: "logout-unconfirmed" };
export type AuthReply = { status: number; body?: unknown };
export type SessionDeps = {
  me(signal: AbortSignal): Promise<AuthReply>;
  signOut(signal: AbortSignal): Promise<AuthReply>;
  now(): number;
  path(): string;
  replace(path: string): void;
  navigate(path: string): void;
  broadcast(): void;
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem">;
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const RETURN_KEY = "creativeops.return-intent";
const RETURN_TTL = 600_000;
export const ACTIVITY_INTERVAL = 300_000;
export const AUTH_ERROR_CODES = ["auth_not_configured", "oauth_flow_invalid", "oauth_denied",
  "oauth_provider_unavailable", "oauth_identity_rejected", "authentication_required", "origin_not_allowed"] as const;

export function safeReturnPath(value: string): string {
  if (typeof value !== "string" || new TextEncoder().encode(value).length > 512) return "/generate";
  let decoded = value;
  for (let depth = 0; depth < 4; depth++) {
    if (!decoded.startsWith("/") || decoded.startsWith("//") || /[\\\x00-\x20\x7f]/.test(decoded)) return "/generate";
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      if (depth === 3) return "/generate";
      decoded = next;
    } catch { return "/generate"; }
  }
  const url = new URL(value, "https://return.invalid");
  const path = url.pathname;
  const detail = /^\/(jobs|pipelines)\/([^/]+)$/.exec(path);
  if (!["/generate", "/history", "/ops"].includes(path) && !(detail && UUID.test(detail[2]))) return "/generate";
  const query = new URLSearchParams();
  if (path === "/generate") {
    const mode = url.searchParams.get("mode");
    const asset = url.searchParams.get("source_asset_id");
    if (mode && ["t2i", "t2v", "i2v", "pipeline"].includes(mode) && url.searchParams.getAll("mode").length === 1) query.set("mode", mode);
    if (asset && UUID.test(asset) && url.searchParams.getAll("source_asset_id").length === 1) query.set("source_asset_id", asset);
  }
  return path + (query.size ? `?${query}` : "");
}

export function validUser(value: unknown): SafeUser | null {
  if (!value || typeof value !== "object") return null;
  const u = value as Record<string, unknown>;
  if (typeof u.id !== "string" || !UUID.test(u.id) || !["user", "master"].includes(String(u.role)) ||
    u.status !== "active" || typeof u.email !== "string" || u.email.length > 320 || !/^[^\s@]+@[^\s@]+$/.test(u.email) ||
    !(u.display_name === null || (typeof u.display_name === "string" && u.display_name.length <= 256)) ||
    !(u.picture === null || (typeof u.picture === "string" && u.picture.length <= 2048))) return null;
  return { id: u.id, role: u.role as SafeUser["role"], status: "active", email: u.email,
    display_name: u.display_name as string | null, picture: u.picture as string | null };
}

export function createSession(deps: SessionDeps) {
  let view: SessionView = { kind: "checking" };
  let epoch = 0;
  let lastCheck = -Infinity;
  let checking: Promise<void> | undefined;
  let signingOut: Promise<void> | undefined;
  let checkAbort: AbortController | undefined;
  let logoutAbort: AbortController | undefined;
  let navigating = false;
  const listeners = new Set<() => void>();
  let returnTo = safeReturnPath(deps.path());
  let loginError = false;
  const initial = new URL(deps.path(), "https://return.invalid");
  if (initial.searchParams.has("auth_error")) {
    // Bounded and unknown errors share a safe retry message; raw values never escape.
    loginError = true;
    deps.replace(initial.pathname === "/" || initial.pathname === "/login" ? "/login" : safeReturnPath(initial.pathname));
  }
  try {
    const stored = JSON.parse(deps.storage?.getItem(RETURN_KEY) ?? "null");
    if (stored && typeof stored.returnTo === "string" && typeof stored.createdAt === "number" &&
      deps.now() >= stored.createdAt && deps.now() - stored.createdAt < RETURN_TTL) returnTo = safeReturnPath(stored.returnTo);
    else deps.storage?.removeItem(RETURN_KEY);
  } catch { /* Storage is optional, never authentication evidence. */ }
  const publish = (next: SessionView) => { view = next; listeners.forEach((fn) => fn()); };
  const forgetReturn = () => { try { deps.storage?.removeItem(RETURN_KEY); } catch { /* optional */ } };
  const lock = (next: SessionView) => {
    epoch++;
    checkAbort?.abort(); checking = undefined;
    publish(next);
  };
  function retry(): Promise<void> {
    if (signingOut) return signingOut;
    if (checking) return checking;
    const requestEpoch = epoch;
    const abort = new AbortController(); checkAbort = abort;
    lastCheck = deps.now();
    if (view.kind !== "authenticated") publish({ kind: "checking" });
    const run = (async () => {
      try {
        const reply = await deps.me(abort.signal);
        if (epoch !== requestEpoch || abort.signal.aborted) return;
        const user = reply.status === 200 ? validUser(reply.body) : null;
        if (user) {
          if (view.kind !== "authenticated" || view.user.id !== user.id) epoch++;
          publish({ kind: "authenticated", user });
          const path = new URL(deps.path(), "https://return.invalid").pathname;
          if (path === "/login" || path === "/") deps.replace(returnTo);
          forgetReturn(); loginError = false;
        } else if (reply.status === 401) {
          const expired = view.kind === "authenticated";
          if (expired) returnTo = safeReturnPath(deps.path());
          lock({ kind: "anonymous", reason: loginError ? "login-error" : expired ? "expired" : "required" });
          deps.replace("/login");
        } else lock({ kind: "unavailable" });
      } catch { if (epoch === requestEpoch && !abort.signal.aborted) lock({ kind: "unavailable" }); }
    })();
    checking = run;
    void run.finally(() => { if (checking === run) checking = undefined; });
    return run;
  }
  function logout(): Promise<void> {
    if (signingOut) return signingOut;
    navigating = false; forgetReturn(); returnTo = "/generate";
    lock({ kind: "signing-out" });
    const abort = new AbortController(); logoutAbort = abort;
    const requestEpoch = epoch;
    const run = (async () => {
      try {
        const reply = await deps.signOut(abort.signal);
        if (requestEpoch !== epoch || abort.signal.aborted) return;
        if (reply.status === 204) {
          publish({ kind: "anonymous", reason: "signed-out" }); deps.replace("/login"); deps.broadcast();
        } else publish({ kind: "logout-unconfirmed" });
      } catch { if (requestEpoch === epoch && !abort.signal.aborted) publish({ kind: "logout-unconfirmed" }); }
    })();
    signingOut = run;
    void run.finally(() => { if (signingOut === run) signingOut = undefined; });
    return run;
  }
  return {
    getSnapshot: () => view,
    getEpoch: () => epoch,
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn); }; },
    retry, logout,
    beginLogin() {
      if (navigating || view.kind !== "anonymous") return;
      navigating = true;
      try { deps.storage?.setItem(RETURN_KEY, JSON.stringify({ returnTo, createdAt: deps.now() })); } catch { /* optional */ }
      deps.navigate(`/api/auth/google/start?ui=1&return_to=${encodeURIComponent(returnTo)}`);
    },
    activity(visible: boolean) {
      return visible && ["authenticated", "anonymous"].includes(view.kind) && deps.now() - lastCheck >= ACTIVITY_INTERVAL ? retry() : Promise.resolve();
    },
    unauthorized(requestEpoch: number) {
      if (requestEpoch !== epoch || view.kind !== "authenticated") return;
      returnTo = safeReturnPath(deps.path());
      lock({ kind: "anonymous", reason: "expired" }); deps.replace("/login");
    },
    sessionChanged() {
      if (signingOut) return signingOut;
      lock({ kind: "checking" }); return retry();
    },
    dispose() { epoch++; checkAbort?.abort(); logoutAbort?.abort(); checking = undefined; listeners.clear(); },
  };
}
export type SessionController = ReturnType<typeof createSession>;
