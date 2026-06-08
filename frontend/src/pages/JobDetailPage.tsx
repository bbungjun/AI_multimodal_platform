import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import {
  retryGeneration,
  type AssetResponse,
  type JobResponse,
  type JobState,
  type StateHistoryEntry,
} from "../api/client";
import { Badge, Button, Panel, RoutePlaceholder, StatusDot } from "../components/ui";
import { FilmIcon, ImageIcon, PipelineIcon, RetryIcon } from "../components/icons";
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
    label: "요청 준비 중",
    summary: "작업이 접수되어 runner 처리를 기다리고 있습니다.",
    detail:
      "요청이 저장되었고 다음 생성 슬롯을 기다리고 있습니다.",
    timeline: "요청이 저장되어 처리 준비가 끝났습니다.",
  },
  enhancing: {
    label: "프롬프트 향상 중",
    summary: "Gemini가 생성에 사용할 프롬프트를 준비하고 있습니다.",
    detail:
      "이미지 또는 영상 모델 호출 전에 프롬프트 향상이 실행 중입니다.",
    timeline: "프롬프트 향상 단계가 진행 중입니다.",
  },
  queued: {
    label: "생성 슬롯 대기 중",
    summary: "현재 모델 처리 용량 때문에 작업이 대기열에 있습니다.",
    detail:
      "Runner가 Vertex AI로 요청을 보내기 전 사용 가능한 슬롯을 기다리고 있습니다.",
    timeline: "모델 용량이 생길 때까지 대기합니다.",
  },
  generating: {
    label: "Vertex AI에서 생성 중",
    summary: "모델 요청이 실행 중입니다.",
    detail:
      "Imagen 또는 Veo가 결과를 생성하고 있습니다. 보통 이 단계가 가장 오래 걸립니다.",
    timeline: "모델 생성이 진행 중입니다.",
  },
  polling: {
    label: "모델 결과 확인 중",
    summary: "서비스가 완료된 결과를 확인하고 있습니다.",
    detail:
      "오래 걸리는 이미지/영상 작업일 수 있어 결과가 준비되는 동안 이 페이지가 자동으로 새로고침됩니다.",
    timeline: "결과가 준비되고 있습니다.",
  },
  downloading: {
    label: "결과 저장 중",
    summary: "생성된 결과를 로컬 저장소에 쓰고 있습니다.",
    detail:
      "모델이 데이터를 반환했고, 이 화면에서 preview할 수 있도록 결과를 저장하고 있습니다.",
    timeline: "생성 결과를 저장하고 있습니다.",
  },
  completed: {
    label: "완료",
    summary: "작업이 성공적으로 최종 상태에 도달했습니다.",
    detail: "반환된 asset이 있으면 Asset Viewer에서 확인할 수 있습니다.",
    timeline: "결과가 준비되었습니다.",
  },
  failed: {
    label: "실패",
    summary: "작업이 오류로 중단되었습니다.",
    detail: "요청이 오류를 반환했습니다.",
    timeline: "최종 실패 상태입니다.",
  },
  cancelled: {
    label: "취소됨",
    summary: "작업이 완료 전에 취소되었습니다.",
    detail: "이 작업에는 더 이상 생성 처리가 실행되지 않습니다.",
    timeline: "최종 취소 상태입니다.",
  },
};

