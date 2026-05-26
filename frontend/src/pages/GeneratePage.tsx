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
    detail: "fast image generation",
  },
  {
    id: "imagen-4.0-generate-001",
    label: "Imagen 4",
    detail: "balanced image generation",
  },
  {
    id: "imagen-4.0-ultra-generate-001",
    label: "Imagen 4 Ultra",
    detail: "highest fidelity image generation",
  },
];

const veoModels: ModelOption[] = [
  {
    id: "veo-3.0-fast-generate-001",
    label: "Veo 3 Fast",
    detail: "fast video generation",
  },
  {
    id: "veo-3.0-generate-001",
    label: "Veo 3",
    detail: "higher quality video generation",
  },
];

const modes: ModeConfig[] = [
  {
    mode: "t2i",
    label: "T2I",
    title: "Text to image",
    description: "Create an Imagen job from a text prompt.",
    icon: ImageIcon,
    models: imagenModels,
  },
  {
    mode: "t2v",
    label: "T2V",
    title: "Text to video",
    description: "Create a Veo job from a text prompt.",
    icon: FilmIcon,
    models: veoModels,
  },
  {
    mode: "i2v",
    label: "I2V",
    title: "Image to video",
    description: "Animate a completed image result.",
    icon: PipelineIcon,
    models: veoModels,
  },
  {
    mode: "pipeline",
    label: "Pipeline",
    title: "T2I to I2V",
    description: "Create a parent image job and child I2V job.",
    icon: PipelineIcon,
    models: [
      {
        id: "imagen-4.0-fast-generate-001+veo-3.0-fast-generate-001",
        label: "Imagen Fast + Veo Fast",
        detail: "image first, video next",
      },
    ],
  },
];

