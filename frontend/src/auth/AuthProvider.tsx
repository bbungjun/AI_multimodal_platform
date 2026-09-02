import { createContext, useContext, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { bindSessionGuard, createAuthHttp } from "../api/client";
import { createSession, type SessionView } from "./session";

type SessionInterface = { view: SessionView; beginLogin(): void; retry(): Promise<void>; logout(): Promise<void> };
const SessionContext = createContext<SessionInterface | null>(null);

export function createBrowserSession() {
  let storage: Storage | undefined;
  let channel: BroadcastChannel | undefined;
  try { storage = window.sessionStorage; } catch { /* optional storage */ }
  const session = createSession({ ...createAuthHttp(window.location.origin), now: () => Date.now(), storage,
    path: () => window.location.pathname + window.location.search,
    replace(path) { window.history.replaceState(null, "", path); window.dispatchEvent(new PopStateEvent("popstate")); },
    navigate(path) { window.location.assign(path); }, broadcast() { channel?.postMessage("session-changed"); },
  });
  return Object.assign(session, { connect() {
    try { channel = new BroadcastChannel("creativeops.session"); } catch { channel = undefined; }
    if (channel) channel.onmessage = (event) => { if (event.data === "session-changed") void session.sessionChanged(); };
    const activity = (event: Event) => {
      if ((event.type === "pointerdown" || event.type === "keydown") && !event.isTrusted) return;
      void session.activity(document.visibilityState === "visible");
    };
    window.addEventListener("focus", activity);
    window.addEventListener("pointerdown", activity, { passive: true });
    window.addEventListener("keydown", activity);
    document.addEventListener("visibilitychange", activity);
    return () => {
      window.removeEventListener("focus", activity); window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity); document.removeEventListener("visibilitychange", activity);
      channel?.close(); channel = undefined;
    };
  } });
}
const newClient = () => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false }, mutations: { retry: false } } });

export function AuthProvider({ session, children }: { session: ReturnType<typeof createBrowserSession>; children: ReactNode }) {
  const view = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const resource = useRef({ epoch: session.getEpoch(), client: undefined as QueryClient | undefined });
  if (!resource.current.client) resource.current.client = newClient();
  const [cache, setCache] = useState({ epoch: resource.current.epoch, client: resource.current.client });
  const mounted = useRef(false);
  useLayoutEffect(() => {
    mounted.current = true;
    const unbind = bindSessionGuard(session);
    const disconnect = session.connect();
    const syncCache = () => {
      const epoch = session.getEpoch();
      if (resource.current.epoch === epoch) return;
      const old = resource.current.client!;
      void old.cancelQueries(); old.clear();
      const next = { epoch, client: newClient() }; resource.current = next; setCache(next);
    };
    const unsubscribe = session.subscribe(syncCache);
    syncCache();
    void session.retry();
    return () => {
      mounted.current = false; unsubscribe(); unbind(); disconnect();
      // StrictMode's setup/cleanup/setup shares the same in-flight bootstrap.
      queueMicrotask(() => { if (!mounted.current) { session.dispose(); resource.current.client?.clear(); } });
    };
  }, [session]);
  const admittedView: SessionView = view.kind === "authenticated" && cache.epoch !== session.getEpoch() ? { kind: "checking" } : view;
  return <SessionContext.Provider value={{ view: admittedView, beginLogin: session.beginLogin, retry: session.retry, logout: session.logout }}>
    <QueryClientProvider client={cache.client}>{children}</QueryClientProvider>
  </SessionContext.Provider>;
}
export function useSession(): SessionInterface {
  const context = useContext(SessionContext);
  if (!context) throw new Error("Session provider is required");
  return context;
}
