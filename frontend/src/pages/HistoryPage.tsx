import { type KeyboardEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  deleteGeneration,
  listGenerations,
  type AssetKind,
  type AssetResponse,
  type GenerationListParams,
  type GenerationMode,
  type GenerationResponse,
  type JobState,
} from "../api/client";
import { Badge, Button, Panel, StatusDot } from "../components/ui";
import { FilmIcon, HistoryIcon, ImageIcon, PipelineIcon } from "../components/icons";

const modeOptions: Array<GenerationMode | "all"> = ["all", "t2i", "t2v", "i2v"];
const assetKindOptions: Array<AssetKind | "all"> = ["all", "image", "video"];
const stateOptions: Array<JobState | "all"> = [
  "all",
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
const limitOptions = [10, 20, 50, 100];

export function HistoryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<GenerationMode | "all">("all");
  const [assetKind, setAssetKind] = useState<AssetKind | "all">("all");
  const [state, setState] = useState<JobState | "all">("all");
  const [model, setModel] = useState("");
  const [limit, setLimit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);

  const queryParams: GenerationListParams = {
    ...(mode === "all" ? {} : { mode }),
    ...(assetKind === "all" ? {} : { asset_kind: assetKind }),
    ...(state === "all" ? {} : { state }),
    ...(model.trim() ? { model: model.trim() } : {}),
    limit,
    offset,
  };

  const generations = useQuery({
    queryKey: ["generations", queryParams],
    queryFn: () => listGenerations(queryParams),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteGeneration,
    onMutate: (jobId) => {
      setDeletingJobId(jobId);
      setDeleteError(null);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["generations"] });
    },
    onError: (error) => {
      setDeleteError(error instanceof Error ? error.message : "Delete failed.");
    },
    onSettled: () => {
      setDeletingJobId(null);
    },
  });

  const jobs = generations.data ?? [];
  const canGoBack = offset > 0;
  const canGoNext = jobs.length === limit;
  const visibleStart = jobs.length > 0 ? offset + 1 : 0;
  const visibleEnd = offset + jobs.length;
  const currentPage = Math.floor(offset / limit) + 1;
  const activeFilterCount =
    (mode === "all" ? 0 : 1) +
    (assetKind === "all" ? 0 : 1) +
    (state === "all" ? 0 : 1) +
    (model.trim() ? 1 : 0);

  function resetOffset() {
    setOffset(0);
  }

  function handleRowKeyDown(event: KeyboardEvent<HTMLDivElement>, jobId: string) {
    if (event.target !== event.currentTarget) {
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      navigate(`/jobs/${jobId}`);
    }
  }

  function requestDelete(job: GenerationResponse) {
    const confirmed = window.confirm(
      `Delete only job ${shortJobId(job.id)} and its saved asset files? Related parent or child jobs will stay in History. This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    deleteMutation.mutate(job.id);
  }

  return (
    <div className="page-stack">
      <Panel title="History Filters" eyebrow="Saved generations">
        <p className="panel-copy">
          Browse submitted generation jobs by mode, state, model, and page size.
          Selecting a row opens the full job detail view.
        </p>

        <div className="history-filter-grid">
          <label>
            <span>Mode</span>
            <select
              onChange={(event) => {
                setMode(event.target.value as GenerationMode | "all");
                resetOffset();
              }}
              value={mode}
            >
              {modeOptions.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "All modes" : option.toUpperCase()}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Asset type</span>
            <select
              onChange={(event) => {
                setAssetKind(event.target.value as AssetKind | "all");
                resetOffset();
              }}
              value={assetKind}
            >
              {assetKindOptions.map((option) => (
                <option key={option} value={option}>
                  {assetKindLabel(option)}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>State</span>
            <select
              onChange={(event) => {
                setState(event.target.value as JobState | "all");
                resetOffset();
              }}
              value={state}
            >
              {stateOptions.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "All states" : option}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Model</span>
            <input
              onChange={(event) => {
                setModel(event.target.value);
                resetOffset();
              }}
              placeholder="Filter by model"
              value={model}
            />
            <span className="field-hint">Leave blank to include every model.</span>
          </label>

          <label>
            <span>Page size</span>
            <select
              onChange={(event) => {
                setLimit(Number(event.target.value));
                resetOffset();
              }}
              value={limit}
            >
              {limitOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <span className="field-hint">Results per page.</span>
          </label>
        </div>

        <div className="history-query-summary">
          <Badge tone="info">
            <HistoryIcon size={12} />
            {activeFilterCount === 0
              ? "All generations"
              : `${activeFilterCount} active filter${activeFilterCount === 1 ? "" : "s"}`}
          </Badge>
          <Badge tone="muted">Page {currentPage}</Badge>
          <Badge tone="muted">{limit} per page</Badge>
          {mode !== "all" && <Badge tone="muted">mode {mode}</Badge>}
          {assetKind !== "all" && <Badge tone="muted">asset {assetKind}</Badge>}
          {state !== "all" && <Badge tone="muted">state {state}</Badge>}
          {model.trim() && <Badge tone="muted">model {model.trim()}</Badge>}
        </div>
      </Panel>

      <Panel className="history-table-shell" title="Generation History" eyebrow="Saved jobs">
        <div className="history-table-intro">
          <div>
            <div className="section-label">Current view</div>
            <p>{formatHistorySummary({ assetKind, jobsLength: jobs.length, mode, state })}</p>
          </div>
          {generations.isFetching && !generations.isLoading && (
            <Badge tone="info">
              <StatusDot tone="info" />
              Refreshing
            </Badge>
          )}
        </div>
        {deleteError && (
          <div className="history-delete-alert" role="alert">
            <Badge tone="danger">
              <StatusDot tone="danger" />
              Delete failed
            </Badge>
            <p>{deleteError}</p>
          </div>
        )}

        {generations.isLoading && (
          <HistoryMessage
            label="Loading"
            title="Loading generation history"
            message="Fetching the current page of saved jobs."
          />
        )}
        {generations.isError && (
          <HistoryMessage
            label="Request failed"
            title="Unable to load history"
            tone="danger"
            message={
              generations.error instanceof Error
                ? generations.error.message
                : "Request failed."
            }
          />
        )}
        {!generations.isLoading && !generations.isError && jobs.length === 0 && (
          <HistoryMessage
            title="No generations found"
            label="Empty result"
            message="No jobs match this query. Adjust the filters or create a generation from the Generate workspace."
          />
        )}
        {!generations.isLoading && !generations.isError && jobs.length > 0 && (
          <div className="table-shell">
            <div className="table-row table-row--head history-row-grid">
              <span>Result</span>
              <span>Mode / state</span>
              <span>Prompt / job</span>
              <span>Model</span>
              <span>Created</span>
              <span>Actions</span>
            </div>
            {jobs.map((job) => (
              <div
                className="table-row history-row history-row-grid"
                key={job.id}
                onClick={() => navigate(`/jobs/${job.id}`)}
                onKeyDown={(event) => handleRowKeyDown(event, job.id)}
                role="button"
                tabIndex={0}
              >
                <ResultPreview job={job} />
                <span className="history-mode-state">
                  <ModeBadge mode={job.mode} />
                  <StateBadge state={job.state} />
                </span>
                <span className="history-prompt">
                  <strong>{summarizePrompt(job.prompt)}</strong>
                  <small title={job.id}>Job {shortJobId(job.id)}</small>
                </span>
                <span className="history-model" title={job.model}>
                  <small>Model</small>
                  <strong>{job.model}</strong>
                </span>
                <span className="history-created">
                  <small>Created</small>
                  <strong>{formatDateTime(job.created_at)}</strong>
                </span>
                <span className="history-actions">
                  {canDeleteHistoryJob(job) ? (
                    <Button
                      className="history-delete-button"
                      disabled={deleteMutation.isPending}
                      onClick={(event) => {
                        event.stopPropagation();
                        requestDelete(job);
                      }}
                      type="button"
                      variant="ghost"
                    >
                      {deletingJobId === job.id ? "Deleting" : "Delete"}
                    </Button>
                  ) : (
                    <span className="history-actions__empty">-</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <div className="pagination-row">
        <Button
          disabled={!canGoBack || generations.isFetching}
          onClick={() => setOffset(Math.max(0, offset - limit))}
          type="button"
          variant="secondary"
        >
          Previous
        </Button>
        <span>
          {jobs.length > 0
            ? `Showing ${visibleStart}-${visibleEnd} · ${jobs.length} loaded`
            : "No rows on this page"}
        </span>
        <Button
          disabled={!canGoNext || generations.isFetching}
          onClick={() => setOffset(offset + limit)}
          type="button"
          variant="secondary"
        >
          Next
        </Button>
      </div>
    </div>
  );
}

function HistoryMessage({
  label,
  message,
  title,
  tone = "muted",
}: {
  label?: string;
  message?: string;
  title: string;
  tone?: "muted" | "danger";
}) {
  return (
    <div className="history-message">
      <Badge tone={tone}>
        <StatusDot tone={tone} />
        {label ?? title}
      </Badge>
      <h2>{title}</h2>
      {message && <p>{message}</p>}
    </div>
  );
}

function ModeBadge({ mode }: { mode: GenerationMode }) {
  const Icon = mode === "t2i" ? ImageIcon : mode === "t2v" ? FilmIcon : PipelineIcon;
  return (
    <Badge tone={mode === "i2v" ? "warning" : "info"}>
      <Icon size={12} />
      {mode.toUpperCase()}
    </Badge>
  );
}

function StateBadge({ state }: { state: JobState }) {
  const tone = stateTone(state);
  return (
    <Badge tone={tone}>
      <StatusDot tone={tone} />
      {state}
    </Badge>
  );
}

function ResultPreview({ job }: { job: GenerationResponse }) {
  const asset = job.assets[0] ?? null;
  if (!asset) {
    const copy = emptyResultCopy(job.state);
    return (
      <span className="history-result-thumb history-result-thumb--empty" title={copy.title}>
        <strong>{copy.label}</strong>
        <small>{copy.detail}</small>
      </span>
    );
  }

  const label = `${asset.kind} · ${asset.mime}`;
  if (asset.kind === "image" || asset.mime.startsWith("image/")) {
    return (
      <span className="history-result-thumb history-result-thumb--image" title={label}>
        <img alt="" src={asset.url} />
        <small>Image</small>
      </span>
    );
  }

  if (asset.kind === "video" || asset.mime.startsWith("video/")) {
    return <VideoResultPreview asset={asset} label={label} />;
  }

  return (
    <span
      className="history-result-thumb history-result-thumb--unavailable"
      title={`Preview unavailable · ${label}`}
    >
      <strong>Preview</strong>
      <small>Unavailable</small>
    </span>
  );
}

function VideoResultPreview({ asset, label }: { asset: AssetResponse; label: string }) {
  const [hasPreviewError, setHasPreviewError] = useState(false);

  return (
    <span
      className="history-result-thumb history-result-thumb--video"
      title={hasPreviewError ? `Video ready · thumbnail unavailable · ${label}` : label}
    >
      {hasPreviewError ? (
        <>
          <span className="history-video-tile__icon">
            <FilmIcon size={15} />
          </span>
          <strong>Video ready</strong>
        </>
      ) : (
        <video
          aria-label="Video preview"
          muted
          onError={() => setHasPreviewError(true)}
          playsInline
          preload="metadata"
          src={videoPreviewUrl(asset.url)}
        />
      )}
      <small>{hasPreviewError ? "No thumbnail" : "Video"}</small>
    </span>
  );
}

function stateTone(state: JobState): "info" | "success" | "warning" | "danger" | "muted" {
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
    return "warning";
  }
  if (state === "generating" || state === "polling" || state === "downloading") {
    return "info";
  }
  return "muted";
}

function summarizePrompt(prompt: string): string {
  const trimmed = prompt.trim();
  if (trimmed.length <= 110) {
    return trimmed;
  }
  return `${trimmed.slice(0, 107).trimEnd()}...`;
}

function emptyResultCopy(state: JobState): {
  detail: string;
  label: string;
  title: string;
} {
  if (state === "completed") {
    return {
      detail: "completed",
      label: "No asset",
      title: "Completed job returned no asset preview.",
    };
  }
  if (state === "failed") {
    return {
      detail: "failed",
      label: "No result",
      title: "Failed jobs do not have a completed asset.",
    };
  }
  if (state === "cancelled") {
    return {
      detail: "cancelled",
      label: "Stopped",
      title: "Cancelled jobs do not have a completed asset.",
    };
  }
  return {
    detail: "in progress",
    label: "Pending",
    title: "Asset preview will appear after completion.",
  };
}

function formatHistorySummary({
  assetKind,
  jobsLength,
  mode,
  state,
}: {
  assetKind: AssetKind | "all";
  jobsLength: number;
  mode: GenerationMode | "all";
  state: JobState | "all";
}): string {
  const modeText = mode === "all" ? "all modes" : mode.toUpperCase();
  const stateText = state === "all" ? "all states" : state;
  const assetText = assetKind === "all" ? "all result types" : `${assetKind} assets`;
  return `${jobsLength} job${jobsLength === 1 ? "" : "s"} shown for ${modeText}, ${stateText}, and ${assetText}.`;
}

function shortJobId(id: string): string {
  return id.slice(0, 8);
}

function assetKindLabel(option: AssetKind | "all"): string {
  if (option === "all") {
    return "All result types";
  }
  return option === "image" ? "Images" : "Videos";
}

function canDeleteHistoryJob(job: GenerationResponse): boolean {
  return job.state === "completed" || job.state === "failed" || job.state === "cancelled";
}

function videoPreviewUrl(url: string): string {
  return url.includes("#") ? url : `${url}#t=0.1`;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