const aspectOptions = ["1:1", "16:9", "9:16", "4:3"];
const durationOptions = [4, 6, 8];
const creativityOptions: CreativityOption[] = [
  { value: "faithful", label: "Faithful" },
  { value: "balanced", label: "Balanced" },
  { value: "imaginative", label: "Imaginative" },
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
      : "What are you imagining?";
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
      return pipelineMutation.isPending ? "Creating pipeline..." : "Create pipeline";
    }
    if (mode === "i2v" && !sourceAssetId) {
      return "Select image source";
    }
    if (submitMutation.isPending) {
      return "Creating job...";
    }
    return "Generate";
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
                  ? "Create a parent T2I image and a blocked child I2V job."
                  : enhanceReview
                    ? "Review the enhanced draft below. It will not change this prompt until accepted."
                    : usableEnhancementId
                      ? "The accepted draft is now the generation prompt and will be attached to this job."
                      : "Choose mode and model, write a prompt, optionally enhance, then generate."}
              </p>
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Request Builder" eyebrow="Generate">
        <div className="request-flow" aria-label="Generation request flow">
          <div className="request-flow__item">
            <span>1</span>
            <strong>Mode and model</strong>
            <small>{activeMode.title} selected</small>
          </div>
          <div
            className={`request-flow__item${
              mode === "pipeline" ? " request-flow__item--muted" : ""
            }`}
          >
            <span>2</span>
            <strong>Optional enhance</strong>
            <small>
              {mode === "pipeline"
                ? "Single-job prompts only"
                : "Gemini returns a review draft"}
            </small>
          </div>
          <div
            className={`request-flow__item${
              enhanceReview || usableEnhancementId ? "" : " request-flow__item--muted"
            }`}
          >
            <span>3</span>
            <strong>Review and accept</strong>
            <small>
              {usableEnhancementId
                ? "Draft accepted into prompt"
                : enhanceReview
                  ? "Editable draft is waiting below"
                  : "Main prompt stays unchanged"}
            </small>
          </div>
          <div className="request-flow__item">
            <span>4</span>
            <strong>Generate</strong>
            <small>Send the visible prompt to the generation queue</small>
          </div>
        </div>

        <div className="mode-grid" role="list" aria-label="Generation modes">
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
                {sourceAssetId ? "Source image locked" : "Image source needed"}
              </Badge>
              <div>
                <strong>
                  {sourceAssetId
                    ? "Using the selected image from the previous result"
                    : "Start from a completed image result"}
                </strong>
                <p>
                  {sourceAssetId
                    ? "The image stays connected. Use the prompt below to describe the motion to add."
                    : "Open a completed image result and choose Start I2V with this image."}
                </p>
              </div>
            </div>
          )}

          <label>
            <span>
              {mode === "pipeline"
                ? "Image prompt"
                : mode === "i2v"
                  ? "Motion prompt"
                  : "Prompt"}
            </span>
            <textarea
              onChange={(event) => updatePrompt(event.target.value)}
              placeholder={
                mode === "pipeline"
                  ? "Describe the still image the pipeline should generate first."
                  : mode === "i2v"
                  ? "Describe the motion to add: camera movement, subject action, and pacing."
                  : "Describe subject, composition, light, motion, and style."
              }
              value={prompt}
            />
            <span className="field-hint">
              {mode === "pipeline"
                ? "This image prompt starts the parent T2I job."
                : mode === "i2v"
                  ? "The connected image remains the visual source; this prompt controls how it moves."
                : "This is the prompt Generate will send. Enhanced drafts only replace it after you accept them."}
            </span>
          </label>

          {mode === "pipeline" && (
            <label>
              <span>Video prompt</span>
              <textarea
                onChange={(event) => setPipelineVideoPrompt(event.target.value)}
                placeholder="Describe camera motion, subject action, and atmosphere for the child I2V job."
                value={pipelineVideoPrompt}
              />
              <span className="field-hint">
                This prompt is held for the child I2V job after the image completes.
              </span>
            </label>
          )}

          {mode === "pipeline" ? (
            <div className="field-grid field-grid--pipeline">
              <label>
                Image model
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
                Video model
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
                Image aspect
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
                Video aspect
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
                Duration
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
                Model
                <select onChange={(event) => setModel(event.target.value)} value={model}>
                  {activeMode.models.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label} - {item.detail}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Aspect
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
                  Images
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
                  Duration
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
              {mode === "t2i" ? `${numberOfImages} image` : `${durationSec}s`}
            </Badge>
            {sourceAssetId && (
              <Badge tone="success">
                <PipelineIcon size={12} />
                Source image connected
              </Badge>
            )}
          </div>

          {mode === "pipeline" && (
            <div className="inline-notice">
              Pipeline creates an image first, then uses that result as the source
              for a follow-up video.
            </div>
          )}

          {usableEnhancementId && (
            <div className="inline-notice inline-notice--success">
              Prompt enhancement accepted. The prompt above is the version that
              will be generated while these settings remain unchanged.
            </div>
          )}

          {enhanceReview && (
            <div className="inline-notice">
              Enhanced draft is waiting below. Generate still uses the prompt above
              until you edit and accept that draft into the main prompt.
            </div>
          )}

          <ApiErrorMessage
            error={enhanceMutation.error ?? submitMutation.error ?? pipelineMutation.error}
          />

          <div className="enhancer-action-row">
            {mode !== "pipeline" && (
              <label className="enhancer-select">
                Gemini enhancer creativity
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
                <span>Prompt enhancement only; generation settings stay unchanged.</span>
              </label>
            )}

            <div className="action-row">
              <Button
                disabled={!canEnhance || enhanceMutation.isPending || submitMutation.isPending}
                onClick={runEnhance}
                type="button"
                variant="secondary"
              >
                {enhanceMutation.isPending ? "Enhancing..." : "Enhance prompt"}
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
    heroTitle === "What are you imagining?" ? "Animate the selected image" : heroTitle;
  const badgeTone = imageAsset ? "success" : isError || asset ? "warning" : "info";

  return (
    <div className="cinema-source">
      <div className="cinema-source__media">
        {isLoading ? (
          <div className="cinema-source__placeholder">Loading source image</div>
        ) : imageAsset ? (
          <img alt={`Selected I2V source asset ${imageAsset.id}`} src={imageAsset.url} />
        ) : isError ? (
          <div className="cinema-source__placeholder cinema-source__placeholder--warning">
            Source image unavailable
          </div>
        ) : (
          <div className="cinema-source__placeholder cinema-source__placeholder--warning">
            Selected source is not an image
          </div>
        )}
      </div>

      <div className="cinema-screen__content cinema-screen__content--source">
        <Badge tone={badgeTone}>
          <PipelineIcon size={12} />
          {imageAsset ? "Source image locked" : "I2V source"}
        </Badge>
        <h2>{previewTitle}</h2>
        <p>
          {imageAsset
            ? "This image is connected as the I2V source. Use the motion prompt to describe how it should move."
            : "The source asset is connected, but the preview could not render an image."}
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
    <Panel className="enhance-panel" title="Review Enhanced Prompt" eyebrow="Prompt Enhance">
      <div className="enhance-panel__top">
        <p className="panel-copy">
          Gemini produced an editable draft. Accept it to copy the draft into
          Request Builder before generating.
        </p>

        <div className="action-row enhance-actions">
          <Button onClick={onDiscard} type="button" variant="ghost">
            Discard
          </Button>
          <Button onClick={onUseOriginal} type="button" variant="secondary">
            Keep original
          </Button>
          <Button onClick={onAccept} type="button" variant="primary">
            Accept draft
          </Button>
        </div>
      </div>

      <div className="enhance-meta">
        <Badge tone="info">
          <StatusDot tone="info" />
          Enhanced draft
        </Badge>
        <Badge tone="muted">Target {enhancement.target_mode}</Badge>
        <Badge tone="muted">
          Creativity {formatCreativityPreset(enhancement.creativity_preset)}
        </Badge>
        {enhancement.latency_ms !== null && (
          <Badge tone="muted">{enhancement.latency_ms}ms</Badge>
        )}
      </div>

      <div className="enhance-grid">
        <div className="enhance-section">
          <div className="enhance-section__head">
            <div className="section-label">Original prompt</div>
            <p>Source text used for the enhancement.</p>
          </div>
          <div className="prompt-box">{enhancement.original}</div>
        </div>
        <label className="enhance-section">
          <div className="enhance-section__head">
            <span className="section-label">Enhanced prompt draft</span>
            <span className="field-hint">
              Editable draft. Accepting it copies this text into the main prompt.
            </span>
          </div>
          <textarea
            aria-label="Editable enhanced prompt draft"
            onChange={(event) => onChange(event.target.value)}
            value={editableEnhancedPrompt}
          />
        </label>
      </div>

      <div className="enhance-components">
        <div className="enhance-section__head">
          <div className="section-label">Components</div>
          <p>Key creative cues from the enhanced prompt.</p>
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
    : "Request failed.";

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
    return "none";
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
