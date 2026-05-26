import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { AssetResponse, JobResponse, JobState, StateHistoryEntry } from "../api/client";
import { Badge, Button, Panel, RoutePlaceholder, StatusDot } from "../components/ui";
import { FilmIcon, ImageIcon, PipelineIcon } from "../components/icons";
import { useAsset } from "../hooks/useAsset";
import { isTerminalJobState, useJob } from "../hooks/useJob";

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
    detail: string;
    timeline: string;
  }
> = {
  pending: {
    label: "Preparing request",
    summary: "The job is accepted and waiting for the runner to pick it up.",
    detail:
      "The request is saved and waiting for the next available generation slot.",
    timeline: "Request stored and ready for processing.",
  },
  enhancing: {
    label: "Improving prompt",
    summary: "Gemini is preparing the prompt used for generation.",
    detail:
      "Prompt enhancement is running before the image or video model call starts.",
    timeline: "Prompt enhancement step is active.",
  },
  queued: {
    label: "Waiting for generation slot",
    summary: "The job is queued behind current model capacity.",
    detail:
      "The runner is waiting for an available slot before sending this request to Vertex AI.",
    timeline: "Queued until model capacity is available.",
  },
  generating: {
    label: "Generating on Vertex AI",
    summary: "The model request is running.",
    detail:
      "Imagen or Veo is creating the output. This is usually the longest part of the job.",
    timeline: "Model generation is underway.",
  },
  polling: {
    label: "Waiting for model output",
    summary: "The service is checking for the completed result.",
    detail:
      "Long-running video and image operations can take time; this page refreshes automatically while the result is prepared.",
    timeline: "The result is being prepared.",
  },
  downloading: {
    label: "Saving result",
    summary: "The generated output is being written to local storage.",
    detail:
      "The model returned data and the result is being saved so it can be previewed here.",
    timeline: "Generated output is being saved.",
  },
  completed: {
    label: "Completed",
    summary: "The job reached a final successful state.",
    detail: "The generated asset is ready in the Asset Viewer when one was returned.",
    timeline: "Result is ready.",
  },
  failed: {
    label: "Failed",
    summary: "The job stopped with an error.",
    detail: "The request returned an error.",
    timeline: "Terminal failure state.",
  },
  cancelled: {
    label: "Cancelled",
    summary: "The job was cancelled before completion.",
    detail: "No further generation work will run for this job.",
    timeline: "Terminal cancellation state.",
  },
};

export function JobDetailPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const jobQuery = useJob(jobId);
  const job = jobQuery.data;
  const primaryAsset = job?.assets[0] ?? null;
  const imageResultAsset = useMemo(() => findCompletedImageAsset(job), [job]);
  const i2vSourceAssetId = getI2VSourcePreviewAssetId(job);
  const i2vSourceQuery = useAsset(i2vSourceAssetId);

  if (!jobId) {
    return (
      <RoutePlaceholder eyebrow="Missing route param" title="Job id is required">
        Navigate from a submitted generation or history row to inspect a job.
      </RoutePlaceholder>
    );
  }

  if (jobQuery.isLoading) {
    return <JobLoading jobId={jobId} />;
  }

  if (jobQuery.isError || !job) {
    const message =
      jobQuery.error instanceof Error ? jobQuery.error.message : "Unable to load job.";
    return (
      <RoutePlaceholder eyebrow="Job request failed" title={jobId}>
        {message}
      </RoutePlaceholder>
    );
  }

  return (
    <div className="page-grid page-grid--detail">
      <Panel className="asset-shell" title="Asset Viewer" eyebrow="Result">
        <AssetViewer
          asset={primaryAsset}
          imageResultAsset={imageResultAsset}
          i2vSourceAsset={i2vSourceQuery.data ?? null}
          i2vSourceError={i2vSourceQuery.isError}
          i2vSourceLoading={i2vSourceQuery.isLoading}
          job={job}
          onStartI2V={(assetId) => {
            navigate(`/generate?mode=i2v&source_asset_id=${assetId}`);
          }}
        />
      </Panel>

      <Panel
        title="Job State"
        eyebrow={isTerminalJobState(job.state) ? "Terminal state" : "Live progress"}
      >
        {!isTerminalJobState(job.state) && <CurrentStepSummary job={job} />}
        <JobStateTimeline history={job.state_history} state={job.state} />
        <JobWaitingContext job={job} />
      </Panel>

      <Panel title="Request Summary" eyebrow={job.mode}>
        <RequestSummary job={job} />
      </Panel>

      {job.error && (
        <Panel title="Error Message" eyebrow="Generation error">
          <div className="inline-notice inline-notice--danger">
            {formatErrorMessage(job.error)}
          </div>
        </Panel>
      )}
    </div>
  );
}

