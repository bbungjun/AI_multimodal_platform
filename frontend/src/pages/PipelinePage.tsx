import { Link, useParams } from "react-router-dom";

import type {
  AssetResponse,
  JobResponse,
  JobState,
  PipelineResponse,
  StateHistoryEntry,
} from "../api/client";
import { FilmIcon, ImageIcon, PipelineIcon, ClockIcon } from "../components/icons";
import { Badge, Panel, RoutePlaceholder, StatusDot } from "../components/ui";
import { isTerminalJobState } from "../hooks/useJob";
import { usePipeline } from "../hooks/usePipeline";

type Tone = "default" | "info" | "success" | "warning" | "danger" | "muted";
type PipelineStageName = "parent" | "child" | "done";

const stateSteps: JobState[] = [
  "pending",
  "enhancing",
  "queued",
  "generating",
  "polling",
  "downloading",
  "completed",
];

const stateCopy: Record<
  JobState,
  {
    label: string;
    summary: string;
    timeline: string;
  }
> = {
  pending: {
    label: "Preparing request",
    summary: "The job is stored and waiting for the runner.",
    timeline: "Request accepted.",
  },
  enhancing: {
    label: "Improving prompt",
    summary: "Prompt enhancement is running before generation.",
    timeline: "Prompt enhancement active.",
  },
  queued: {
    label: "Waiting for generation slot",
    summary: "The runner is waiting for model capacity.",
    timeline: "Queued for model execution.",
  },
  generating: {
    label: "Generating on Vertex AI",
    summary: "The model request is active.",
    timeline: "Model generation underway.",
  },
  polling: {
    label: "Waiting for model output",
    summary: "The service is polling for the completed result.",
    timeline: "Result is still being prepared.",
  },
  downloading: {
    label: "Saving result",
    summary: "The returned bytes are being written to local storage.",
    timeline: "Output is being saved.",
  },
  completed: {
    label: "Completed",
    summary: "The job reached a successful terminal state.",
    timeline: "Result is ready.",
  },
  failed: {
    label: "Failed",
    summary: "The job stopped with an error.",
    timeline: "Terminal failure state.",
  },
  cancelled: {
    label: "Cancelled",
    summary: "The job was cancelled before completion.",
    timeline: "Terminal cancellation state.",
  },
};

export function PipelinePage() {
  const { pipelineId } = useParams();
  const pipelineQuery = usePipeline(pipelineId);
  const pipeline = pipelineQuery.data;

  if (!pipelineId) {
    return (
      <RoutePlaceholder eyebrow="Missing route param" title="Pipeline id is required">
        Open a pipeline from the generation form or history to inspect both jobs.
      </RoutePlaceholder>
    );
  }

  if (pipelineQuery.isLoading) {
    return <PipelineLoading pipelineId={pipelineId} />;
  }

  if (pipelineQuery.isError || !pipeline) {
    const message =
      pipelineQuery.error instanceof Error
        ? pipelineQuery.error.message
        : "Unable to load pipeline.";
    return (
      <RoutePlaceholder eyebrow="Pipeline request failed" title={pipelineId}>
        {message}
      </RoutePlaceholder>
    );
  }

  const sourceAsset = findImageAsset(pipeline.parent);
  const activeStage = getActiveStage(pipeline);

  return (
    <div className="page-stack">
      <Panel title="Pipeline Detail" eyebrow={shortId(pipeline.id)}>
        <PipelineStatusBar pipeline={pipeline} />
        <PipelineLiveSummary activeStage={activeStage} pipeline={pipeline} />

        <div className="pipeline-shell">
          <PipelineStage
            active={activeStage === "parent"}
            icon={<ImageIcon size={18} />}
            job={pipeline.parent}
            stepLabel="Step 1"
            title="Imagen image source"
          />

          <div aria-hidden="true" className="pipeline-connector">
            <PipelineIcon size={26} />
          </div>

          <PipelineStage
            active={activeStage === "child"}
            icon={<FilmIcon size={18} />}
            job={pipeline.child}
            sourceAsset={sourceAsset}
            stepLabel="Step 2"
            title="Veo image-to-video"
          />
        </div>
      </Panel>
    </div>
  );
}

