import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  ApiError,
  createGeneration,
  createPipeline,
  enhancePrompt,
  type AssetResponse,
  type CreativityPreset,
  type GenerationCreateRequest,
  type GenerationMode,
  type PipelineCreateRequest,
  type PromptEnhancementResponse,
} from "../api/client";
import { Badge, Button, Panel, StatusDot } from "../components/ui";
import { ClockIcon, CpuIcon, FilmIcon, ImageIcon, PipelineIcon, SparkleIcon } from "../components/icons";
import { useAsset } from "../hooks/useAsset";

type GenerateMode = GenerationMode | "pipeline";

type ModelOption = {
  id: string;
  label: string;
  detail: string;
};

type ModeConfig = {
  mode: GenerateMode;
  label: string;
  title: string;
  description: string;
  icon: typeof ImageIcon;
  models: ModelOption[];
};

type AcceptedEnhancement = {
  id: string;
  target_mode: GenerationMode;
  target_model: string;
  creativity_preset: CreativityPreset;
};

type CreativityOption = {
  value: CreativityPreset;
  label: string;
};

const imagenModels: ModelOption[] = [
  {
    id: "imagen-4.0-fast-generate-001",
    label: "Imagen 4 Fast",
    detail: "빠른 이미지 생성",
  },
  {
    id: "imagen-4.0-generate-001",
    label: "Imagen 4",
    detail: "균형 잡힌 이미지 생성",
  },
  {
    id: "imagen-4.0-ultra-generate-001",
    label: "Imagen 4 Ultra",
    detail: "최고 품질 이미지 생성",
  },
];

const veoModels: ModelOption[] = [
  {
    id: "veo-3.0-fast-generate-001",
    label: "Veo 3 Fast",
    detail: "빠른 영상 생성",
  },
  {
    id: "veo-3.0-generate-001",
    label: "Veo 3",
    detail: "더 높은 품질의 영상 생성",
  },
];

const modes: ModeConfig[] = [
  {
    mode: "t2i",
    label: "T2I",
    title: "텍스트 → 이미지",
    description: "텍스트 프롬프트로 Imagen 작업을 만듭니다.",
    icon: ImageIcon,
    models: imagenModels,
  },
  {
    mode: "t2v",
    label: "T2V",
    title: "텍스트 → 영상",
    description: "텍스트 프롬프트로 Veo 작업을 만듭니다.",
    icon: FilmIcon,
    models: veoModels,
  },
  {
    mode: "i2v",
    label: "I2V",
    title: "이미지 → 영상",
    description: "완성된 이미지 결과에 움직임을 더합니다.",
    icon: PipelineIcon,
    models: veoModels,
  },
  {
    mode: "pipeline",
    label: "Pipeline",
    title: "T2I → I2V",
    description: "이미지 parent 작업과 I2V child 작업을 함께 만듭니다.",
    icon: PipelineIcon,
    models: [
      {
        id: "imagen-4.0-fast-generate-001+veo-3.0-fast-generate-001",
        label: "Imagen Fast + Veo Fast",
        detail: "이미지 먼저, 영상은 다음",
      },
    ],
  },
];

const aspectOptions = ["1:1", "16:9", "9:16", "4:3"];
const durationOptions = [4, 6, 8];
const creativityOptions: CreativityOption[] = [
  { value: "faithful", label: "원본 충실" },
  { value: "balanced", label: "균형" },
  { value: "imaginative", label: "상상력" },
];
const defaultCreativityPreset: CreativityPreset = "balanced";
const defaultPrompt =
  "Neon-soaked Seoul alley at night, rain reflections, lone cyclist passing a noodle stall.";
const defaultPipelineVideoPrompt =
  "Slow dolly forward as the cyclist passes, steam rises from the stall, neon reflections ripple in puddles.";

