import type {
  ApiErrorBody,
  AssetResponse,
  GenerationCreateRequest,
  GenerationListParams,
  GenerationResponse,
  HealthResponse,
  PipelineCreateRequest,
  PipelineResponse,
  PromptEnhanceRequest,
  PromptEnhancementResponse,
  UUID,
} from "./types";

export type {
  AssetResponse,
  AssetKind,
  CreativityPreset,
  GenerationCreateRequest,
  GenerationListParams,
  GenerationMode,
  GenerationResponse,
  HealthResponse,
  I2VRequest,
  JobResponse,
  JobState,
  PipelineCreateRequest,
  PipelineResponse,
  PromptEnhanceRequest,
  PromptEnhancementResponse,
  StateHistoryEntry,
  T2IRequest,
  T2VRequest,
  UUID,
} from "./types";

const apiBase = normalizeApiBase(import.meta.env.VITE_API_BASE);

type QueryValue = string | number | boolean | null | undefined;

type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, QueryValue>;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/health");
}

export async function createGeneration(
  payload: GenerationCreateRequest,
): Promise<GenerationResponse> {
  const job = await apiRequest<GenerationResponse>("/api/generations", {
    method: "POST",
    body: payload,
  });
  return resolveJobAssetUrls(job);
}

export async function listGenerations(
  params: GenerationListParams = {},
): Promise<GenerationResponse[]> {
  const jobs = await apiRequest<GenerationResponse[]>("/api/generations", {
    query: params,
  });
  return jobs.map(resolveJobAssetUrls);
}

export async function getGeneration(jobId: UUID): Promise<GenerationResponse> {
  const job = await apiRequest<GenerationResponse>(`/api/generations/${jobId}`);
  return resolveJobAssetUrls(job);
}

export async function deleteGeneration(jobId: UUID): Promise<void> {
  await apiRequest<void>(`/api/generations/${jobId}`, {
    method: "DELETE",
  });
}

export async function enhancePrompt(
  payload: PromptEnhanceRequest,
): Promise<PromptEnhancementResponse> {
  return apiRequest<PromptEnhancementResponse>("/api/prompts/enhance", {
    method: "POST",
    body: payload,
  });
}

export async function createPipeline(
  payload: PipelineCreateRequest,
): Promise<PipelineResponse> {
  const pipeline = await apiRequest<PipelineResponse>("/api/pipelines", {
    method: "POST",
    body: payload,
  });
  return resolvePipelineAssetUrls(pipeline);
}

export async function getPipeline(parentJobId: UUID): Promise<PipelineResponse> {
  const pipeline = await apiRequest<PipelineResponse>(
    `/api/pipelines/${parentJobId}`,
  );
  return resolvePipelineAssetUrls(pipeline);
}

async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { body, headers, query, ...init } = options;
  const requestHeaders = new Headers(headers);

  const requestInit: RequestInit = {
    ...init,
    headers: requestHeaders,
  };

  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
    requestInit.body = JSON.stringify(body);
  }

  const response = await fetch(buildUrl(path, query), requestInit);

  if (!response.ok) {
    const errorBody = await readJson<ApiErrorBody>(response);
    const detail = errorBody?.detail;
    throw new ApiError(
      formatApiErrorMessage(response.status, detail),
      response.status,
      detail,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${apiBase}${normalizedPath}`;
  const searchParams = new URLSearchParams();

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        searchParams.set(key, String(value));
      }
    }
  }

  const queryString = searchParams.toString();
  return queryString ? `${url}?${queryString}` : url;
}

function normalizeApiBase(value: string | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

function resolvePipelineAssetUrls(pipeline: PipelineResponse): PipelineResponse {
  return {
    ...pipeline,
    parent: resolveJobAssetUrls(pipeline.parent),
    child: resolveJobAssetUrls(pipeline.child),
  };
}

function resolveJobAssetUrls(job: GenerationResponse): GenerationResponse {
  if (!apiBase || job.assets.length === 0) {
    return job;
  }

  return {
    ...job,
    assets: job.assets.map(resolveAssetUrl),
  };
}

function resolveAssetUrl(asset: AssetResponse): AssetResponse {
  if (isAbsoluteUrl(asset.url)) {
    return asset;
  }

  return {
    ...asset,
    url: buildUrl(asset.url),
  };
}

function isAbsoluteUrl(value: string): boolean {
  return /^[a-z][a-z\d+\-.]*:/i.test(value) || value.startsWith("//");
}

async function readJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function formatApiErrorMessage(status: number, detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }

  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") {
      return message;
    }
  }

  return `API request failed with HTTP ${status}`;
}
