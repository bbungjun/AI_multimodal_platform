import { useQuery } from "@tanstack/react-query";

import { getOpsHealth, type JobState, type OpsHealthResponse } from "../api/client";
import { Badge, Panel, StatusDot } from "../components/ui";
import { ClockIcon, CpuIcon, HistoryIcon, PipelineIcon } from "../components/icons";
import { OPS_COPY } from "../ui/copy";
import { formatDateTime, formatJobState } from "../ui/viewModels";

const jobStates: JobState[] = [
  "pending",
  "enhancing",
  "queued",
  "generating",
  "polling",
  "downloading",
  "completed",
  "failed",
  "cancelled",
];

const outboxStatuses = ["pending", "published", "failed"] as const;

const outboxStatusCopy: Record<(typeof outboxStatuses)[number], string> = {
  pending: "대기 중",
  published: "발행됨",
  failed: "실패",
};

export function OpsPage() {
  const ops = useQuery({
    queryKey: ["ops-health"],
    queryFn: getOpsHealth,
    refetchInterval: 5000,
    retry: false,
  });

  if (ops.isLoading) {
    return (
      <div className="creative-page creative-page--ops">
        <Panel className="creative-panel" title="운영 상태" eyebrow="헬스">
          <div className="ops-message">
            <Badge tone="info">
              <StatusDot tone="info" />
              불러오는 중
            </Badge>
            <p>운영 상태를 확인하고 있습니다.</p>
          </div>
        </Panel>
      </div>
    );
  }

  if (ops.isError || !ops.data) {
    return (
      <div className="creative-page creative-page--ops">
        <Panel className="creative-panel" title="운영 상태" eyebrow="헬스">
          <div className="ops-message">
            <Badge tone="danger">
              <StatusDot tone="danger" />
              사용 불가
            </Badge>
            <p>{ops.error instanceof Error ? ops.error.message : "운영 상태 요청에 실패했습니다."}</p>
          </div>
        </Panel>
      </div>
    );
  }

  return <OpsDashboard data={ops.data} isFetching={ops.isFetching} />;
}

function OpsDashboard({
  data,
  isFetching,
}: {
  data: OpsHealthResponse;
  isFetching: boolean;
}) {
  const queueTone = data.outbox.failed > 0 ? "danger" : data.outbox.pending > 0 ? "warning" : "success";
  const workerTone = data.dispatch.task_acks_late && data.dispatch.task_reject_on_worker_lost
    ? "success"
    : "warning";

  return (
    <div className="creative-page creative-page--ops">
      <section className="creative-page-hero">
        <div className="creative-page-hero__copy">
          <Badge tone={data.ok ? "success" : "danger"}>
            <StatusDot tone={data.ok ? "success" : "danger"} />
            {data.db === "up" ? "DB 연결됨" : "DB 연결 끊김"}
          </Badge>
          <h1>운영 상태</h1>
          <p>{data.dispatch.mode} 디스패치 · 큐 {data.dispatch.queue ?? "없음"}</p>
        </div>
        <div className="creative-page-hero__metrics" aria-label="운영 요약">
          <div className="creative-metric">
            <span>작업</span>
            <strong>{data.jobs.total}</strong>
          </div>
          <div className="creative-metric">
            <span>Outbox</span>
            <strong>{data.outbox.pending}</strong>
          </div>
          <div className="creative-metric">
            <span>실패</span>
            <strong>{data.recent_failures.length}</strong>
          </div>
        </div>
        {isFetching && (
          <Badge tone="info">
            <StatusDot tone="info" />
            새로고침 중
          </Badge>
        )}
      </section>

      <div className="ops-grid">
        <Panel className="creative-panel" title="작업" eyebrow="상태">
          <div className="ops-stat-grid">
            <OpsStat label="전체" value={data.jobs.total} tone="info" />
            <OpsStat label="진행 중" value={data.jobs.active} tone="warning" />
            <OpsStat label="대기 차단" value={data.jobs.blocked} tone={data.jobs.blocked > 0 ? "warning" : "muted"} />
            <OpsStat
              label="재개 가능"
              value={data.jobs.resumable_polling}
              tone={data.jobs.resumable_polling > 0 ? "warning" : "muted"}
            />
          </div>
          <div className="ops-state-list">
            {jobStates.map((state) => (
              <div key={state}>
                <span>{formatJobState(state)}</span>
                <strong>{data.jobs.by_state[state] ?? 0}</strong>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="creative-panel" title={OPS_COPY.outbox} eyebrow="Dispatch">
          <div className="ops-stat-grid">
            <OpsStat label="대기 중" value={data.outbox.pending} tone={queueTone} />
            <OpsStat label="실패" value={data.outbox.failed} tone={data.outbox.failed > 0 ? "danger" : "muted"} />
            <OpsStat label="발행됨" value={data.outbox.published} tone="success" />
            <OpsStat label="전체" value={data.outbox.total} tone="info" />
          </div>
          <div className="ops-state-list">
            {outboxStatuses.map((status) => (
              <div key={status}>
                <span>{outboxStatusCopy[status]}</span>
                <strong>{data.outbox.by_status[status] ?? 0}</strong>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="creative-panel" title="워커" eyebrow="Celery">
          <div className="ops-worker-card">
            <Badge tone={workerTone}>
              <CpuIcon size={12} />
              {data.dispatch.mode}
            </Badge>
            <dl>
              <div>
                <dt>큐</dt>
                <dd>{data.dispatch.queue ?? "-"}</dd>
              </div>
              <div>
                <dt>지연 ack</dt>
                <dd>{data.dispatch.task_acks_late ? "켜짐" : "꺼짐"}</dd>
              </div>
              <div>
                <dt>유실 작업 거부</dt>
                <dd>{data.dispatch.task_reject_on_worker_lost ? "켜짐" : "꺼짐"}</dd>
              </div>
              <div>
                <dt>Prefetch</dt>
                <dd>{data.dispatch.worker_prefetch_multiplier}</dd>
              </div>
            </dl>
          </div>
        </Panel>

        <Panel className="creative-panel" title={OPS_COPY.recentFailures} eyebrow="작업">
          {data.recent_failures.length === 0 ? (
            <div className="ops-empty">
              <Badge tone="success">
                <StatusDot tone="success" />
                정상
              </Badge>
              <p>최근 실패 작업이 없습니다.</p>
            </div>
          ) : (
            <div className="ops-failure-list">
              {data.recent_failures.map((failure) => (
                <div className="ops-failure-row" key={failure.id}>
                  <div>
                    <Badge tone={failure.dead_letter ? "warning" : "danger"}>
                      {failure.dead_letter ? <PipelineIcon size={12} /> : <HistoryIcon size={12} />}
                      {failure.dead_letter ? OPS_COPY.deadLetter : failure.code ?? "실패"}
                    </Badge>
                    <strong>{failure.model}</strong>
                    <p>{failure.message ?? "기록된 실패 메시지가 없습니다."}</p>
                  </div>
                  <span title={failure.id}>
                    <ClockIcon size={12} />
                    {formatDateTime(failure.updated_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function OpsStat({
  label,
  tone,
  value,
}: {
  label: string;
  tone: "danger" | "info" | "muted" | "success" | "warning";
  value: number;
}) {
  return (
    <div className={`ops-stat ops-stat--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
