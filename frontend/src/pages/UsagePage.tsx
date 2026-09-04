import { useQuery } from "@tanstack/react-query";

import { ApiError, getPersonalUsage } from "../api/client";
import { Badge, Button, Panel, StatusDot } from "../components/ui";
import { USAGE_COPY } from "../ui/copy";
import { buildPersonalUsageView, type PersonalUsageView } from "../ui/usage";

export function UsagePage() {
  const usage = useQuery({
    queryKey: ["personal-usage"],
    queryFn: getPersonalUsage,
    retry: false,
    staleTime: 30_000,
  });

  if (usage.isLoading) {
    return (
      <div className="creative-page creative-page--usage">
        <Panel className="creative-panel usage-state-panel" title="사용량" eyebrow="ACCOUNT">
          <div className="usage-state" role="status">
            <Badge tone="info"><StatusDot tone="pending" />확인 중</Badge>
            <p>{USAGE_COPY.loading}</p>
          </div>
        </Panel>
      </div>
    );
  }

  if (usage.isError || !usage.data) {
    return (
      <div className="creative-page creative-page--usage">
        <Panel className="creative-panel usage-state-panel" title="사용량을 표시할 수 없습니다" eyebrow="ACCOUNT">
          <div className="usage-state" role="alert">
            <Badge tone="danger"><StatusDot tone="danger" />사용 불가</Badge>
            <p>{usageFailureCopy(usage.error)}</p>
            <Button onClick={() => void usage.refetch()} disabled={usage.isFetching}>
              {USAGE_COPY.retry}
            </Button>
          </div>
        </Panel>
      </div>
    );
  }

  const view = buildPersonalUsageView(usage.data, new Date(usage.dataUpdatedAt));
  return <UsageDashboard view={view} fetching={usage.isFetching} refresh={() => void usage.refetch()} />;
}

function usageFailureCopy(error: unknown): string {
  if (error instanceof ApiError && error.status === 503 && error.detail === "usage_busy") {
    return USAGE_COPY.busy;
  }
  if (error instanceof Error && error.message === "usage_response_invalid") {
    return USAGE_COPY.invalid;
  }
  return USAGE_COPY.unavailable;
}

function UsageDashboard({
  view,
  fetching,
  refresh,
}: {
  view: PersonalUsageView;
  fetching: boolean;
  refresh: () => void;
}) {
  return (
    <div className="creative-page creative-page--usage">
      <section className="creative-page-hero usage-hero">
        <div className="creative-page-hero__copy">
          <Badge tone="success"><StatusDot tone="success" />{view.planLabel} Plan</Badge>
          <h1>{USAGE_COPY.title}</h1>
          <p>{USAGE_COPY.description}</p>
          {view.pendingPlanLabel && (
            <div className="usage-pending-plan">
              <Badge tone="warning">다음 주기 · {view.pendingPlanLabel}로 변경 예정</Badge>
            </div>
          )}
        </div>
        <div className="creative-page-hero__metrics" aria-label="사용량 요약">
          <div className="creative-metric"><span>현재 플랜</span><strong>{view.planLabel}</strong></div>
          <div className="creative-metric"><span>갱신 시각</span><strong>{view.renewsAt}</strong></div>
          <div className="creative-metric"><span>동시 처리</span><strong>{view.concurrency.active} / {view.concurrency.limit}</strong></div>
        </div>
        <Button className="usage-refresh" variant="ghost" onClick={refresh} disabled={fetching}
          aria-label={USAGE_COPY.refresh}>
          {fetching ? "새로고침 중" : "새로고침"}
        </Button>
      </section>

      <div className="usage-overview-grid">
        <Panel className="creative-panel usage-credit-panel" title="크레딧" eyebrow="CURRENT BALANCE">
          <div className="usage-credit-primary">
            <span>사용 가능 크레딧</span>
            <strong>{view.credit.available}</strong>
            <small>기본 한도와 사용 가능한 보너스를 포함합니다.</small>
          </div>
          <dl className="usage-definition-grid">
            <div><dt>처리 중 예약</dt><dd>{view.credit.held}</dd></div>
            <div><dt>현재 주기 차감</dt><dd>{view.credit.charged}</dd></div>
            <div><dt>주기 기본 한도</dt><dd>{view.credit.allowance}</dd></div>
          </dl>
          <UsageProgress label="주기 기본 한도 대비 사용" value={view.allowanceProgressPercent}
            detail={`${view.credit.charged} / ${view.credit.allowance}`} />
        </Panel>

        <Panel className="creative-panel usage-cycle-panel" title="30일 주기" eyebrow={`CYCLE ${view.cycleIndex}`}>
          <dl className="usage-definition-grid usage-definition-grid--stacked">
            <div><dt>시작</dt><dd>{view.startsAt}</dd></div>
            <div><dt>갱신</dt><dd>{view.renewsAt}</dd></div>
          </dl>
          <UsageProgress label="현재 주기 경과" value={view.cycleProgressPercent}
            detail={`${view.cycleProgressPercent}%`} />
          <p className="usage-updated">마지막 확인 {view.updatedAt}</p>
        </Panel>

        <Panel className="creative-panel usage-concurrency-panel" title="동시 처리" eyebrow="ACTIVE REQUESTS">
          <div className="usage-concurrency-value">
            <strong>{view.concurrency.active}</strong><span>/ {view.concurrency.limit}</span>
          </div>
          <p>held 상태의 최상위 요청이 슬롯 하나를 사용합니다.</p>
          <UsageProgress label="동시 처리 슬롯" value={view.concurrencyPercent}
            detail={`${view.concurrency.active} / ${view.concurrency.limit}`} />
        </Panel>
      </div>

      <Panel className="creative-panel usage-meter-panel" title="과금 meter" eyebrow="CURRENT CYCLE">
        <div className="usage-meter-intro">
          <p>관측 사용량은 원본 단위, 차감 크레딧은 내부 정산값입니다.</p>
          <Badge tone="muted">정확한 모델별 청구서가 아닙니다</Badge>
        </div>
        <div className="usage-meter-table-wrap">
          <table className="usage-meter-table">
            <thead><tr><th scope="col">Meter</th><th scope="col">관측 사용량</th><th scope="col">차감 크레딧</th></tr></thead>
            <tbody>
              {view.meters.map((meter) => (
                <tr key={meter.meter}>
                  <th scope="row" data-label="Meter"><strong>{meter.label}</strong><small>{meter.meter}</small></th>
                  <td data-label="관측 사용량">{meter.observed}</td>
                  <td data-label="차감 크레딧">{meter.charged}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function UsageProgress({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="usage-progress-block">
      <div><span>{label}</span><strong>{detail}</strong></div>
      <div className="usage-progress" role="progressbar" aria-label={label}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}>
        <span style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
