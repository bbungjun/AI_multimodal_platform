export type UUID = string;
export type ISODateTime = string;
export type JsonObject = Record<string, unknown>;

export type VertexReadinessResponse = {
  ready: boolean;
  status: string;
  credentials: string;
  project: string;
  location: string;
};

export type HealthResponse = {
  ok: boolean;
  ready: boolean;
  service: string;
  db: "up" | "down";
  vertex: VertexReadinessResponse;
};

export type GenerationMode = "t2i" | "t2v" | "i2v";

export type CreativityPreset = "faithful" | "balanced" | "imaginative";

export type JobState =
  | "pending"
  | "enhancing"
  | "queued"
  | "generating"
  | "polling"
  | "downloading"
  | "completed"
  | "failed"
  | "cancelled";

export type AssetKind = "image" | "video";

export type StateHistoryEntry = {
  state: JobState;
  at: ISODateTime;
  detail: JsonObject | null;
};

export type AssetResponse = {
  id: UUID;
  job_id: UUID;
  kind: AssetKind;
  local_path: string;
  mime: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration_sec: number | null;
  created_at: ISODateTime;
  url: string;
};

export type PromptEnhanceRequest = {
  prompt: string;
  target_mode: GenerationMode;
  target_model: string;
  creativity_preset?: CreativityPreset;
};

export type PromptEnhancementResponse = {
  id: UUID;
  original: string;
  enhanced: string;
  components: JsonObject;
  target_mode: GenerationMode;
  target_model: string;
  llm_model: string;
  creativity_preset: CreativityPreset;
  temperature: number;
  latency_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: ISODateTime;
};

export type GenerationRequestBase = {
  prompt: string;
  model: string;
  auto_enhance?: boolean;
  enhancement_id?: UUID | null;
};

export type T2IRequest = GenerationRequestBase & {
  mode: "t2i";
  aspect_ratio?: string;
  number_of_images?: number;
};

export type T2VRequest = GenerationRequestBase & {
  mode: "t2v";
  aspect_ratio?: string;
  duration_sec?: number;
};

export type I2VRequest = GenerationRequestBase & {
  mode: "i2v";
  source_asset_id: UUID;
  aspect_ratio?: string;
  duration_sec?: number;
};

export type GenerationCreateRequest = T2IRequest | T2VRequest | I2VRequest;

export type JobResponse = {
  id: UUID;
  mode: GenerationMode;
  model: string;
  state: JobState;
  prompt: string;
  enhanced_prompt: string | null;
  enhancement_id: UUID | null;
  parent_job_id: UUID | null;
  source_asset_id: UUID | null;
  blocked: boolean;
  vertex_operation_name: string | null;
  attempts: number;
  parameters: JsonObject;
  state_history: StateHistoryEntry[];
  error: JsonObject | null;
  vertex_charged: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  assets: AssetResponse[];
};

export type GenerationResponse = JobResponse;

export type GenerationListParams = {
  mode?: GenerationMode;
  model?: string;
  state?: JobState;
  limit?: number;
  offset?: number;
};

export type PipelineCreateRequest = {
  image_prompt: string;
  video_prompt: string;
  image_model: string;
  video_model: string;
  image_aspect_ratio?: string;
  video_aspect_ratio?: string;
  duration_sec?: number;
};

export type PipelineResponse = {
  id: UUID;
  parent: JobResponse;
  child: JobResponse;
};

export type ApiErrorBody = {
  detail?: unknown;
};
