import { useQuery } from "@tanstack/react-query";

import { getOpsHealth, type JobState, type OpsHealthResponse } from "../api/client";
import { Badge, Panel, StatusDot } from "../components/ui";
import { ClockIcon, CpuIcon, HistoryIcon, PipelineIcon } from "../components/icons";

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

export function OpsPage() {
  const ops = useQuery({
    queryKey: ["ops-health"],
    queryFn: getOpsHealth,
    refetchInterval: 5000,
    retry: false,
  });

  if (ops.isLoading) {
    return (
      <div className="page-stack">
        <Panel title="Operations" eyebrow="Health">
          <div className="ops-message">
            <Badge tone="info">
              <StatusDot tone="info" />
              Loading
            </Badge>
            <p>Fetching operational status.</p>
          </div>
        </Panel>
      </div>
    );
  }

  if (ops.isError || !ops.data) {
    return (
      <div className="page-stack">
        <Panel title="Operations" eyebrow="Health">
          <div className="ops-message">
            <Badge tone="danger">
              <StatusDot tone="danger" />
              Unavailable
            </Badge>
            <p>{ops.error instanceof Error ? ops.error.message : "Ops health request failed."}</p>
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
    <div className="page-stack">
      <Panel title="Runtime Health" eyebrow="Ops">
        <div className="ops-hero">
          <div>
            <Badge tone={data.ok ? "success" : "danger"}>
              <StatusDot tone={data.ok ? "success" : "danger"} />
              {data.db === "up" ? "DB up" : "DB down"}
            </Badge>
            <h2>{data.service}</h2>
            <p>{data.dispatch.mode} dispatch on {data.dispatch.queue ?? "no queue"}</p>
          </div>
          {isFetching && (
            <Badge tone="info">
              <StatusDot tone="info" />
              Refreshing
            </Badge>
          )}
        </div>
      </Panel>

      <div className="ops-grid">
        <Panel title="Jobs" eyebrow="State">
          <div className="ops-stat-grid">
            <OpsStat label="Total" value={data.jobs.total} tone="info" />
            <OpsStat label="Active" value={data.jobs.active} tone="warning" />
            <OpsStat label="Blocked" value={data.jobs.blocked} tone={data.jobs.blocked > 0 ? "warning" : "muted"} />
            <OpsStat
              label="Resume"
              value={data.jobs.resumable_polling}
              tone={data.jobs.resumable_polling > 0 ? "warning" : "muted"}
            />
          </div>
          <div className="ops-state-list">
            {jobStates.map((state) => (
              <div key={state}>
                <span>{state}</span>
                <strong>{data.jobs.by_state[state] ?? 0}</strong>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Outbox" eyebrow="Dispatch">
          <div className="ops-stat-grid">
            <OpsStat label="Pending" value={data.outbox.pending} tone={queueTone} />
            <OpsStat label="Failed" value={data.outbox.failed} tone={data.outbox.failed > 0 ? "danger" : "muted"} />
            <OpsStat label="Published" value={data.outbox.published} tone="success" />
            <OpsStat label="Total" value={data.outbox.total} tone="info" />
          </div>
          <div className="ops-state-list">
            {outboxStatuses.map((status) => (
              <div key={status}>
                <span>{status}</span>
                <strong>{data.outbox.by_status[status] ?? 0}</strong>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Worker" eyebrow="Celery">
          <div className="ops-worker-card">
            <Badge tone={workerTone}>
              <CpuIcon size={12} />
              {data.dispatch.mode}
            </Badge>
            <dl>
              <div>
                <dt>Queue</dt>
                <dd>{data.dispatch.queue ?? "-"}</dd>
              </div>
              <div>
                <dt>Late ack</dt>
                <dd>{data.dispatch.task_acks_late ? "on" : "off"}</dd>
              </div>
              <div>
                <dt>Reject lost</dt>
                <dd>{data.dispatch.task_reject_on_worker_lost ? "on" : "off"}</dd>
              </div>
              <div>
                <dt>Prefetch</dt>
                <dd>{data.dispatch.worker_prefetch_multiplier}</dd>
              </div>
            </dl>
          </div>
        </Panel>

        <Panel title="Recent Failures" eyebrow="Jobs">
          {data.recent_failures.length === 0 ? (
            <div className="ops-empty">
              <Badge tone="success">
                <StatusDot tone="success" />
                Clear
              </Badge>
              <p>No recent failed jobs.</p>
            </div>
          ) : (
            <div className="ops-failure-list">
              {data.recent_failures.map((failure) => (
                <div className="ops-failure-row" key={failure.id}>
                  <div>
                    <Badge tone={failure.dead_letter ? "warning" : "danger"}>
                      {failure.dead_letter ? <PipelineIcon size={12} /> : <HistoryIcon size={12} />}
                      {failure.code ?? "failed"}
                    </Badge>
                    <strong>{failure.model}</strong>
                    <p>{failure.message ?? "No failure message recorded."}</p>
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

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
