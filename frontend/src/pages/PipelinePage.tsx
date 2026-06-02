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
    label: "요청 준비 중",
    summary: "작업이 저장되어 runner 처리를 기다리고 있습니다.",
    timeline: "요청이 접수되었습니다.",
  },
  enhancing: {
    label: "프롬프트 향상 중",
    summary: "생성 전에 프롬프트 향상이 실행 중입니다.",
    timeline: "프롬프트 향상이 진행 중입니다.",
  },
  queued: {
    label: "생성 슬롯 대기 중",
    summary: "Runner가 모델 처리 용량을 기다리고 있습니다.",
    timeline: "모델 실행 대기열에 있습니다.",
  },
  generating: {
    label: "Vertex AI에서 생성 중",
    summary: "모델 요청이 실행 중입니다.",
    timeline: "모델 생성이 진행 중입니다.",
  },
  polling: {
    label: "모델 결과 확인 중",
    summary: "서비스가 완료된 결과를 polling하고 있습니다.",
    timeline: "결과가 아직 준비 중입니다.",
  },
  downloading: {
    label: "결과 저장 중",
    summary: "반환된 bytes를 로컬 저장소에 쓰고 있습니다.",
    timeline: "출력을 저장하고 있습니다.",
  },
  completed: {
    label: "완료",
    summary: "작업이 성공적인 최종 상태에 도달했습니다.",
    timeline: "결과가 준비되었습니다.",
  },
  failed: {
    label: "실패",
    summary: "작업이 오류로 중단되었습니다.",
    timeline: "최종 실패 상태입니다.",
  },
  cancelled: {
    label: "취소됨",
    summary: "작업이 완료 전에 취소되었습니다.",
    timeline: "최종 취소 상태입니다.",
  },
};

