import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, getMasterView, sendMasterCommand } from "../api/client";
import { useSession } from "../auth/AuthProvider";
import { Badge, Button, Panel } from "../components/ui";
import { ACTIONS, PLANS, REASONS, createCommand, formatCredit, formatTime, parseAudit, parseOverview,
  parseReceipt, parseUsers, type Action, type AuditPage, type MasterCommand, type MasterUser, type Origin, type Overview, type Plan } from "../ui/master";

const labels = { plan_change: "플랜 변경", bonus_grant: "보너스 지급", suspend: "사용자 정지", reactivate: "사용자 재활성화", promote: "Master 지정" };
const reasonLabels: Record<string, string> = { entitlement_change: "이용 플랜 변경", support_adjustment: "고객 지원 조정",
  service_recovery: "서비스 장애 보상", account_policy: "계정 정책 위반", account_reactivated: "계정 이용 재개", operator_bootstrap: "운영자 초기 설정" };
const identity = (id: string) => <span className="master-identity">{id}</span>;

export function MasterPage() {
  const { view } = useSession();
  if (view.kind !== "authenticated" || view.user.role !== "master") return <Panel title="접근 권한이 없습니다"><p role="alert">Master 계정에서만 관리 콘솔을 사용할 수 있습니다.</p></Panel>;
  return <Console actorId={view.user.id} />;
}

function Table({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return <div className="usage-meter-table-wrap"><table className="usage-meter-table master-table">
    <thead><tr>{headers.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead>
    <tbody>{rows.length ? rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} data-label={headers[j]}>{v}</td>)}</tr>) :
      <tr><td colSpan={headers.length}>데이터가 없습니다.</td></tr>}</tbody></table></div>;
}

function QueryState({ loading, error, retry }: { loading: boolean; error: unknown; retry(): void }) {
  if (loading) return <p role="status">관리 데이터를 확인 중입니다.</p>;
  return <div role="alert"><p>{error instanceof ApiError && error.status === 403 ? "관리 권한을 확인할 수 없습니다." : "관리 데이터를 불러오지 못했습니다. 잠시 후 다시 시도하세요."}</p><Button onClick={retry}>다시 시도</Button></div>;
}

