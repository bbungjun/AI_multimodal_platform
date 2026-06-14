import type {
  AssetResponse,
  GenerationMode,
  JobResponse,
  JobState,
  PipelineResponse,
} from "../api/client";
import { ASSET_KIND_COPY, JOB_STATE_COPY, MODE_COPY } from "./copy";

export type AssetPreviewViewModel = {
  id: string;
  kind: AssetResponse["kind"];
  url: string;
  label: string;
  meta: string;
};

export type JobSummaryViewModel = {
  id: string;
  shortId: string;
  mode: GenerationMode;
  modeLabel: string;
  state: JobState;
  stateLabel: string;
  prompt: string;
  createdAt: string;
  updatedAt: string;
  assets: AssetPreviewViewModel[];
  isTerminal: boolean;
  canRetry: boolean;
  canUseAsI2V: boolean;
};

export type PipelineViewModel = {
  id: string;
  parent: JobSummaryViewModel;
  child: JobSummaryViewModel;
};

export function toAssetPreviewViewModel(asset: AssetResponse): AssetPreviewViewModel {
  const dimensions =
    asset.width && asset.height
      ? `${asset.width} x ${asset.height}`
      : asset.duration_sec
        ? `${asset.duration_sec}s`
        : "메타데이터 대기 중";

  return {
    id: asset.id,
    kind: asset.kind,
    url: asset.url,
    label: asset.kind === "image" ? "이미지 결과" : "영상 결과",
    meta: `${asset.mime} · ${dimensions}`,
  };
}

export function toJobSummaryViewModel(job: JobResponse): JobSummaryViewModel {
  return {
    id: job.id,
    shortId: shortId(job.id),
    mode: job.mode,
    modeLabel: MODE_COPY[job.mode].title,
    state: job.state,
    stateLabel: JOB_STATE_COPY[job.state],
    prompt: job.prompt,
    createdAt: formatDateTime(job.created_at),
    updatedAt: formatDateTime(job.updated_at),
    assets: job.assets.map(toAssetPreviewViewModel),
    isTerminal: isTerminalJobState(job.state),
    canRetry: job.state === "failed" || job.state === "cancelled",
    canUseAsI2V:
      job.mode === "t2i" &&
      job.assets.some((asset) => asset.kind === "image" || asset.mime.startsWith("image/")),
  };
}

export function toPipelineViewModel(pipeline: PipelineResponse): PipelineViewModel {
  return {
    id: pipeline.id,
    parent: toJobSummaryViewModel(pipeline.parent),
    child: toJobSummaryViewModel(pipeline.child),
  };
}

export function formatAssetKind(kind: AssetResponse["kind"] | "all"): string {
  return ASSET_KIND_COPY[kind];
}

export function formatJobState(state: JobState): string {
  return JOB_STATE_COPY[state];
}

export function formatGenerationMode(mode: GenerationMode): string {
  return MODE_COPY[mode].title;
}

export function isTerminalJobState(state: JobState): boolean {
  return state === "completed" || state === "failed" || state === "cancelled";
}

export function shortId(value: string | null | undefined): string {
  if (!value) {
    return "알 수 없음";
  }
  return value.length > 12 ? value.slice(0, 8) : value;
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