export function PipelinePage() {
  const { pipelineId } = useParams();
  const pipelineQuery = usePipeline(pipelineId);
  const pipeline = pipelineQuery.data;

  if (!pipelineId) {
    return (
      <RoutePlaceholder eyebrow="Route 파라미터 없음" title="Pipeline ID가 필요합니다">
        생성 폼이나 기록에서 Pipeline을 열면 두 작업을 함께 확인할 수 있습니다.
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
        : "Pipeline을 불러올 수 없습니다.";
    return (
      <RoutePlaceholder eyebrow="Pipeline 요청 실패" title={pipelineId}>
        {message}
      </RoutePlaceholder>
    );
  }

  const sourceAsset = findImageAsset(pipeline.parent);
  const activeStage = getActiveStage(pipeline);

  return (
    <div className="page-stack">
      <Panel title="Pipeline 상세" eyebrow={shortId(pipeline.id)}>
        <PipelineStatusBar pipeline={pipeline} />
        <PipelineLiveSummary activeStage={activeStage} pipeline={pipeline} />

        <div className="pipeline-shell">
          <PipelineStage
            active={activeStage === "parent"}
            icon={<ImageIcon size={18} />}
            job={pipeline.parent}
            stepLabel="1단계"
            title="Imagen 이미지 소스"
          />

          <div aria-hidden="true" className="pipeline-connector">
            <PipelineIcon size={26} />
          </div>

          <PipelineStage
            active={activeStage === "child"}
            icon={<FilmIcon size={18} />}
            job={pipeline.child}
            sourceAsset={sourceAsset}
            stepLabel="2단계"
            title="Veo Image-to-Video"
          />
        </div>
      </Panel>
    </div>
  );
}

function PipelineLoading({ pipelineId }: { pipelineId: string }) {
  return (
    <div className="page-stack">
      <Panel title="Pipeline 로딩 중" eyebrow={shortId(pipelineId)}>
        <div className="pipeline-live-summary">
          <Badge tone="info">
            <ClockIcon size={12} />
            Polling 중
          </Badge>
          <div className="pipeline-live-summary__copy">
            <strong>Parent와 child 작업을 가져오는 중</strong>
            <p>
              두 작업이 모두 최종 상태에 도달할 때까지 Pipeline 상세가 2초마다 새로고침됩니다.
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
        1단계 {stateCopy[pipeline.parent.state].label}
      </Badge>
      <Badge tone={toneForState(pipeline.child.state)}>
        <StatusDot tone={dotToneForState(pipeline.child.state)} />
        2단계 {stateCopy[pipeline.child.state].label}
      </Badge>
      {pipeline.child.blocked && <Badge tone="warning">소스 이미지 대기 중</Badge>}
      {pipeline.child.source_asset_id && (
        <Badge tone="success">
          <PipelineIcon size={12} />
          소스 이미지 연결됨
        </Badge>
      )}
      {!terminal && (
        <Badge tone="info">
          <ClockIcon size={12} />
          2초마다 polling
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
          {stateCopy[job.state].label}
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
          <span>작업</span>
          <Link to={`/jobs/${job.id}`}>{shortId(job.id)}</Link>
        </div>
        <div>
          <span>모델</span>
          <strong>{job.model}</strong>
        </div>
        <div>
          <span>수정일</span>
          <strong>{formatDateTime(job.updated_at)}</strong>
        </div>
        <div>
          <span>시도</span>
          <strong>{job.attempts}</strong>
        </div>
        {job.source_asset_id && (
          <div>
            <span>소스 asset</span>
            <strong>{shortId(job.source_asset_id)}</strong>
          </div>
        )}
        {formatParameter(job, "duration_sec") && (
          <div>
            <span>길이</span>
            <strong>{formatParameter(job, "duration_sec")}s</strong>
          </div>
        )}
      </div>

      <div className="pipeline-stage__prompt">
        <Badge tone="muted">프롬프트</Badge>
        <p>{job.prompt}</p>
      </div>

      {job.error && (
        <div className="pipeline-stage__prompt">
          <Badge tone="danger">오류</Badge>
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
            <small>{historyEntry ? formatDateTime(historyEntry.at) : "대기"}</small>
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
          <small>종료</small>
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
            <a href={asset.url}>생성된 영상 열기</a>
          </video>
        )}
        {!isImage && !isVideo && (
          <div className="pipeline-asset-preview--empty">
            <strong>Asset 반환됨</strong>
            <span>{asset.mime}는 inline preview를 할 수 없습니다.</span>
          </div>
        )}
      </div>
    );
  }

  if (job.mode === "i2v" && sourceAsset) {
    return (
      <div className="pipeline-asset-preview">
        <img alt={`소스 asset ${sourceAsset.id}`} src={sourceAsset.url} />
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
      badge: "2단계 중 1단계",
      detail:
        "이미지 작업이 아직 진행 중입니다. 이미지 asset이 준비될 때까지 I2V child는 대기합니다.",
      title: `소스 이미지 ${stateCopy[pipeline.parent.state].label}`,
      tone: "info",
    };
  }

  if (pipeline.parent.state === "failed" || pipeline.parent.state === "cancelled") {
    return {
      badge: "중단됨",
      detail:
        "사용 가능한 소스 asset이 만들어지기 전에 이미지 단계가 끝나 child 영상 작업을 계속할 수 없습니다.",
      title: "Pipeline이 이미지 단계에서 중단되었습니다",
      tone: pipeline.parent.state === "failed" ? "danger" : "warning",
    };
  }

  if (activeStage === "child") {
    return {
      badge: "2단계 중 2단계",
      detail: pipeline.child.blocked
        ? "영상 작업이 완료된 이미지 asset 연결을 기다리고 있습니다."
        : "소스 이미지가 연결되었고 Veo I2V 작업이 진행 중입니다.",
      title: `영상 결과 ${stateCopy[pipeline.child.state].label}`,
      tone: pipeline.child.blocked ? "warning" : "info",
    };
  }

  if (pipeline.child.state === "completed") {
    return {
      badge: "완료",
      detail: "두 작업 모두 성공 최종 상태에 도달했고 결과 asset을 사용할 수 있습니다.",
      title: "T2I → I2V Pipeline 완료",
      tone: "success",
    };
  }

  return {
    badge: "종료",
    detail: "Pipeline이 최종 상태에 도달했습니다. 각 단계의 오류 상세를 확인하세요.",
    title: "Pipeline에 더 이상 진행 중인 작업이 없습니다",
    tone: pipeline.child.state === "failed" ? "danger" : "warning",
  };
}

function getStageProgressTitle(job: JobResponse): string {
  if (job.blocked) {
    return "상위 이미지 대기 중";
  }
  return stateCopy[job.state].label;
}

function getStageProgressDetail(job: JobResponse): string {
  if (job.blocked) {
    return "Child I2V 요청은 저장되었지만 parent 이미지 asset이 연결될 때까지 실행되지 않습니다.";
  }
  if (job.mode === "i2v" && job.source_asset_id && !isTerminalJobState(job.state)) {
    return "소스 이미지가 고정되었고 Veo가 출력을 준비하는 동안 이 영상 작업이 계속 새로고침됩니다.";
  }
  return stateCopy[job.state].summary;
}

function getEmptyPreviewTitle(job: JobResponse): string {
  if (job.blocked) {
    return "Imagen 소스 대기 중";
  }
  if (job.state === "failed") {
    return "실패 후 preview 없음";
  }
  if (job.state === "cancelled") {
    return "취소 후 preview 없음";
  }
  if (job.state === "completed") {
    return "Asset 없이 완료됨";
  }
  return "Preview 대기 중";
}

function getEmptyPreviewDetail(job: JobResponse): string {
  if (job.blocked) {
    return "1단계가 유효한 이미지 asset을 만든 뒤 2단계가 시작됩니다.";
  }
  if (job.state === "polling") {
    return "Veo 출력이 아직 준비 중입니다.";
  }
  if (job.state === "downloading") {
    return "생성된 출력을 로컬에 저장하고 있습니다.";
  }
  if (job.state === "failed" || job.state === "cancelled") {
    return "원인은 단계 오류 또는 상태 기록을 확인하세요.";
  }
  if (job.state === "completed") {
    return "Backend가 preview 가능한 asset 없이 완료 상태를 반환했습니다.";
  }
  return "이 단계가 asset을 반환하면 preview가 여기에 표시됩니다.";
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
