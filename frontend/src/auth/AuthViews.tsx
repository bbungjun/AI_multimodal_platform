import { Navigate, Outlet } from "react-router-dom";
import { Button, Panel } from "../components/ui";
import { AUTH_COPY } from "../ui/copy";
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
  return <div className="creative-auth-frame"><Panel className="creative-auth-panel" eyebrow="CREATIVEOPS · STUDIO" title={title}>
    <p role={error ? "alert" : "status"}>{message}</p>
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
