import { type KeyboardEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  deleteGeneration,
  listGenerations,
  retryGeneration,
  type AssetKind,
  type AssetResponse,
  type GenerationListParams,
  type GenerationMode,
  type GenerationResponse,
  type JobState,
} from "../api/client";
import { Badge, Button, Panel, StatusDot } from "../components/ui";
import { FilmIcon, HistoryIcon, ImageIcon, PipelineIcon, RetryIcon } from "../components/icons";
import { MODE_COPY } from "../ui/copy";
import {
  formatAssetKind,
  formatDateTime,
  formatGenerationMode,
  formatJobState,
  shortId,
  toJobSummaryViewModel,
} from "../ui/viewModels";
import { hasRepairSignal } from "../utils/repair";

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
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);

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
      setDeleteError(error instanceof Error ? error.message : "삭제에 실패했습니다.");
    },
    onSettled: () => {
      setDeletingJobId(null);
    },
  });

  const retryMutation = useMutation({
    mutationFn: retryGeneration,
    onMutate: (jobId) => {
      setRetryingJobId(jobId);
      setRetryError(null);
    },
    onSuccess: async (newJob) => {
      queryClient.setQueryData(["job", newJob.id], newJob);
      await queryClient.invalidateQueries({ queryKey: ["generations"] });
      navigate(`/jobs/${newJob.id}`);
    },
    onError: (error) => {
      setRetryError(error instanceof Error ? error.message : "재시도에 실패했습니다.");
    },
    onSettled: () => {
      setRetryingJobId(null);
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
      `작업 ${shortId(job.id)}와 저장된 결과 파일만 삭제할까요? 연결된 상위/하위 작업은 기록에 남습니다. 이 작업은 되돌릴 수 없습니다.`,
    );
    if (!confirmed) {
      return;
    }
    deleteMutation.mutate(job.id);
  }

  return (
    <div className="creative-page creative-page--history">
      <section className="creative-page-hero">
        <div className="creative-page-hero__copy">
          <Badge tone="info">
            <HistoryIcon size={12} />
            Library
          </Badge>
          <h1>생성 기록</h1>
          <p>
            완료, 실패, 진행 중인 작업을 빠르게 스캔하고 결과 미리보기에서 상세 화면으로
            이어집니다.
          </p>
        </div>
        <div className="creative-page-hero__metrics" aria-label="기록 요약">
          <div className="creative-metric">
            <span>현재 보기</span>
            <strong>{jobs.length}</strong>
          </div>
          <div className="creative-metric">
            <span>필터</span>
            <strong>{activeFilterCount}</strong>
          </div>
          <div className="creative-metric">
            <span>페이지</span>
            <strong>{currentPage}</strong>
          </div>
        </div>
      </section>

      <Panel className="creative-panel history-filter-panel" title="기록 필터" eyebrow="저장된 생성">
        <p className="panel-copy">
          제출한 생성 작업을 모드, 상태, 모델, 페이지 크기로 살펴봅니다.
          행을 선택하면 전체 작업 상세 화면이 열립니다.
        </p>

        <div className="history-filter-grid">
          <label>
            <span>모드</span>
            <select
              onChange={(event) => {
                setMode(event.target.value as GenerationMode | "all");
                resetOffset();
              }}
              value={mode}
            >
              {modeOptions.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "전체 모드" : formatGenerationMode(option)}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>결과 유형</span>
            <select
              onChange={(event) => {
                setAssetKind(event.target.value as AssetKind | "all");
                resetOffset();
              }}
              value={assetKind}
            >
              {assetKindOptions.map((option) => (
                <option key={option} value={option}>
                  {formatAssetKind(option)}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>상태</span>
            <select
              onChange={(event) => {
                setState(event.target.value as JobState | "all");
                resetOffset();
              }}
              value={state}
            >
              {stateOptions.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "전체 상태" : formatJobState(option)}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>모델</span>
            <input
              onChange={(event) => {
                setModel(event.target.value);
                resetOffset();
              }}
              placeholder="모델로 필터링"
              value={model}
            />
            <span className="field-hint">비워두면 모든 모델을 포함합니다.</span>
          </label>

          <label>
            <span>페이지 크기</span>
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
            <span className="field-hint">페이지당 결과 수입니다.</span>
          </label>
        </div>

        <div className="history-query-summary">
          <Badge tone="info">
            <HistoryIcon size={12} />
            {activeFilterCount === 0
              ? "전체 생성"
              : `활성 필터 ${activeFilterCount}개`}
          </Badge>
          <Badge tone="muted">{currentPage}페이지</Badge>
          <Badge tone="muted">페이지당 {limit}개</Badge>
          {mode !== "all" && <Badge tone="muted">모드 {formatGenerationMode(mode)}</Badge>}
          {assetKind !== "all" && <Badge tone="muted">결과 {formatAssetKind(assetKind)}</Badge>}
          {state !== "all" && <Badge tone="muted">상태 {formatJobState(state)}</Badge>}
          {model.trim() && <Badge tone="muted">모델 {model.trim()}</Badge>}
        </div>
      </Panel>

      <Panel className="creative-panel history-table-shell" title="생성 기록" eyebrow="저장된 작업">
        <div className="history-table-intro">
          <div>
            <div className="section-label">현재 보기</div>
            <p>{formatHistorySummary({ assetKind, jobsLength: jobs.length, mode, state })}</p>
          </div>
          {generations.isFetching && !generations.isLoading && (
            <Badge tone="info">
              <StatusDot tone="info" />
              새로고침 중
            </Badge>
          )}
        </div>
        {deleteError && (
          <div className="history-delete-alert" role="alert">
            <Badge tone="danger">
              <StatusDot tone="danger" />
              삭제 실패
            </Badge>
            <p>{deleteError}</p>
          </div>
        )}
        {retryError && (
          <div className="history-delete-alert" role="alert">
            <Badge tone="danger">
              <StatusDot tone="danger" />
              재시도 실패
            </Badge>
            <p>{retryError}</p>
          </div>
        )}

        {generations.isLoading && (
          <HistoryMessage
            label="로딩 중"
            title="생성 기록을 불러오는 중"
            message="저장된 작업의 현재 페이지를 가져오고 있습니다."
          />
        )}
        {generations.isError && (
          <HistoryMessage
            label="요청 실패"
            title="기록을 불러올 수 없습니다"
            tone="danger"
            message={
              generations.error instanceof Error
                ? generations.error.message
                : "요청에 실패했습니다."
            }
          />
        )}
        {!generations.isLoading && !generations.isError && jobs.length === 0 && (
          <HistoryMessage
            title="생성 기록이 없습니다"
            label="결과 없음"
            message="이 조건과 일치하는 작업이 없습니다. 필터를 조정하거나 생성 작업공간에서 새 작업을 만드세요."
          />
        )}
        {!generations.isLoading && !generations.isError && jobs.length > 0 && (
          <div className="table-shell">
            <div className="table-row table-row--head history-row-grid">
              <span>결과</span>
              <span>모드 / 상태</span>
              <span>프롬프트 / 작업</span>
              <span>모델</span>
              <span>생성일</span>
              <span>작업</span>
            </div>
            {jobs.map((job) => {
              const jobView = toJobSummaryViewModel(job);
              const repairRequired = hasRepairSignal(job);

              return (
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
                    <ModeBadge mode={jobView.mode} />
                    <StateBadge state={jobView.state} />
                  </span>
                  <span className="history-prompt">
                    <strong>{summarizePrompt(jobView.prompt)}</strong>
                    <small title={jobView.id}>작업 {jobView.shortId}</small>
                    {job.retry_of_job_id && (
                      <span className="history-retry-badge" title={job.retry_of_job_id}>
                        재시도 원본 {shortId(job.retry_of_job_id)}
                      </span>
                    )}
                    {repairRequired && (
                      <span className="history-repair-badge">수동 복구 필요</span>
                    )}
                  </span>
                  <span className="history-model" title={job.model}>
                    <small>모델</small>
                    <strong>{job.model}</strong>
                  </span>
                  <span className="history-created">
                    <small>생성일</small>
                    <strong>{jobView.createdAt}</strong>
                  </span>
                  <span className="history-actions">
                    {jobView.canRetry && job.state === "failed" && (
                      <Button
                        className="history-retry-button"
                        disabled={retryMutation.isPending}
                        onClick={(event) => {
                          event.stopPropagation();
                          retryMutation.mutate(job.id);
                        }}
                        type="button"
                        variant="ghost"
                      >
                        <RetryIcon size={13} />
                        {retryingJobId === job.id
                          ? "재시도 중"
                          : repairRequired
                            ? "복구 재시도"
                            : "재시도"}
                      </Button>
                    )}
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
                        {deletingJobId === job.id ? "삭제 중" : "삭제"}
                      </Button>
                    ) : (
                      <span className="history-actions__empty">-</span>
                    )}
                  </span>
                </div>
              );
            })}
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
          이전
        </Button>
        <span>
          {jobs.length > 0
            ? `${visibleStart}-${visibleEnd} 표시 · ${jobs.length}개 로드됨`
            : "이 페이지에 행이 없습니다"}
        </span>
        <Button
          disabled={!canGoNext || generations.isFetching}
          onClick={() => setOffset(offset + limit)}
          type="button"
          variant="secondary"
        >
          다음
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
      {MODE_COPY[mode].short}
    </Badge>
  );
}

function StateBadge({ state }: { state: JobState }) {
  const tone = stateTone(state);
  return (
    <Badge tone={tone}>
      <StatusDot tone={tone} />
      {formatJobState(state)}
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

  const label = `${formatAssetKind(asset.kind)} · ${asset.mime}`;
  if (asset.kind === "image" || asset.mime.startsWith("image/")) {
    return (
      <span className="history-result-thumb history-result-thumb--image" title={label}>
        <img alt="" src={asset.url} />
        <small>이미지</small>
      </span>
    );
  }

  if (asset.kind === "video" || asset.mime.startsWith("video/")) {
    return <VideoResultPreview asset={asset} label={label} />;
  }

  return (
    <span
      className="history-result-thumb history-result-thumb--unavailable"
      title={`미리보기 불가 · ${label}`}
    >
      <strong>미리보기</strong>
      <small>불가</small>
    </span>
  );
}

function VideoResultPreview({ asset, label }: { asset: AssetResponse; label: string }) {
  const [hasPreviewError, setHasPreviewError] = useState(false);

  return (
    <span
      className="history-result-thumb history-result-thumb--video"
      title={hasPreviewError ? `영상 준비됨 · 썸네일 불가 · ${label}` : label}
    >
      {hasPreviewError ? (
        <>
          <span className="history-video-tile__icon">
            <FilmIcon size={15} />
          </span>
          <strong>영상 준비됨</strong>
        </>
      ) : (
        <video
          aria-label="영상 preview"
          muted
          onError={() => setHasPreviewError(true)}
          playsInline
          preload="metadata"
          src={videoPreviewUrl(asset.url)}
        />
      )}
      <small>{hasPreviewError ? "썸네일 없음" : "영상"}</small>
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
      detail: "완료됨",
      label: "결과 없음",
      title: "완료된 작업이 결과 미리보기를 반환하지 않았습니다.",
    };
  }
  if (state === "failed") {
    return {
      detail: "실패",
      label: "결과 없음",
      title: "실패한 작업에는 완료된 asset이 없습니다.",
    };
  }
  if (state === "cancelled") {
    return {
      detail: "취소됨",
      label: "중단됨",
      title: "취소된 작업에는 완료된 asset이 없습니다.",
    };
  }
  return {
    detail: "진행 중",
    label: "대기 중",
    title: "완료 후 결과 미리보기가 표시됩니다.",
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
  const modeText = mode === "all" ? "전체 모드" : formatGenerationMode(mode);
  const stateText = state === "all" ? "전체 상태" : formatJobState(state);
  const assetText =
    assetKind === "all" ? "전체 결과 유형" : `${formatAssetKind(assetKind)} 결과`;
  return `${modeText}, ${stateText}, ${assetText} 조건으로 ${jobsLength}개 작업이 표시됩니다.`;
}

function canDeleteHistoryJob(job: GenerationResponse): boolean {
  return job.state === "completed" || job.state === "failed" || job.state === "cancelled";
}

function videoPreviewUrl(url: string): string {
  return url.includes("#") ? url : `${url}#t=0.1`;
}
