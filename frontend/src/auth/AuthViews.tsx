import { useEffect, useId, useRef, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { Button, Panel } from "../components/ui";
import { AUTH_COPY } from "../ui/copy";
import { authApiConfigurationValid } from "../api/client";
import { useSession } from "./AuthProvider";

export function SessionScreen() {
  const { view, beginLogin, retry, logout } = useSession();
  if (view.kind === "authenticated") return <Navigate to="/generate" replace />;
  const busy = view.kind === "checking" || view.kind === "signing-out";
  const title = view.kind === "checking" ? AUTH_COPY.checking : view.kind === "signing-out" ? AUTH_COPY.signingOut :
    view.kind === "unavailable" ? AUTH_COPY.unavailable : view.kind === "logout-unconfirmed" ? AUTH_COPY.unconfirmed : AUTH_COPY.title;
  const message = view.kind === "anonymous" ? (view.reason === "expired" ? AUTH_COPY.expired :
    view.reason === "signed-out" ? AUTH_COPY.signedOut : view.reason === "login-error" ? AUTH_COPY.loginError : AUTH_COPY.description) : AUTH_COPY.noDraft;
  const error = view.kind === "unavailable" || view.kind === "logout-unconfirmed" || (view.kind === "anonymous" && view.reason === "login-error");
  const configurationError = !authApiConfigurationValid(window.location.origin);
  return <div className="creative-auth-frame"><Panel className="creative-auth-panel" eyebrow="CREATIVEOPS · STUDIO" title={title}>
    <p role={error || configurationError ? "alert" : "status"}>{configurationError ? AUTH_COPY.configurationError : message}</p>
    <div className="creative-auth-actions">
      {view.kind === "anonymous" && <Button variant="primary" onClick={beginLogin}>{AUTH_COPY.continueGoogle}</Button>}
      {view.kind === "unavailable" && <Button onClick={() => void retry()}>{AUTH_COPY.retry}</Button>}
      {view.kind === "logout-unconfirmed" && <><Button onClick={() => void logout()}>{AUTH_COPY.retryLogout}</Button><Button onClick={() => void retry()}>{AUTH_COPY.retry}</Button></>}
      {busy && <span aria-hidden="true" className="creative-auth-pending">···</span>}
    </div>
    <p className="creative-auth-note">{AUTH_COPY.noDraft}</p>
  </Panel></div>;
}

export function WorkspaceGate() {
  const { view } = useSession();
  if (view.kind !== "authenticated") return <SessionScreen />;
  return <div key={view.user.id}><p className="creative-auth-notice">{AUTH_COPY.noDraft}</p><Outlet /></div>;
}

export function AccountControl({ mobile = false }: { mobile?: boolean }) {
  const { view, logout } = useSession();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const identity = view.kind === "authenticated" ? view.user.id : null;
  useEffect(() => { setOpen(false); }, [identity]);
  useEffect(() => {
    if (!open) return;
    const close = () => { setOpen(false); trigger.current?.focus(); };
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); close(); } };
    // Close after the browser's pointer focus transfer, so focus return survives.
    const outside = (event: MouseEvent) => { if (!container.current?.contains(event.target as Node)) close(); };
    document.addEventListener("keydown", key); document.addEventListener("click", outside);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("click", outside); };
  }, [open]);
  if (view.kind !== "authenticated") return null;
  const name = view.user.display_name?.trim() || "사용자";
  const initials = Array.from(name).slice(0, 2).join("").toUpperCase();
  return <div ref={container} className={`creative-account${mobile ? " creative-account--mobile" : ""}`}>
    <button ref={trigger} type="button" className="creative-account-trigger creative-user-card"
      aria-label={AUTH_COPY.account} aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
      <span className="creative-user-avatar" aria-hidden="true">{initials}</span>
      <span className="creative-account-name"><strong>{name}</strong><span>{AUTH_COPY.account}</span></span>
    </button>
    {open && <div id={id} className="creative-account-details">
      <strong>{name}</strong><p>{view.user.email}</p>
      <Button onClick={() => void logout()}>{AUTH_COPY.logout}</Button>
    </div>}
  </div>;
}