function Console({ actorId }: { actorId: string }) {
  const [tab, setTab] = useState<"overview" | "users" | "audit">("overview");
  const [origin, setOrigin] = useState<Origin>("all"), [days, setDays] = useState(30);
  const [userCursor, setUserCursor] = useState<string | null>(null), [auditCursor, setAuditCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<MasterUser | null>(null);
  const overview = useQuery({ queryKey: ["master", "overview", origin, days], queryFn: async () => parseOverview(await getMasterView("overview", { origin, days })), enabled: tab === "overview", retry: false });
  const users = useQuery({ queryKey: ["master", "users", origin, userCursor], queryFn: async () => parseUsers(await getMasterView("users", { origin, limit: 25, ...(userCursor ? { after: userCursor } : {}) })), enabled: tab === "users", retry: false });
  const audit = useQuery({ queryKey: ["master", "audit", auditCursor], queryFn: async () => parseAudit(await getMasterView("audit", { limit: 25, ...(auditCursor ? { after: auditCursor } : {}) })), enabled: tab === "audit", retry: false });
  const active = tab === "overview" ? overview : tab === "users" ? users : audit;
  return <div className="creative-page master-page">
    <section className="creative-page-hero"><div className="creative-page-hero__copy"><Badge tone="warning">MASTER · OPERATIONS</Badge>
      <h1>관리 콘솔</h1><p>계정과 크레딧을 확인하고, 변경 이력을 추적합니다.</p></div>
      <Button onClick={() => void active.refetch()} disabled={active.isFetching}>새로고침</Button></section>
    <div className="master-toolbar">
      <div className="master-tabs" aria-label="관리 화면">{(["overview", "users", "audit"] as const).map(t => <Button key={t} aria-pressed={tab === t}
        disabled={!!selected} onClick={() => setTab(t)}>{({ overview: "운영 현황", users: "사용자", audit: "Audit" })[t]}</Button>)}</div>
      {tab !== "audit" && <label>데이터 구분<select aria-label="데이터 구분" value={origin} disabled={!!selected} onChange={e => { setOrigin(e.target.value as Origin); setUserCursor(null); }}>
        <option value="all">전체</option><option value="oauth">실제 가입 사용자</option><option value="synthetic">Synthetic</option></select></label>}
      {tab === "overview" && <label>조회 기간<select aria-label="조회 기간" value={days} onChange={e => setDays(Number(e.target.value))}>{[7, 30, 90].map(n => <option key={n} value={n}>{n}일</option>)}</select></label>}
    </div>
    {active.isLoading || active.isError || !active.data ? <Panel title="관리 데이터"><QueryState loading={active.isLoading} error={active.error} retry={() => void active.refetch()} /></Panel> : <>
      {tab === "overview" && overview.data && <OverviewPanels data={overview.data} />}
      {tab === "users" && users.data && <Panel className="creative-panel" title="사용자 계정" eyebrow="ACCOUNT CONTROL">
        <p>갱신 미반영 잔액은 현재 30일 주기의 예상값입니다. 조회는 계정을 변경하지 않습니다.</p>
        <Table headers={["사용자", "플랜 · 상태", "가입 · 갱신 (KST)", "크레딧", "관리"]} rows={users.data.items.map(u => [identity(u.id),
          <>{u.plan.toUpperCase()} · {u.role}<br />{u.origin} · {u.status}{u.pending_plan && <small>다음: {u.pending_plan}</small>}</>,
          <>{formatTime(u.signed_up_at)}<br />{formatTime(u.renews_at)}</>,
          <>가능 {formatCredit(u.available_microcredits)}<br />예약 {formatCredit(u.held_microcredits)}<br />차감 {formatCredit(u.charged_microcredits)}{!u.balance_materialized && <Badge tone="warning">갱신 예상</Badge>}</>,
          <Button disabled={!!selected} onClick={() => setSelected(u)} aria-label={`사용자 관리 ${u.id}`}>관리</Button>])} />
        <div className="master-pagination"><Button disabled={!userCursor || !!selected} onClick={() => setUserCursor(null)}>처음</Button><Button disabled={!users.data.next_cursor || !!selected} onClick={() => setUserCursor(users.data!.next_cursor)}>다음 사용자</Button></div>
      </Panel>}
      {tab === "audit" && audit.data && <AuditPanel data={audit.data} first={() => setAuditCursor(null)} next={() => setAuditCursor(audit.data!.next_cursor)} hasPrevious={!!auditCursor} />}
    </>}
    {selected && <CommandForm key={selected.id} user={selected} actorId={actorId} close={() => setSelected(null)} />}
  </div>;
}

function OverviewPanels({ data }: { data: Overview }) {
  return <>
    <div className="usage-overview-grid master-summary">
      <Panel className="creative-panel" title="사용자"><strong className="master-big">{data.counts.reduce((n, r) => n+r.count, 0)}</strong><p>선택한 데이터 구분 · 현재 계정 수</p></Panel>
      <Panel className="creative-panel" title="생성 성공률"><strong className="master-big">{data.success_rate === null ? "측정 없음" : `${(data.success_rate*100).toFixed(1)}%`}</strong><p>완료·실패 {data.terminal_count}건 기준 · 취소 제외</p></Panel>
    </div>
    <Panel className="creative-panel" title="계정 분포"><Table headers={["구분", "플랜", "상태", "계정 수"]} rows={data.counts.map(r => [r.origin, r.plan.toUpperCase(), r.status, r.count])} /></Panel>
    <Panel className="creative-panel" title="크레딧 흐름"><p>예약: 생성 시각 기준 · 차감/반환: 정산 시각 기준 · 처리 중 예약: 현재 잔액</p>
      <p>현재 저장된 플랜으로 분류하며, 과거 사용 시점의 플랜이나 실제 provider 청구서가 아닙니다.</p>
      <Table headers={["플랜", "기간 예약", "기간 차감", "기간 반환", "처리 중 예약"]} rows={data.credits.map(r => [r.plan.toUpperCase(), formatCredit(r.reserved_microcredits), formatCredit(r.charged_microcredits), formatCredit(r.released_microcredits), formatCredit(r.held_microcredits)])} /></Panel>
    <Panel className="creative-panel" title="관측 사용량"><Table headers={["Meter", "원본 사용량", "내부 차감"]} rows={data.usage.map(r => [r.meter, `${r.observed_units} ${r.unit}`, formatCredit(r.charged_microcredits)])} /></Panel>
    <Panel className="creative-panel" title="일별 차감"><Table headers={["일자 (UTC)", "크레딧"]} rows={data.daily.map(r => [r.day, formatCredit(r.charged_microcredits)])} /></Panel>
    <Panel className="creative-panel" title="생성 처리"><p>p95는 모델·상태별 대기 포함 Job 생성~마지막 변경 시간입니다. Provider 응답 지연이 아닙니다.</p>
      <Table headers={["저장된 모델", "상태", "건수", "p95"]} rows={data.jobs.map(r => [r.model, r.state, r.count, r.p95_seconds === null ? "측정 없음" : `${r.p95_seconds.toFixed(2)}초`])} /></Panel>
    <Panel className="creative-panel" title="실패 유형"><Table headers={["공개 오류 코드", "건수"]} rows={data.errors.map(r => [r.code, r.count])} /><p>Job으로 저장되지 않은 사전 거절은 포함하지 않습니다.</p></Panel>
    <Panel className="creative-panel" title="최근 실패"><Table headers={["Job", "모델", "오류", "생성 (KST)"]} rows={data.recent_failures.map(r => [identity(r.id), r.model, r.code, formatTime(r.created_at)])} /></Panel>
  </>;
}

function changes(value: Record<string, string | number | null>) {
  const names: Record<string, string> = { role: "권한", status: "상태", plan: "플랜", pending_plan: "예정 플랜", bonus_microcredits: "보너스", revoked_sessions: "폐기 세션", cancelled_jobs: "취소 작업" };
  return Object.entries(value).map(([key, v]) => <div key={key}>{names[key]}: {v === null ? "없음" : key === "bonus_microcredits" ? formatCredit(String(v)) : v}</div>);
}
function AuditPanel({ data, first, next, hasPrevious }: { data: AuditPage; first(): void; next(): void; hasPrevious: boolean }) {
  return <Panel className="creative-panel" title="Audit" eyebrow="APPEND-ONLY HISTORY"><p>운영 변경 이력입니다. DB 소유자의 스키마 변경까지 방지하는 증거 저장소는 아닙니다.</p>
    <Table headers={["시각 · 요청", "수행자 → 대상", "변경 · 사유", "이전", "이후"]} rows={data.items.map(r => [<>{formatTime(r.created_at)}<br />{identity(r.request_id)}</>,
      <>{identity(r.actor_id)} → {identity(r.target_id)}</>, <>{labels[r.action]}<br />{reasonLabels[r.reason_code]}<br />{r.source}</>, changes(r.before), changes(r.after)])} />
    <div className="master-pagination"><Button disabled={!hasPrevious} onClick={first}>최신 이력</Button><Button disabled={!data.next_cursor} onClick={next}>다음 이력</Button></div></Panel>;
}

function CommandForm({ user, actorId, close }: { user: MasterUser; actorId: string; close(): void }) {
  const cache = useQueryClient(), heading = useRef<HTMLHeadingElement>(null), inFlight = useRef(false);
  const [action, setAction] = useState<Action>(user.status === "suspended" ? "reactivate" : "plan_change");
  const [plan, setPlan] = useState<Plan>(user.plan), [reason, setReason] = useState("support_adjustment");
  const [credit, setCredit] = useState(""), [expiry, setExpiry] = useState(""), [confirmed, setConfirmed] = useState(false);
  const [frozen, setFrozen] = useState<MasterCommand | null>(null), [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(""), [done, setDone] = useState(false);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    if (!frozen || done) return;
    const unload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    const navigate = (e: MouseEvent) => { if ((e.target as Element).closest("a") && !window.confirm("처리 결과가 미확인 상태입니다. 이동한 경우 Audit에서 결과를 먼저 확인하세요.")) { e.preventDefault(); e.stopPropagation(); } };
    window.addEventListener("beforeunload", unload); document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); };
  }, [frozen, done]);
  const submit = async () => {
    if (inFlight.current || !confirmed || done || action === "suspend" && user.id === actorId) return;
    let command: MasterCommand;
    try { command = frozen ?? createCommand(action, reason, plan, credit, expiry, crypto.randomUUID()); }
    catch { setMessage("금액은 양수·소수점 6자리 이내, 만료는 미래 시각으로 입력하세요."); return; }
    inFlight.current = true; setFrozen(command); setBusy(true); setMessage("");
    try {
      const receipt = parseReceipt(await sendMasterCommand(user.id, command));
      if (receipt.request_id !== command.request_id || receipt.action !== command.action) throw new Error("receipt_mismatch");
      setDone(true); setMessage(receipt.replayed ? "이미 처리된 동일 요청입니다. 중복 변경하지 않았습니다." : "변경이 완료되었습니다. Audit에 기록했습니다.");
      await Promise.all([cache.invalidateQueries({ queryKey: ["master"] }), cache.invalidateQueries({ queryKey: ["personal-usage"] })]);
    } catch { setMessage("변경 결과를 확인하지 못했습니다. 아래 버튼으로 동일 요청을 재시도하세요. 이동하거나 새로고침했다면 Audit에서 먼저 확인하세요."); }
    finally { inFlight.current = false; setBusy(false); }
  };
  return <Panel className="creative-panel master-command" eyebrow="ACCOUNT ACTION"><h2 ref={heading} tabIndex={-1}>사용자 변경</h2><p>대상 {identity(user.id)}</p>
    <fieldset disabled={!!frozen || busy || done}><label>조치<select aria-label="조치" value={action} onChange={e => { setAction(e.target.value as Action); setConfirmed(false); }}>
      {ACTIONS.map(a => <option key={a} value={a} disabled={a === "suspend" && user.id === actorId}>{labels[a]}</option>)}</select></label>
      {action === "plan_change" && <label>변경 플랜<select aria-label="변경 플랜" value={plan} onChange={e => setPlan(e.target.value as Plan)}>{PLANS.map(p => <option key={p} value={p} disabled={user.role === "master" && p !== "max"}>{p.toUpperCase()}</option>)}</select></label>}
      {action === "bonus_grant" && <><label>보너스 크레딧<input aria-label="보너스 크레딧" inputMode="decimal" value={credit} onChange={e => setCredit(e.target.value)} /></label>
        <label>만료 시각 (선택 · 현지 시각)<input aria-label="만료 시각" type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} /></label></>}
      <label>변경 사유<select aria-label="변경 사유" value={reason} onChange={e => setReason(e.target.value)}>{REASONS.filter(r => r !== "operator_bootstrap").map(r => <option key={r} value={r}>{reasonLabels[r]}</option>)}</select></label>
      <p>{action === "suspend" ? "모든 세션을 폐기하고 미발행 작업을 취소합니다. 이미 발행된 작업은 정상 정산합니다." : action === "reactivate" ? "새 로그인이 가능해집니다. 이전 세션과 취소 작업은 복원하지 않습니다." : action === "plan_change" ? "상향은 즉시, 하향은 다음 30일 주기부터 적용합니다." : "보너스 크레딧을 추가 지급합니다. 실제 결제가 아닙니다."}</p>
      <label className="master-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />대상과 변경 내용을 확인했습니다.</label></fieldset>
    {message && <p role={done ? "status" : "alert"}>{message}</p>}
    <div className="master-pagination"><Button variant="primary" disabled={!confirmed || busy || done} onClick={() => void submit()}>{busy ? "처리 중" : frozen && !done ? "동일 요청 재시도" : "변경 적용"}</Button>
      <Button onClick={close} disabled={!!frozen && !done}>닫기</Button></div></Panel>;
}