export function GeneratePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const querySourceAssetId = parseUuid(searchParams.get("source_asset_id"));
  const initialMode = querySourceAssetId
    ? "i2v"
    : parseGenerateMode(searchParams.get("mode"));
  const initialModeConfig =
    modes.find((item) => item.mode === initialMode) ?? modes[0];
  const [mode, setModeState] = useState<GenerateMode>(initialMode);
  const [model, setModelState] = useState(initialModeConfig.models[0].id);
  const [prompt, setPrompt] = useState(initialMode === "i2v" ? "" : defaultPrompt);
  const [aspectRatio, setAspectRatio] = useState(initialMode === "t2i" ? "1:1" : "16:9");
  const [durationSec, setDurationSec] = useState(4);
  const [numberOfImages, setNumberOfImages] = useState(1);
  const [pipelineVideoPrompt, setPipelineVideoPrompt] = useState(defaultPipelineVideoPrompt);
  const [pipelineImageModel, setPipelineImageModel] = useState(imagenModels[0].id);
  const [pipelineVideoModel, setPipelineVideoModel] = useState(veoModels[0].id);
  const [pipelineImageAspectRatio, setPipelineImageAspectRatio] = useState("1:1");
  const [pipelineVideoAspectRatio, setPipelineVideoAspectRatio] = useState("16:9");
  const [creativityPreset, setCreativityPresetState] = useState<CreativityPreset>(
    defaultCreativityPreset,
  );
  const [enhanceReview, setEnhanceReview] = useState<PromptEnhancementResponse | null>(
    null,
  );
  const [editableEnhancedPrompt, setEditableEnhancedPrompt] = useState("");
  const [acceptedEnhancement, setAcceptedEnhancement] =
    useState<AcceptedEnhancement | null>(null);

  const activeMode = modes.find((item) => item.mode === mode) ?? modes[0];
  const canEnhance = mode !== "pipeline" && prompt.trim().length > 0;
  const usableEnhancementId =
    acceptedEnhancement &&
    mode !== "pipeline" &&
    acceptedEnhancement.target_mode === mode &&
    acceptedEnhancement.target_model === model &&
    acceptedEnhancement.creativity_preset === creativityPreset
      ? acceptedEnhancement.id
      : null;

  const sourceAssetId = mode === "i2v" ? querySourceAssetId : null;
  const sourceAssetQuery = useAsset(sourceAssetId);
  const heroPrompt = prompt.trim();
  const heroTitle =
    heroPrompt && heroPrompt !== defaultPrompt
      ? heroPrompt
      : "무엇을 상상하고 있나요?";
  const pipelineSubmitDisabled =
    mode === "pipeline" && (!prompt.trim() || !pipelineVideoPrompt.trim());
  const submitDisabled =
    mode === "pipeline"
      ? pipelineSubmitDisabled
      : !prompt.trim() || (mode === "i2v" && !sourceAssetId);

  const submitMutation = useMutation({
    mutationFn: createGeneration,
    onSuccess: (job) => {
      navigate(`/jobs/${job.id}`);
    },
  });

  const enhanceMutation = useMutation({
    mutationFn: enhancePrompt,
    onSuccess: (result) => {
      setEnhanceReview(result);
      setEditableEnhancedPrompt(result.enhanced);
      setAcceptedEnhancement(null);
    },
  });

  const pipelineMutation = useMutation({
    mutationFn: createPipeline,
    onSuccess: (pipeline) => {
      navigate(`/pipelines/${pipeline.id}`);
    },
  });

  const submitLabel = useMemo(() => {
    if (mode === "pipeline") {
      return pipelineMutation.isPending ? "Pipeline 생성 중..." : "Pipeline 생성";
    }
    if (mode === "i2v" && !sourceAssetId) {
      return "이미지 소스 선택";
    }
    if (submitMutation.isPending) {
      return "작업 생성 중...";
    }
    return "생성";
  }, [mode, pipelineMutation.isPending, sourceAssetId, submitMutation.isPending]);

  function setMode(nextMode: GenerateMode) {
    const nextConfig = modes.find((item) => item.mode === nextMode) ?? modes[0];
    setModeState(nextMode);
    setModelState(nextConfig.models[0].id);
    setAspectRatio(nextMode === "t2i" ? "1:1" : "16:9");
    clearEnhancementState();
  }

  function setModel(nextModel: string) {
    setModelState(nextModel);
    clearEnhancementState();
  }

  function setCreativityPreset(nextPreset: CreativityPreset) {
    setCreativityPresetState(nextPreset);
    clearEnhancementState();
  }

  function updatePrompt(nextPrompt: string) {
    setPrompt(nextPrompt);
    setAcceptedEnhancement(null);
  }

  function clearEnhancementState() {
    setAcceptedEnhancement(null);
    setEnhanceReview(null);
    setEditableEnhancedPrompt("");
  }

  function acceptEnhancement() {
    if (!enhanceReview || mode === "pipeline") {
      return;
    }

    setPrompt(editableEnhancedPrompt);
    setAcceptedEnhancement({
      id: enhanceReview.id,
      target_mode: enhanceReview.target_mode,
      target_model: enhanceReview.target_model,
      creativity_preset: enhanceReview.creativity_preset,
    });
    setEnhanceReview(null);
  }

  function runEnhance() {
    if (!canEnhance) {
      return;
    }

    enhanceMutation.mutate({
      prompt,
      target_mode: mode,
      target_model: model,
      creativity_preset: creativityPreset,
    });
  }

  function submitGeneration() {
    if (submitDisabled) {
      return;
    }

    if (mode === "pipeline") {
      const payload: PipelineCreateRequest = {
        image_prompt: prompt,
        video_prompt: pipelineVideoPrompt,
        image_model: pipelineImageModel,
        video_model: pipelineVideoModel,
        image_aspect_ratio: pipelineImageAspectRatio,
        video_aspect_ratio: pipelineVideoAspectRatio,
        duration_sec: durationSec,
      };
      pipelineMutation.mutate(payload);
      return;
    }

    const base = {
      prompt,
      model,
      auto_enhance: false,
      ...(usableEnhancementId ? { enhancement_id: usableEnhancementId } : {}),
    };

    let payload: GenerationCreateRequest;
    if (mode === "t2i") {
      payload = {
        ...base,
        mode,
        aspect_ratio: aspectRatio,
        number_of_images: numberOfImages,
      };
    } else if (mode === "t2v") {
      payload = {
        ...base,
        mode,
        aspect_ratio: aspectRatio,
        duration_sec: durationSec,
      };
    } else {
      if (!sourceAssetId) {
        return;
      }
      payload = {
        ...base,
        mode,
        source_asset_id: sourceAssetId,
        aspect_ratio: aspectRatio,
        duration_sec: durationSec,
      };
    }

    submitMutation.mutate(payload);
  }

  return (
    <div className="page-grid page-grid--generate">
      <Panel className="cinema-panel">
        <div
          className={`cinema-screen${
            mode === "i2v" && sourceAssetId ? " cinema-screen--source" : ""
          }`}
        >
          {mode === "i2v" && sourceAssetId ? (
            <SourceImageCinema
              asset={sourceAssetQuery.data ?? null}
              heroTitle={heroTitle}
              isError={sourceAssetQuery.isError}
              isLoading={sourceAssetQuery.isLoading}
            />
          ) : (
            <div className="cinema-screen__content">
              <Badge tone={mode === "pipeline" ? "warning" : "info"}>
                <SparkleIcon size={12} />
                {activeMode.title}
              </Badge>
              <h2>{heroTitle}</h2>
              <p>
                {mode === "pipeline"
                  ? "Parent T2I 이미지와 대기 중인 child I2V 작업을 함께 만듭니다."
                  : enhanceReview
                    ? "아래 향상 초안을 검토하세요. 수락하기 전까지 현재 프롬프트는 바뀌지 않습니다."
                    : usableEnhancementId
                      ? "수락한 초안이 생성 프롬프트로 반영되었고 이 작업에 연결됩니다."
                      : "모드와 모델을 고르고 프롬프트를 작성한 뒤, 필요하면 향상 후 생성하세요."}
              </p>
            </div>
          )}
        </div>
      </Panel>

      <Panel title="요청 구성" eyebrow="생성">
        <div className="request-flow" aria-label="생성 요청 흐름">
          <div className="request-flow__item">
            <span>1</span>
            <strong>모드와 모델</strong>
            <small>{activeMode.title} 선택됨</small>
          </div>
          <div
            className={`request-flow__item${
              mode === "pipeline" ? " request-flow__item--muted" : ""
            }`}
          >
            <span>2</span>
            <strong>선택 향상</strong>
            <small>
              {mode === "pipeline"
                ? "단일 작업 프롬프트만 가능"
                : "Gemini가 검토용 초안을 반환합니다"}
            </small>
          </div>
          <div
            className={`request-flow__item${
              enhanceReview || usableEnhancementId ? "" : " request-flow__item--muted"
            }`}
          >
            <span>3</span>
            <strong>검토 후 수락</strong>
            <small>
              {usableEnhancementId
                ? "초안이 프롬프트에 반영됨"
                : enhanceReview
                  ? "편집 가능한 초안이 아래에 대기 중"
                  : "메인 프롬프트는 그대로 유지"}
            </small>
          </div>
          <div className="request-flow__item">
            <span>4</span>
            <strong>생성</strong>
            <small>화면에 보이는 프롬프트를 생성 큐로 보냅니다</small>
          </div>
        </div>

        <div className="mode-grid" role="list" aria-label="생성 모드">
          {modes.map((item) => {
            const Icon = item.icon;
            const active = item.mode === mode;
            return (
              <button
                className={`mode-card${active ? " mode-card--active" : ""}`}
                key={item.mode}
                onClick={() => setMode(item.mode)}
                type="button"
              >
                <div className="mode-card__icon">
                  <Icon size={16} />
                </div>
                <div>
                  <div className="mode-card__label">{item.label}</div>
                  <div className="mode-card__title">{item.title}</div>
                  <p>{item.description}</p>
                </div>
              </button>
            );
          })}
        </div>

        <form
          className="form-shell"
          onSubmit={(event) => {
            event.preventDefault();
            submitGeneration();
          }}
        >
          {mode === "i2v" && (
            <div
              className={`source-lock-card${
                sourceAssetId ? " source-lock-card--connected" : ""
              }`}
            >
              <Badge tone={sourceAssetId ? "success" : "warning"}>
                <PipelineIcon size={12} />
                {sourceAssetId ? "소스 이미지 잠김" : "이미지 소스 필요"}
              </Badge>
              <div>
                <strong>
                  {sourceAssetId
                    ? "이전 결과에서 선택한 이미지를 사용합니다"
                    : "완성된 이미지 결과에서 시작하세요"}
                </strong>
                <p>
                  {sourceAssetId
                    ? "이미지가 계속 연결됩니다. 아래 프롬프트에 추가할 움직임을 설명하세요."
                    : "완성된 이미지 결과를 열고 이 이미지로 I2V 시작을 선택하세요."}
                </p>
              </div>
            </div>
          )}

          <label>
            <span>
              {mode === "pipeline"
                ? "이미지 프롬프트"
                : mode === "i2v"
                  ? "모션 프롬프트"
                  : "프롬프트"}
            </span>
            <textarea
              onChange={(event) => updatePrompt(event.target.value)}
              placeholder={
                mode === "pipeline"
                  ? "Pipeline이 먼저 생성할 정지 이미지를 설명하세요."
                  : mode === "i2v"
                  ? "추가할 움직임을 설명하세요: 카메라 이동, 피사체 동작, 속도감."
                  : "피사체, 구도, 조명, 움직임, 스타일을 설명하세요."
              }
              value={prompt}
            />
            <span className="field-hint">
              {mode === "pipeline"
                ? "이 이미지 프롬프트가 parent T2I 작업을 시작합니다."
                : mode === "i2v"
                  ? "연결된 이미지는 시각 소스로 유지되고, 이 프롬프트가 움직임을 제어합니다."
                : "생성 요청에 전송될 프롬프트입니다. 향상 초안은 수락한 뒤에만 이 내용을 대체합니다."}
            </span>
          </label>

          {mode === "pipeline" && (
            <label>
              <span>영상 프롬프트</span>
              <textarea
                onChange={(event) => setPipelineVideoPrompt(event.target.value)}
                placeholder="Child I2V 작업에 사용할 카메라 움직임, 피사체 동작, 분위기를 설명하세요."
                value={pipelineVideoPrompt}
              />
              <span className="field-hint">
                이미지가 완성된 뒤 child I2V 작업에 사용될 프롬프트입니다.
              </span>
            </label>
          )}

          {mode === "pipeline" ? (
            <div className="field-grid field-grid--pipeline">
              <label>
                이미지 모델
                <select
                  onChange={(event) => setPipelineImageModel(event.target.value)}
                  value={pipelineImageModel}
                >
                  {imagenModels.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label} - {item.detail}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                영상 모델
                <select
                  onChange={(event) => setPipelineVideoModel(event.target.value)}
                  value={pipelineVideoModel}
                >
                  {veoModels.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label} - {item.detail}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                이미지 비율
                <select
                  onChange={(event) => setPipelineImageAspectRatio(event.target.value)}
                  value={pipelineImageAspectRatio}
                >
                  {aspectOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                영상 비율
                <select
                  onChange={(event) => setPipelineVideoAspectRatio(event.target.value)}
                  value={pipelineVideoAspectRatio}
                >
                  {aspectOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                길이
                <select
                  onChange={(event) => setDurationSec(Number(event.target.value))}
                  value={durationSec}
                >
                  {durationOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}s
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            <div className="field-grid">
              <label>
                모델
                <select onChange={(event) => setModel(event.target.value)} value={model}>
                  {activeMode.models.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label} - {item.detail}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                비율
                <select
                  onChange={(event) => setAspectRatio(event.target.value)}
                  value={aspectRatio}
                >
                  {aspectOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              {mode === "t2i" ? (
                <label>
                  이미지 수
                  <select
                    onChange={(event) => setNumberOfImages(Number(event.target.value))}
                    value={numberOfImages}
                  >
                    {[1, 2, 3, 4].map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label>
                  길이
                  <select
                    onChange={(event) => setDurationSec(Number(event.target.value))}
                    value={durationSec}
                  >
                    {durationOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}s
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}

          <div className="control-row">
            {mode === "pipeline" ? (
              <>
                <Badge tone="muted">
                  <ImageIcon size={12} />
                  {pipelineImageModel}
                </Badge>
                <Badge tone="muted">
                  <FilmIcon size={12} />
                  {pipelineVideoModel}
                </Badge>
              </>
            ) : (
              <Badge tone="muted">
                <CpuIcon size={12} />
                {model}
              </Badge>
            )}
            <Badge tone="muted">
              <ClockIcon size={12} />
              {mode === "t2i" ? `${numberOfImages}장` : `${durationSec}s`}
            </Badge>
            {sourceAssetId && (
              <Badge tone="success">
                <PipelineIcon size={12} />
                소스 이미지 연결됨
              </Badge>
            )}
          </div>

          {mode === "pipeline" && (
            <div className="inline-notice">
              Pipeline은 이미지를 먼저 만들고, 그 결과를 후속 영상의 소스로 사용합니다.
            </div>
          )}

          {usableEnhancementId && (
            <div className="inline-notice inline-notice--success">
              프롬프트 향상을 수락했습니다. 설정을 바꾸지 않는 동안 위 프롬프트가 생성에 사용됩니다.
            </div>
          )}

          {enhanceReview && (
            <div className="inline-notice">
              향상 초안이 아래에 대기 중입니다. 초안을 편집하고 수락하기 전까지 생성은 위 프롬프트를 사용합니다.
            </div>
          )}

          <ApiErrorMessage
            error={enhanceMutation.error ?? submitMutation.error ?? pipelineMutation.error}
          />

          <div className="enhancer-action-row">
            {mode !== "pipeline" && (
              <label className="enhancer-select">
                Gemini Enhancer 창의성
                <select
                  onChange={(event) =>
                    setCreativityPreset(event.target.value as CreativityPreset)
                  }
                  value={creativityPreset}
                >
                  {creativityOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <span>프롬프트 향상에만 적용되며 생성 설정은 바뀌지 않습니다.</span>
              </label>
            )}

            <div className="action-row">
              <Button
                disabled={!canEnhance || enhanceMutation.isPending || submitMutation.isPending}
                onClick={runEnhance}
                type="button"
                variant="secondary"
              >
                {enhanceMutation.isPending ? "향상 중..." : "프롬프트 향상"}
              </Button>
              <Button
                disabled={
                  submitDisabled || submitMutation.isPending || pipelineMutation.isPending
                }
                type="submit"
                variant="primary"
              >
                {submitLabel}
              </Button>
            </div>
          </div>
        </form>
      </Panel>

      {enhanceReview && (
        <EnhanceReviewPanel
          editableEnhancedPrompt={editableEnhancedPrompt}
          enhancement={enhanceReview}
          onAccept={acceptEnhancement}
          onChange={setEditableEnhancedPrompt}
          onDiscard={() => setEnhanceReview(null)}
          onUseOriginal={() => {
            setEnhanceReview(null);
            setEditableEnhancedPrompt("");
          }}
        />
      )}
    </div>
  );
}

function SourceImageCinema({
  asset,
  heroTitle,
  isError,
  isLoading,
}: {
  asset: AssetResponse | null;
  heroTitle: string;
  isError: boolean;
  isLoading: boolean;
}) {
  const isImage = asset
    ? asset.kind === "image" || asset.mime.startsWith("image/")
    : false;
  const imageAsset = isImage && asset ? asset : null;
  const previewTitle =
    heroTitle === "무엇을 상상하고 있나요?" ? "선택한 이미지에 움직임 더하기" : heroTitle;
  const badgeTone = imageAsset ? "success" : isError || asset ? "warning" : "info";

  return (
    <div className="cinema-source">
      <div className="cinema-source__media">
        {isLoading ? (
          <div className="cinema-source__placeholder">소스 이미지 로딩 중</div>
        ) : imageAsset ? (
          <img alt={`선택된 I2V 소스 asset ${imageAsset.id}`} src={imageAsset.url} />
        ) : isError ? (
          <div className="cinema-source__placeholder cinema-source__placeholder--warning">
            소스 이미지를 불러올 수 없습니다
          </div>
        ) : (
          <div className="cinema-source__placeholder cinema-source__placeholder--warning">
            선택한 소스가 이미지가 아닙니다
          </div>
        )}
      </div>

      <div className="cinema-screen__content cinema-screen__content--source">
        <Badge tone={badgeTone}>
          <PipelineIcon size={12} />
          {imageAsset ? "소스 이미지 잠김" : "I2V 소스"}
        </Badge>
        <h2>{previewTitle}</h2>
        <p>
          {imageAsset
            ? "이 이미지는 I2V 소스로 연결되어 있습니다. 모션 프롬프트에 어떻게 움직일지 설명하세요."
            : "소스 asset은 연결되었지만 이미지 preview를 렌더링할 수 없습니다."}
        </p>
      </div>
    </div>
  );
}

function EnhanceReviewPanel({
  editableEnhancedPrompt,
  enhancement,
  onAccept,
  onChange,
  onDiscard,
  onUseOriginal,
}: {
  editableEnhancedPrompt: string;
  enhancement: PromptEnhancementResponse;
  onAccept: () => void;
  onChange: (value: string) => void;
  onDiscard: () => void;
  onUseOriginal: () => void;
}) {
  return (
    <Panel className="enhance-panel" title="향상된 프롬프트 검토" eyebrow="Prompt Enhance">
      <div className="enhance-panel__top">
        <p className="panel-copy">
          Gemini가 편집 가능한 초안을 만들었습니다. 생성하기 전에 수락하면 요청 구성의 프롬프트로 복사됩니다.
        </p>

        <div className="action-row enhance-actions">
          <Button onClick={onDiscard} type="button" variant="ghost">
            버리기
          </Button>
          <Button onClick={onUseOriginal} type="button" variant="secondary">
            원본 유지
          </Button>
          <Button onClick={onAccept} type="button" variant="primary">
            초안 수락
          </Button>
        </div>
      </div>

      <div className="enhance-meta">
        <Badge tone="info">
          <StatusDot tone="info" />
          향상 초안
        </Badge>
        <Badge tone="muted">대상 {enhancement.target_mode}</Badge>
        <Badge tone="muted">
          창의성 {formatCreativityPreset(enhancement.creativity_preset)}
        </Badge>
        {enhancement.latency_ms !== null && (
          <Badge tone="muted">{enhancement.latency_ms}ms</Badge>
        )}
      </div>

      <div className="enhance-grid">
        <div className="enhance-section">
          <div className="enhance-section__head">
            <div className="section-label">원본 프롬프트</div>
            <p>향상에 사용한 원본 텍스트입니다.</p>
          </div>
          <div className="prompt-box">{enhancement.original}</div>
        </div>
        <label className="enhance-section">
          <div className="enhance-section__head">
            <span className="section-label">향상 프롬프트 초안</span>
            <span className="field-hint">
              편집 가능한 초안입니다. 수락하면 이 텍스트가 메인 프롬프트로 복사됩니다.
            </span>
          </div>
          <textarea
            aria-label="편집 가능한 향상 프롬프트 초안"
            onChange={(event) => onChange(event.target.value)}
            value={editableEnhancedPrompt}
          />
        </label>
      </div>

      <div className="enhance-components">
        <div className="enhance-section__head">
          <div className="section-label">구성 요소</div>
          <p>향상 프롬프트에서 뽑은 주요 creative cue입니다.</p>
        </div>
        <div className="component-list">
          {Object.entries(enhancement.components).map(([key, value]) => (
            <div className="component-chip" key={key}>
              <span>{key}</span>
              <strong>{formatComponentValue(value)}</strong>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function ApiErrorMessage({ error }: { error: unknown }) {
  if (!error) {
    return null;
  }

  const message = error instanceof ApiError || error instanceof Error
    ? error.message
    : "요청에 실패했습니다.";

  return <div className="inline-notice inline-notice--danger">{message}</div>;
}

function formatComponentValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value === null || value === undefined) {
    return "없음";
  }
  return JSON.stringify(value);
}

function formatCreativityPreset(value: CreativityPreset): string {
  const option = creativityOptions.find((item) => item.value === value);
  return option?.label ?? value;
}

function parseGenerateMode(value: string | null): GenerateMode {
  if (value === "t2i" || value === "t2v" || value === "i2v" || value === "pipeline") {
    return value;
  }
  return "t2i";
}

function parseUuid(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const uuidV4Pattern =
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidV4Pattern.test(value) ? value : null;
}