function PipelineLoading({ pipelineId }: { pipelineId: string }) {
  return (
    <div className="page-stack">
      <Panel title="Loading Pipeline" eyebrow={shortId(pipelineId)}>
        <div className="pipeline-live-summary">
          <Badge tone="info">
            <ClockIcon size={12} />
            Polling
          </Badge>
          <div className="pipeline-live-summary__copy">
            <strong>Fetching parent and child jobs</strong>
            <p>
              Pipeline detail refreshes every 2 seconds until both jobs reach a
              final state.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function PipelineStatusBar({ pipeline }: { pipeline: PipelineResponse }) {
  const terminal =
    isTerminalJobState(pipeline.parent.state) &&
    isTerminalJobState(pipeline.child.state);

  return (
    <div className="pipeline-status-bar">
      <Badge tone={toneForState(pipeline.parent.state)}>
        <StatusDot tone={dotToneForState(pipeline.parent.state)} />
        Step 1 {pipeline.parent.state}
      </Badge>
      <Badge tone={toneForState(pipeline.child.state)}>
        <StatusDot tone={dotToneForState(pipeline.child.state)} />
        Step 2 {pipeline.child.state}
      </Badge>
      {pipeline.child.blocked && <Badge tone="warning">Waiting for source image</Badge>}
      {pipeline.child.source_asset_id && (
        <Badge tone="success">
          <PipelineIcon size={12} />
          Source image connected
        </Badge>
      )}
      {!terminal && (
        <Badge tone="info">
          <ClockIcon size={12} />
          Polling every 2s
        </Badge>
      )}
    </div>
  );
}

function PipelineLiveSummary({
  activeStage,
  pipeline,
}: {
  activeStage: PipelineStageName;
  pipeline: PipelineResponse;
}) {
  const summary = getPipelineSummary(pipeline, activeStage);

  return (
    <div className="pipeline-live-summary">
      <Badge tone={summary.tone}>
        <StatusDot tone={summary.tone === "success" ? "success" : summary.tone} />
        {summary.badge}
      </Badge>
      <div className="pipeline-live-summary__copy">
        <strong>{summary.title}</strong>
        <p>{summary.detail}</p>
      </div>
    </div>
  );
}

function PipelineStage({
  active,
  icon,
  job,
  sourceAsset,
  stepLabel,
  title,
}: {
  active: boolean;
  icon: JSX.Element;
  job: JobResponse;
  sourceAsset?: AssetResponse | null;
  stepLabel: string;
  title: string;
}) {
  return (
    <article className={`pipeline-stage${active ? " pipeline-stage--active" : ""}`}>
      <div className="pipeline-stage__top">
        <span className="pipeline-stage__icon">{icon}</span>
        <Badge tone={toneForState(job.state)}>
          <StatusDot tone={dotToneForState(job.state)} />
          {job.state}
        </Badge>
      </div>

      <div className="section-label">{stepLabel}</div>
      <h2>{title}</h2>
      <p>{stateCopy[job.state].summary}</p>

      <div className="pipeline-stage__progress-copy">
        <strong>{getStageProgressTitle(job)}</strong>
        <p>{getStageProgressDetail(job)}</p>
      </div>

      <CompactStateTimeline history={job.state_history} state={job.state} />

      <div className="pipeline-stage__meta">
        <div>
          <span>Job</span>
          <Link to={`/jobs/${job.id}`}>{shortId(job.id)}</Link>
        </div>
        <div>
          <span>Model</span>
          <strong>{job.model}</strong>
        </div>
        <div>
          <span>Updated</span>
          <strong>{formatDateTime(job.updated_at)}</strong>
        </div>
        <div>
          <span>Attempts</span>
          <strong>{job.attempts}</strong>
        </div>
        {job.source_asset_id && (
          <div>
            <span>Source asset</span>
            <strong>{shortId(job.source_asset_id)}</strong>
          </div>
        )}
        {formatParameter(job, "duration_sec") && (
          <div>
            <span>Duration</span>
            <strong>{formatParameter(job, "duration_sec")}s</strong>
          </div>
        )}
      </div>

      <div className="pipeline-stage__prompt">
        <Badge tone="muted">Prompt</Badge>
        <p>{job.prompt}</p>
      </div>

      {job.error && (
        <div className="pipeline-stage__prompt">
          <Badge tone="danger">Error</Badge>
          <p>{formatErrorMessage(job.error)}</p>
        </div>
      )}

      <PipelineAssetPreview job={job} sourceAsset={sourceAsset ?? null} />
    </article>
  );
}

function CompactStateTimeline({
  history,
  state,
}: {
  history: StateHistoryEntry[];
  state: JobState;
}) {
  const activeIndex = stateSteps.includes(state) ? stateSteps.indexOf(state) : -1;

  return (
    <div className="pipeline-compact-timeline">
      {stateSteps.map((step, index) => {
        const active = step === state;
        const done = activeIndex >= 0 && index < activeIndex;
        const historyEntry = history.find((entry) => entry.state === step);

        return (
          <div
            className={`pipeline-compact-timeline__item${
              active ? " pipeline-compact-timeline__item--active" : ""
            }${!active && !done ? " pipeline-compact-timeline__item--waiting" : ""}`}
            key={step}
          >
            <StatusDot tone={active ? "info" : done ? "success" : "muted"} />
            <div className="pipeline-compact-timeline__body">
              <span>{stateCopy[step].label}</span>
              <p>{stateCopy[step].timeline}</p>
            </div>
            <small>{historyEntry ? formatDateTime(historyEntry.at) : "waiting"}</small>
          </div>
        );
      })}
      {(state === "failed" || state === "cancelled") && (
        <div className="pipeline-compact-timeline__item pipeline-compact-timeline__item--active">
          <StatusDot tone={state === "failed" ? "danger" : "warning"} />
          <div className="pipeline-compact-timeline__body">
            <span>{stateCopy[state].label}</span>
            <p>{stateCopy[state].timeline}</p>
          </div>
          <small>terminal</small>
        </div>
      )}
    </div>
  );
}

function PipelineAssetPreview({
  job,
  sourceAsset,
}: {
  job: JobResponse;
  sourceAsset: AssetResponse | null;
}) {
  const asset = job.assets[0] ?? null;

  if (asset) {
    const isImage = asset.kind === "image" || asset.mime.startsWith("image/");
    const isVideo = asset.kind === "video" || asset.mime.startsWith("video/");

    return (
      <div className="pipeline-asset-preview">
        {isImage && <img alt={`Pipeline asset ${asset.id}`} src={asset.url} />}
        {isVideo && (
          <video controls src={asset.url}>
            <a href={asset.url}>Open generated video</a>
          </video>
        )}
        {!isImage && !isVideo && (
          <div className="pipeline-asset-preview--empty">
            <strong>Asset returned</strong>
            <span>{asset.mime} cannot be previewed inline.</span>
          </div>
        )}
      </div>
    );
  }

  if (job.mode === "i2v" && sourceAsset) {
    return (
      <div className="pipeline-asset-preview">
        <img alt={`Source asset ${sourceAsset.id}`} src={sourceAsset.url} />
      </div>
    );
  }

  return (
    <div className="pipeline-asset-preview pipeline-asset-preview--empty">
      <strong>{getEmptyPreviewTitle(job)}</strong>
      <span>{getEmptyPreviewDetail(job)}</span>
    </div>
  );
}

function getActiveStage(pipeline: PipelineResponse): PipelineStageName {
  if (!isTerminalJobState(pipeline.parent.state)) {
    return "parent";
  }
  if (!isTerminalJobState(pipeline.child.state)) {
    return "child";
  }
  return "done";
}

function getPipelineSummary(
  pipeline: PipelineResponse,
  activeStage: PipelineStageName,
): {
  badge: string;
  detail: string;
  title: string;
  tone: Tone;
} {
  if (activeStage === "parent") {
    return {
      badge: "Step 1 of 2",
      detail:
        "The image job is still active. The I2V child remains blocked until an image asset is available.",
      title: `${stateCopy[pipeline.parent.state].label} for the source image`,
      tone: "info",
    };
  }

  if (pipeline.parent.state === "failed" || pipeline.parent.state === "cancelled") {
    return {
      badge: "Stopped",
      detail:
        "The image step ended before a usable source asset was produced, so the child video job cannot continue.",
      title: "Pipeline stopped at the image step",
      tone: pipeline.parent.state === "failed" ? "danger" : "warning",
    };
  }

  if (activeStage === "child") {
    return {
      badge: "Step 2 of 2",
      detail: pipeline.child.blocked
        ? "The video job is waiting for the completed image asset to be linked."
        : "The source image is connected and the Veo I2V job is progressing.",
      title: `${stateCopy[pipeline.child.state].label} for the video result`,
      tone: pipeline.child.blocked ? "warning" : "info",
    };
  }

  if (pipeline.child.state === "completed") {
    return {
      badge: "Complete",
      detail: "Both jobs reached terminal success and the resulting assets are available.",
      title: "T2I -> I2V pipeline completed",
      tone: "success",
    };
  }

  return {
    badge: "Terminal",
    detail: "The pipeline reached a terminal state. Check each stage for error details.",
    title: "Pipeline no longer has active work",
    tone: pipeline.child.state === "failed" ? "danger" : "warning",
  };
}

function getStageProgressTitle(job: JobResponse): string {
  if (job.blocked) {
    return "Waiting for upstream image";
  }
  return stateCopy[job.state].label;
}

function getStageProgressDetail(job: JobResponse): string {
  if (job.blocked) {
    return "The child I2V request is saved but will not run until the parent image asset is connected.";
  }
  if (job.mode === "i2v" && job.source_asset_id && !isTerminalJobState(job.state)) {
    return "The source image is locked and this video job continues to refresh while Veo prepares output.";
  }
  return stateCopy[job.state].summary;
}

function getEmptyPreviewTitle(job: JobResponse): string {
  if (job.blocked) {
    return "Waiting for Imagen source";
  }
  if (job.state === "failed") {
    return "No preview after failure";
  }
  if (job.state === "cancelled") {
    return "No preview after cancellation";
  }
  if (job.state === "completed") {
    return "Completed without asset";
  }
  return "Preview pending";
}

function getEmptyPreviewDetail(job: JobResponse): string {
  if (job.blocked) {
    return "Step 2 starts after Step 1 produces a valid image asset.";
  }
  if (job.state === "polling") {
    return "Veo output is still being prepared.";
  }
  if (job.state === "downloading") {
    return "The generated output is being saved locally.";
  }
  if (job.state === "failed" || job.state === "cancelled") {
    return "Inspect the stage error or state history for the reason.";
  }
  if (job.state === "completed") {
    return "The backend returned completion without a previewable asset.";
  }
  return "The preview appears here after this stage returns an asset.";
}

function toneForState(state: JobState): Tone {
  if (state === "completed") {
    return "success";
  }
  if (state === "failed") {
    return "danger";
  }
  if (state === "cancelled") {
    return "warning";
  }
  if (state === "pending" || state === "queued") {
    return "muted";
  }
  return "info";
}

function dotToneForState(state: JobState): Tone | "pending" {
  if (state === "pending" || state === "queued") {
    return "pending";
  }
  return toneForState(state);
}

function findImageAsset(job: JobResponse): AssetResponse | null {
  return (
    job.assets.find((asset) => asset.kind === "image" || asset.mime.startsWith("image/")) ??
    null
  );
}

function formatParameter(job: JobResponse, key: string): string | null {
  const value = job.parameters[key];
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  return null;
}

function formatErrorMessage(error: Record<string, unknown>): string {
  if (typeof error.message === "string") {
    return error.message;
  }
  if (typeof error.code === "string") {
    return error.code;
  }
  return JSON.stringify(error);
}

function shortId(value: string): string {
  return value.length > 12 ? value.slice(0, 8) : value;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