export function JobDetailPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [retryError, setRetryError] = useState<string | null>(null);
  const jobQuery = useJob(jobId);
  const job = jobQuery.data;
  const primaryAsset = job?.assets[0] ?? null;
  const imageResultAssets = useMemo(() => findCompletedImageAssets(job), [job]);
  const i2vSourceAssetId = getI2VSourcePreviewAssetId(job);
  const i2vSourceQuery = useAsset(i2vSourceAssetId);
  const retryMutation = useMutation({
    mutationFn: retryGeneration,
    onMutate: () => {
      setRetryError(null);
    },
    onSuccess: async (newJob) => {
      queryClient.setQueryData(["job", newJob.id], newJob);
      await queryClient.invalidateQueries({ queryKey: ["generations"] });
      navigate(`/jobs/${newJob.id}`);
    },
    onError: (error) => {
      setRetryError(error instanceof Error ? error.message : "Retry failed.");
    },
  });

  if (!jobId) {
    return (
      <RoutePlaceholder eyebrow="Route 파라미터 없음" title="작업 ID가 필요합니다">
        제출한 생성 결과나 기록 행에서 이동하면 작업을 확인할 수 있습니다.
      </RoutePlaceholder>
    );
  }

  if (jobQuery.isLoading) {
    return <JobLoading jobId={jobId} />;
  }

  if (jobQuery.isError || !job) {
    const message =
      jobQuery.error instanceof Error ? jobQuery.error.message : "작업을 불러올 수 없습니다.";
    return (
      <RoutePlaceholder eyebrow="작업 요청 실패" title={jobId}>
        {message}
      </RoutePlaceholder>
    );
  }

  return (
    <div className="page-grid page-grid--detail">
      <Panel className="asset-shell" title="Asset Viewer" eyebrow="결과">
        <AssetViewer
          asset={primaryAsset}
          imageResultAssets={imageResultAssets}
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
        title="작업 상태"
        eyebrow={isTerminalJobState(job.state) ? "최종 상태" : "실시간 진행"}
      >
        {!isTerminalJobState(job.state) && <CurrentStepSummary job={job} />}
        <JobStateTimeline history={job.state_history} state={job.state} />
        <JobWaitingContext job={job} />
        {job.state === "failed" && (
          <RetryJobAction
            error={retryError}
            isRetrying={retryMutation.isPending}
            onRetry={() => retryMutation.mutate(job.id)}
          />
        )}
      </Panel>

      <Panel title="요청 요약" eyebrow={job.mode}>
        <RequestSummary job={job} />
      </Panel>

      {job.error && (
        <Panel title="오류 메시지" eyebrow="생성 오류">
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
      <Panel title="작업 로딩 중" eyebrow={jobId}>
        <div className="asset-preview">
          <div>
            <Badge tone="muted">
              <StatusDot tone="pending" />
              로딩 중
            </Badge>
            <h2>작업 상태를 가져오는 중</h2>
            <p>
              작업이 최종 상태에 도달할 때까지 이 페이지가 진행 상황을 자동으로 새로고침합니다.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function AssetViewer({
  asset,
  imageResultAssets,
  i2vSourceAsset,
  i2vSourceError,
  i2vSourceLoading,
  job,
  onStartI2V,
}: {
  asset: AssetResponse | null;
  imageResultAssets: AssetResponse[];
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
            {stateCopy[job.state].label}
          </Badge>
          <h2>
            {failed
              ? "결과 생성 전에 작업이 중단되었습니다"
              : cancelled
                ? "생성이 취소되었습니다"
                : "결과 preview가 여기에 표시됩니다"}
          </h2>
          <p>
            {failed || cancelled
              ? "이 작업에는 완료된 asset이 없습니다. 원인은 작업 상태와 오류 상세를 확인하세요."
              : "결과가 저장되면 완성된 이미지 또는 영상이 이 viewer에 렌더링됩니다."}
          </p>
        </div>
      </div>
    );
  }

  if (!asset) {
    return (
      <div className="asset-preview">
        <div>
          <Badge tone="warning">반환된 asset 없음</Badge>
          <h2>Preview 없이 작업이 완료되었습니다</h2>
          <p>
            작업은 완료 상태에 도달했지만 표시할 asset이 응답에 포함되지 않았습니다.
            요청 요약과 상태 기록은 계속 확인할 수 있습니다.
          </p>
        </div>
      </div>
    );
  }

  if (job.mode === "t2i" && imageResultAssets.length > 1) {
    return (
      <T2IImageGallery
        assets={imageResultAssets}
        onStartI2V={onStartI2V}
      />
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
          {isVideo ? "영상 결과" : isImage ? "이미지 결과" : "Asset 반환됨"}
        </Badge>
        <div className="asset-result-header__copy">
          <h2>
            {isVideo
              ? "영상 결과 준비됨"
              : isImage
                ? "이미지 결과 준비됨"
                : "Asset 반환됨"}
          </h2>
          <p>
            {isVideo
              ? "아래에서 재생 컨트롤을 사용할 수 있습니다."
              : isImage
                ? "생성된 이미지가 아래에 준비되었습니다."
                : "결과는 반환되었지만 이 viewer는 이미지와 영상 파일만 preview할 수 있습니다."}
          </p>
        </div>
      </div>

      <div className="asset-stage">
        {isImage && (
          <img
            alt={`생성된 asset ${asset.id}`}
            className="asset-media"
            src={asset.url}
          />
        )}
        {isVideo && (
          <video className="asset-media" controls src={asset.url}>
            <a href={asset.url}>생성된 영상 열기</a>
          </video>
        )}
        {!isPreviewable && (
          <div className="asset-preview">
            <div>
              <Badge tone="warning">Preview 불가</Badge>
              <h2>이 파일 유형은 여기서 preview할 수 없습니다</h2>
              <p>
                이 asset은 {asset.mime} 유형으로 반환되었고, 이 viewer에서는 inline 렌더링할 수 없습니다.
                Metadata는 아래에 표시됩니다.
              </p>
            </div>
          </div>
        )}
      </div>

      {isImage && imageResultAssets[0] && (
        <div className="result-next-action">
          <div className="result-next-action__copy">
            <Badge tone="success">
              <PipelineIcon size={12} />
              다음 작업
            </Badge>
            <strong>이 이미지로 영상 만들기</strong>
            <p>
              이 완성된 이미지를 새 image-to-video 요청의 고정 소스로 사용합니다.
            </p>
          </div>
          <Button
            onClick={() => onStartI2V(imageResultAssets[0].id)}
            type="button"
            variant="primary"
          >
            <PipelineIcon size={14} />
            이 이미지로 I2V 시작
          </Button>
        </div>
      )}

      <div className="asset-metadata-panel">
        <div className="asset-metadata-panel__head">
          <div className="section-label">파일 상세</div>
          <p>생성 결과의 preview 상세입니다.</p>
        </div>
        <div className="metadata-list asset-metadata">
          <div>
            <span>유형</span>
            <strong>{formatAssetType(asset)}</strong>
          </div>
          <div>
            <span>MIME</span>
            <strong>{asset.mime}</strong>
          </div>
          <div>
            <span>크기</span>
            <strong>{formatBytes(asset.size_bytes)}</strong>
          </div>
          <div>
            <span>해상도</span>
            <strong>{formatDimensions(asset)}</strong>
          </div>
          {asset.duration_sec !== null && (
            <div>
              <span>길이</span>
              <strong>{asset.duration_sec}s</strong>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function T2IImageGallery({
  assets,
  onStartI2V,
}: {
  assets: AssetResponse[];
  onStartI2V: (assetId: string) => void;
}) {
  const totalBytes = assets.reduce((sum, asset) => sum + asset.size_bytes, 0);

  return (
    <div className="asset-viewer">
      <div className="asset-result-header">
        <Badge tone="success">
          <ImageIcon size={12} />
          이미지 결과
        </Badge>
        <div className="asset-result-header__copy">
          <h2>이미지 결과 {assets.length}개 준비됨</h2>
          <p>각 생성 이미지를 I2V 소스로 사용할 수 있습니다.</p>
        </div>
      </div>

      <div className="asset-gallery-grid">
        {assets.map((imageAsset, index) => (
          <div className="asset-gallery-card" key={imageAsset.id}>
            <div className="asset-gallery-card__stage">
              <img
                alt={`생성 이미지 ${index + 1}`}
                className="asset-gallery-card__image"
                src={imageAsset.url}
              />
            </div>
            <div className="asset-gallery-card__body">
              <div className="asset-gallery-card__meta">
                <strong>이미지 {index + 1}</strong>
                <span>
                  {formatDimensions(imageAsset)} / {formatBytes(imageAsset.size_bytes)}
                </span>
              </div>
              <Button
                onClick={() => onStartI2V(imageAsset.id)}
                type="button"
                variant="primary"
              >
                <PipelineIcon size={14} />
                I2V 시작
              </Button>
            </div>
          </div>
        ))}
      </div>

      <div className="asset-metadata-panel">
        <div className="asset-metadata-panel__head">
          <div className="section-label">파일 상세</div>
          <p>생성 이미지 세트의 preview 상세입니다.</p>
        </div>
        <div className="metadata-list asset-metadata">
          <div>
            <span>유형</span>
            <strong>이미지 세트</strong>
          </div>
          <div>
            <span>개수</span>
            <strong>{assets.length}</strong>
          </div>
          <div>
            <span>총 크기</span>
            <strong>{formatBytes(totalBytes)}</strong>
          </div>
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
          소스 이미지 컨텍스트
        </Badge>
        <div className="asset-result-header__copy">
          <h2>{sourcePreviewTitle(job.state)}</h2>
          <p>
            이 I2V 작업은 영상 결과가 준비될 때까지 소스 이미지를 계속 표시합니다.
          </p>
        </div>
      </div>

      <div className="asset-stage asset-stage--source">
        {sourceLoading && (
          <div className="asset-preview">
            <div>
              <Badge tone="muted">
                <StatusDot tone="pending" />
                소스 로딩 중
              </Badge>
              <h2>소스 이미지를 가져오는 중</h2>
              <p>이 I2V 요청에 고정된 이미지 asset을 불러오고 있습니다.</p>
            </div>
          </div>
        )}
        {!sourceLoading && sourceIsImage && (
          <img
            alt={`소스 asset ${sourceAsset.id}`}
            className="asset-media"
            src={sourceAsset.url}
          />
        )}
        {!sourceLoading && (!sourceIsImage || sourceError) && (
          <div className="asset-preview">
            <div>
              <Badge tone={sourceError ? "danger" : "warning"}>
                {sourceError ? "소스 불러오기 실패" : "소스 대기 중"}
              </Badge>
              <h2>소스 이미지 preview를 사용할 수 없습니다</h2>
              <p>
                작업 metadata에는 소스 asset ID {shortId(job.source_asset_id)}가 남아 있지만,
                이미지 preview를 불러오지 못했습니다.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="asset-metadata-panel">
        <div className="asset-metadata-panel__head">
          <div className="section-label">I2V 소스</div>
          <p>이 image-to-video 요청에 고정된 소스 컨텍스트입니다.</p>
        </div>
        <div className="metadata-list asset-metadata">
          <div>
            <span>소스 asset</span>
            <strong>{shortId(job.source_asset_id)}</strong>
          </div>
          <div>
            <span>현재 상태</span>
            <strong>{stateCopy[job.state].label}</strong>
          </div>
          {sourceAsset && (
            <div>
              <span>소스 유형</span>
              <strong>{formatAssetType(sourceAsset)}</strong>
            </div>
          )}
          {sourceAsset && (
            <div>
              <span>해상도</span>
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
          현재 단계
        </Badge>
        <span>
          {stateSteps.length}단계 중 {activeIndex + 1}단계
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
          <small>종료</small>
        </div>
      )}
    </div>
  );
}

function JobWaitingContext({ job }: { job: JobResponse }) {
  const terminal = isTerminalJobState(job.state);

  return (
    <div className="job-context-grid" aria-label="작업 진행 컨텍스트">
      <div className="job-context-card">
        <span>현재 상태</span>
        <strong>{stateCopy[job.state].summary}</strong>
        <small>{terminal ? "최종 상태에 도달했습니다." : "작업이 진행되는 동안 업데이트가 계속됩니다."}</small>
      </div>
      <div className="job-context-card">
        <span>실행 시도</span>
        <strong>{job.attempts}</strong>
        <small>요청에 재시도가 필요하면 여기에 표시됩니다.</small>
      </div>
    </div>
  );
}

function RetryJobAction({
  error,
  isRetrying,
  onRetry,
}: {
  error: string | null;
  isRetrying: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="retry-action">
      <div className="retry-action__copy">
        <Badge tone="danger">
          <StatusDot tone="danger" />
          Retry
        </Badge>
        <strong>Retry this failed generation</strong>
        <p>Create a new job from the same confirmed generation payload.</p>
        {error && (
          <div className="inline-notice inline-notice--danger" role="alert">
            {error}
          </div>
        )}
      </div>
      <Button disabled={isRetrying} onClick={onRetry} type="button" variant="primary">
        <RetryIcon size={14} />
        {isRetrying ? "Retrying" : "Retry"}
      </Button>
    </div>
  );
}

function RequestSummary({ job }: { job: JobResponse }) {
  return (
    <div className="request-summary">
      <div className="metadata-list">
        <div>
          <span>모드</span>
          <strong>{job.mode}</strong>
        </div>
        {job.retry_of_job_id && (
          <div>
            <span>Retry</span>
            <strong>Retry of {shortId(job.retry_of_job_id)}</strong>
          </div>
        )}
        <div>
          <span>모델</span>
          <strong>{job.model}</strong>
        </div>
        <div>
          <span>생성일</span>
          <strong>{formatDateTime(job.created_at)}</strong>
        </div>
        <div>
          <span>수정일</span>
          <strong>{formatDateTime(job.updated_at)}</strong>
        </div>
        {job.enhancement_id && (
          <div>
            <span>프롬프트 향상</span>
            <strong>적용됨</strong>
          </div>
        )}
        {job.source_asset_id && (
          <div>
            <span>소스 이미지</span>
            <strong>연결됨</strong>
          </div>
        )}
      </div>

      <div className="prompt-detail">
        <Badge tone="muted">
          <FilmIcon size={12} />
          프롬프트
        </Badge>
        <p>{job.prompt}</p>
      </div>

      {job.enhanced_prompt && (
        <div className="prompt-detail">
          <Badge tone="info">
            <ImageIcon size={12} />
            향상된 프롬프트
          </Badge>
          <p>{job.enhanced_prompt}</p>
        </div>
      )}

      <div className="prompt-detail">
        <Badge tone="muted">파라미터</Badge>
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
    return "완료";
  }
  if (active && step === state) {
    return "현재";
  }
  if (done) {
    return "완료";
  }
  return "대기";
}

function findCompletedImageAssets(job: JobResponse | undefined): AssetResponse[] {
  if (!job || job.state !== "completed") {
    return [];
  }

  return job.assets.filter(
    (asset) => asset.kind === "image" || asset.mime.startsWith("image/"),
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
    return "영상 결과 전에 I2V가 중단되었습니다";
  }
  if (state === "cancelled") {
    return "I2V가 취소되었습니다";
  }
  return "I2V 소스 이미지가 고정되었습니다";
}

function shortId(value: string | null): string {
  return value ? value.slice(0, 8) : "알 수 없음";
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
    return "이미지";
  }
  if (asset.kind === "video") {
    return "영상";
  }
  return asset.kind;
}

function formatDimensions(asset: AssetResponse): string {
  if (asset.width && asset.height) {
    return `${asset.width} x ${asset.height}`;
  }
  return "알 수 없음";
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