function JobLoading({ jobId }: { jobId: string }) {
  return (
    <div className="page-grid page-grid--detail">
      <Panel title="Loading Job" eyebrow={jobId}>
        <div className="asset-preview">
          <div>
            <Badge tone="muted">
              <StatusDot tone="pending" />
              Loading
            </Badge>
            <h2>Fetching job state</h2>
            <p>
              The page refreshes progress automatically until the job reaches a
              final state.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function AssetViewer({
  asset,
  imageResultAsset,
  i2vSourceAsset,
  i2vSourceError,
  i2vSourceLoading,
  job,
  onStartI2V,
}: {
  asset: AssetResponse | null;
  imageResultAsset: AssetResponse | null;
  i2vSourceAsset: AssetResponse | null;
  i2vSourceError: boolean;
  i2vSourceLoading: boolean;
  job: JobResponse;
  onStartI2V: (assetId: string) => void;
}) {
  if (job.state !== "completed") {
    if (job.mode === "i2v" && job.source_asset_id) {
      return (
        <I2VSourcePreview
          job={job}
          sourceAsset={i2vSourceAsset}
          sourceError={i2vSourceError}
          sourceLoading={i2vSourceLoading}
        />
      );
    }

    const failed = job.state === "failed";
    const cancelled = job.state === "cancelled";

    return (
      <div className="asset-preview">
        <div>
          <Badge tone={failed ? "danger" : cancelled ? "warning" : "muted"}>
            <StatusDot tone={failed ? "danger" : cancelled ? "warning" : "pending"} />
            {job.state}
          </Badge>
          <h2>
            {failed
              ? "Generation stopped before a result"
              : cancelled
                ? "Generation was cancelled"
                : "Result preview will appear here"}
          </h2>
          <p>
            {failed || cancelled
              ? "No completed asset is available for this job. Check the job state and error details for the cause."
              : "Once the result is saved, the completed image or video will render in this viewer."}
          </p>
        </div>
      </div>
    );
  }

  if (!asset) {
    return (
      <div className="asset-preview">
        <div>
          <Badge tone="warning">No asset returned</Badge>
          <h2>Job completed without a preview</h2>
          <p>
            The job reached completed, but the response did not include an asset
            to display. The request summary and state history remain available.
          </p>
        </div>
      </div>
    );
  }

  const isImage = asset.kind === "image" || asset.mime.startsWith("image/");
  const isVideo = asset.kind === "video" || asset.mime.startsWith("video/");
  const isPreviewable = isImage || isVideo;

  return (
    <div className="asset-viewer">
      <div className="asset-result-header">
        <Badge tone={isPreviewable ? "success" : "warning"}>
          {isVideo ? (
            <FilmIcon size={12} />
          ) : isImage ? (
            <ImageIcon size={12} />
          ) : (
            <StatusDot tone="warning" />
          )}
          {isVideo ? "Video result" : isImage ? "Image result" : "Asset returned"}
        </Badge>
        <div className="asset-result-header__copy">
          <h2>
            {isVideo
              ? "Video Result Ready"
              : isImage
                ? "Image Result Ready"
                : "Asset Returned"}
          </h2>
          <p>
            {isVideo
              ? "Playback controls are available below."
              : isImage
                ? "The generated image is ready below."
                : "This result is available, but this viewer can only preview image and video file types."}
          </p>
        </div>
      </div>

      <div className="asset-stage">
        {isImage && (
          <img
            alt={`Generated asset ${asset.id}`}
            className="asset-media"
            src={asset.url}
          />
        )}
        {isVideo && (
          <video className="asset-media" controls src={asset.url}>
            <a href={asset.url}>Open generated video</a>
          </video>
        )}
        {!isPreviewable && (
          <div className="asset-preview">
            <div>
              <Badge tone="warning">Preview unavailable</Badge>
              <h2>This file type cannot be previewed here</h2>
              <p>
                The asset was returned as {asset.mime}, which this viewer does not
                render inline. Metadata is still shown below.
              </p>
            </div>
          </div>
        )}
      </div>

      {isImage && imageResultAsset && (
        <div className="result-next-action">
          <div className="result-next-action__copy">
            <Badge tone="success">
              <PipelineIcon size={12} />
              Next action
            </Badge>
            <strong>Make a video with this image</strong>
            <p>
              Use this completed image as the locked source for a new
              image-to-video request.
            </p>
          </div>
          <Button
            onClick={() => onStartI2V(imageResultAsset.id)}
            type="button"
            variant="primary"
          >
            <PipelineIcon size={14} />
            Start I2V with this image
          </Button>
        </div>
      )}

      <div className="asset-metadata-panel">
        <div className="asset-metadata-panel__head">
          <div className="section-label">File details</div>
          <p>Preview details for the generated result.</p>
        </div>
        <div className="metadata-list asset-metadata">
          <div>
            <span>Type</span>
            <strong>{formatAssetType(asset)}</strong>
          </div>
          <div>
            <span>MIME</span>
            <strong>{asset.mime}</strong>
          </div>
          <div>
            <span>Size</span>
            <strong>{formatBytes(asset.size_bytes)}</strong>
          </div>
          <div>
            <span>Dimensions</span>
            <strong>{formatDimensions(asset)}</strong>
          </div>
          {asset.duration_sec !== null && (
            <div>
              <span>Duration</span>
              <strong>{asset.duration_sec}s</strong>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function I2VSourcePreview({
  job,
  sourceAsset,
  sourceError,
  sourceLoading,
}: {
  job: JobResponse;
  sourceAsset: AssetResponse | null;
  sourceError: boolean;
  sourceLoading: boolean;
}) {
  const failed = job.state === "failed";
  const cancelled = job.state === "cancelled";
  const tone = failed ? "danger" : cancelled ? "warning" : "info";
  const sourceIsImage =
    sourceAsset &&
    (sourceAsset.kind === "image" || sourceAsset.mime.startsWith("image/"));

  return (
    <div className="asset-viewer asset-viewer--source">
      <div className="asset-result-header">
        <Badge tone={tone}>
          <PipelineIcon size={12} />
          Source image context
        </Badge>
        <div className="asset-result-header__copy">
          <h2>{sourcePreviewTitle(job.state)}</h2>
          <p>
            This I2V job keeps the source image visible until the video result is
            available.
          </p>
        </div>
      </div>

      <div className="asset-stage asset-stage--source">
        {sourceLoading && (
          <div className="asset-preview">
            <div>
              <Badge tone="muted">
                <StatusDot tone="pending" />
                Loading source
              </Badge>
              <h2>Fetching source image</h2>
              <p>The locked image asset is being loaded for this I2V request.</p>
            </div>
          </div>
        )}
        {!sourceLoading && sourceIsImage && (
          <img
            alt={`Source asset ${sourceAsset.id}`}
            className="asset-media"
            src={sourceAsset.url}
          />
        )}
        {!sourceLoading && (!sourceIsImage || sourceError) && (
          <div className="asset-preview">
            <div>
              <Badge tone={sourceError ? "danger" : "warning"}>
                {sourceError ? "Source unavailable" : "Source pending"}
              </Badge>
              <h2>Source image preview unavailable</h2>
              <p>
                The job keeps source asset id {shortId(job.source_asset_id)} in
                metadata, but the image preview could not be loaded.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="asset-metadata-panel">
        <div className="asset-metadata-panel__head">
          <div className="section-label">I2V source</div>
          <p>Locked source context for this image-to-video request.</p>
        </div>
        <div className="metadata-list asset-metadata">
          <div>
            <span>Source asset</span>
            <strong>{shortId(job.source_asset_id)}</strong>
          </div>
          <div>
            <span>Current state</span>
            <strong>{job.state}</strong>
          </div>
          {sourceAsset && (
            <div>
              <span>Source type</span>
              <strong>{formatAssetType(sourceAsset)}</strong>
            </div>
          )}
          {sourceAsset && (
            <div>
              <span>Dimensions</span>
              <strong>{formatDimensions(sourceAsset)}</strong>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CurrentStepSummary({ job }: { job: JobResponse }) {
  const activeIndex = stateSteps.includes(job.state) ? stateSteps.indexOf(job.state) : 0;
  const progressPercent = Math.max(
    8,
    Math.round(((activeIndex + 1) / stateSteps.length) * 100),
  );
  const copy = stateCopy[job.state];

  return (
    <div className="job-progress-summary">
      <div className="job-progress-summary__top">
        <Badge tone="info">
          <StatusDot tone="info" />
          Current step
        </Badge>
        <span>
          Step {activeIndex + 1} of {stateSteps.length}
        </span>
      </div>
      <strong>{copy.label}</strong>
      <p>{copy.detail}</p>
      <div aria-hidden="true" className="job-progress-bar">
        <span style={{ width: `${progressPercent}%` }} />
      </div>
    </div>
  );
}

function JobStateTimeline({
  history,
  state,
}: {
  history: StateHistoryEntry[];
  state: JobState;
}) {
  const activeIndex = stateSteps.includes(state) ? stateSteps.indexOf(state) : -1;

  return (
    <div className="timeline">
      {stateSteps.map((step, index) => {
        const historyEntry = history.find((entry) => entry.state === step);
        const done = activeIndex >= 0 && index < activeIndex;
        const active = step === state;
        const marker = formatTimelineMarker({ active, done, state, step });
        return (
          <div
            className={`timeline-item${active ? " timeline-item--active" : ""}${
              done ? " timeline-item--done" : ""
            }${!active && !done ? " timeline-item--waiting" : ""}`}
            key={step}
          >
            <StatusDot tone={active ? "info" : done ? "success" : "muted"} />
            <div className="timeline-item__body">
              <span>{stateCopy[step].label}</span>
              <p>{stateCopy[step].timeline}</p>
            </div>
            <small>
              {historyEntry ? `${marker} · ${formatDateTime(historyEntry.at)}` : marker}
            </small>
          </div>
        );
      })}
      {(state === "failed" || state === "cancelled") && (
        <div className="timeline-item timeline-item--active timeline-item--terminal">
          <StatusDot tone={state === "failed" ? "danger" : "warning"} />
          <div className="timeline-item__body">
            <span>{stateCopy[state].label}</span>
            <p>{stateCopy[state].timeline}</p>
          </div>
          <small>terminal</small>
        </div>
      )}
    </div>
  );
}

function JobWaitingContext({ job }: { job: JobResponse }) {
  const terminal = isTerminalJobState(job.state);

  return (
    <div className="job-context-grid" aria-label="Job progress context">
      <div className="job-context-card">
        <span>Current state</span>
        <strong>{stateCopy[job.state].summary}</strong>
        <small>{terminal ? "Final state reached." : "Updates continue while work is active."}</small>
      </div>
      <div className="job-context-card">
        <span>Run attempts</span>
        <strong>{job.attempts}</strong>
        <small>Retries appear here if the request needs another attempt.</small>
      </div>
    </div>
  );
}

function RequestSummary({ job }: { job: JobResponse }) {
  return (
    <div className="request-summary">
      <div className="metadata-list">
        <div>
          <span>Mode</span>
          <strong>{job.mode}</strong>
        </div>
        <div>
          <span>Model</span>
          <strong>{job.model}</strong>
        </div>
        <div>
          <span>Created</span>
          <strong>{formatDateTime(job.created_at)}</strong>
        </div>
        <div>
          <span>Updated</span>
          <strong>{formatDateTime(job.updated_at)}</strong>
        </div>
        {job.enhancement_id && (
          <div>
            <span>Prompt enhancement</span>
            <strong>Applied</strong>
          </div>
        )}
        {job.source_asset_id && (
          <div>
            <span>Source image</span>
            <strong>Connected</strong>
          </div>
        )}
      </div>

      <div className="prompt-detail">
        <Badge tone="muted">
          <FilmIcon size={12} />
          Prompt
        </Badge>
        <p>{job.prompt}</p>
      </div>

      {job.enhanced_prompt && (
        <div className="prompt-detail">
          <Badge tone="info">
            <ImageIcon size={12} />
            Enhanced prompt
          </Badge>
          <p>{job.enhanced_prompt}</p>
        </div>
      )}

      <div className="prompt-detail">
        <Badge tone="muted">Parameters</Badge>
        <pre>{JSON.stringify(job.parameters, null, 2)}</pre>
      </div>
    </div>
  );
}

function formatTimelineMarker({
  active,
  done,
  state,
  step,
}: {
  active: boolean;
  done: boolean;
  state: JobState;
  step: JobState;
}): string {
  if (active && state === "completed") {
    return "complete";
  }
  if (active && step === state) {
    return "current";
  }
  if (done) {
    return "complete";
  }
  return "waiting";
}

function findCompletedImageAsset(job: JobResponse | undefined): AssetResponse | null {
  if (!job || job.state !== "completed") {
    return null;
  }

  return (
    job.assets.find((asset) => asset.kind === "image" || asset.mime.startsWith("image/")) ??
    null
  );
}

function getI2VSourcePreviewAssetId(job: JobResponse | undefined): string | null {
  if (!job || job.mode !== "i2v" || !job.source_asset_id || job.state === "completed") {
    return null;
  }
  return job.source_asset_id;
}

function sourcePreviewTitle(state: JobState): string {
  if (state === "failed") {
    return "I2V stopped before a video result";
  }
  if (state === "cancelled") {
    return "I2V was cancelled";
  }
  return "I2V source image is locked";
}

function shortId(value: string | null): string {
  return value ? value.slice(0, 8) : "unknown";
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

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatAssetType(asset: AssetResponse): string {
  if (asset.kind === "image") {
    return "Image";
  }
  if (asset.kind === "video") {
    return "Video";
  }
  return asset.kind;
}

function formatDimensions(asset: AssetResponse): string {
  if (asset.width && asset.height) {
    return `${asset.width} x ${asset.height}`;
  }
  return "unknown";
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
