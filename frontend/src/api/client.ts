import type {
  ApiErrorBody,
  AssetResponse,
  GenerationCreateRequest,
  GenerationListParams,
  GenerationResponse,
  HealthResponse,
  OpsHealthResponse,
  PersonalUsageResponse,
  PipelineCreateRequest,
  PipelineResponse,
  PromptEnhanceRequest,
  PromptEnhancementResponse,
  UUID,
} from "./types";
import { parsePersonalUsage } from "../ui/usage";

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
  OpsHealthResponse,
  PersonalUsageResponse,
  PipelineCreateRequest,
  PipelineResponse,
  PromptEnhanceRequest,
  PromptEnhancementResponse,
  StateHistoryEntry,
  T2IRequest,
  T2VRequest,
  UUID,
} from "./types";

const apiBase = normalizeApiBase(import.meta.env?.VITE_API_BASE);
import type { AuthReply, SessionController } from "../auth/session";

let sessionGuard: SessionController | undefined;
export function bindSessionGuard(session: SessionController) {
  sessionGuard = session;
  return () => { if (sessionGuard === session) sessionGuard = undefined; };
}

export function authApiConfigurationValid(origin: string, base = apiBase) {
  return !base || base === origin || base === `${origin}/`;
}
export function createAuthHttp(origin: string, base = apiBase, fetcher: typeof fetch = fetch, timeoutMs = 10_000) {
  const configured = authApiConfigurationValid(origin, base);
  async function request(path: string, signal: AbortSignal, method: string): Promise<AuthReply> {
    if (!configured) throw new Error("Authentication requires a same-origin API root");
    const abort = new AbortController();
    const cancel = () => abort.abort();
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) abort.abort();
    const timer = setTimeout(cancel, timeoutMs);
    try {
      const response = await fetcher(`${origin}${path}`, { method, credentials: "same-origin",
        cache: "no-store", signal: abort.signal, redirect: "error" });
      return { status: response.status, body: response.status === 200 ? await response.json() : undefined };
    } finally { clearTimeout(timer); signal.removeEventListener("abort", cancel); }
  }
  return { me: (signal: AbortSignal) => request("/api/auth/me", signal, "GET"),
    signOut: (signal: AbortSignal) => request("/api/auth/logout", signal, "POST") };
}

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

export async function getOpsHealth(): Promise<OpsHealthResponse> {
  return apiRequest<OpsHealthResponse>("/api/ops/health");
}

export async function getPersonalUsage(): Promise<PersonalUsageResponse> {
  return parsePersonalUsage(await apiRequest<unknown>("/api/usage/me"));
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

export async function retryGeneration(jobId: UUID): Promise<GenerationResponse> {
  const job = await apiRequest<GenerationResponse>(
    `/api/generations/${jobId}/retry`,
    {
      method: "POST",
    },
  );
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

export async function getAsset(assetId: UUID): Promise<AssetResponse> {
  const asset = await apiRequest<AssetResponse>(`/api/assets/${assetId}`);
  return resolveAssetUrl(asset);
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
  if (typeof window !== "undefined" && !authApiConfigurationValid(window.location.origin)) {
    throw new ApiError("Authentication requires a same-origin API root", 0, null);
  }
  const guard = path === "/api/health" ? undefined : sessionGuard;
  const epoch = guard?.getEpoch();
  const assertCurrent = () => {
    if (guard && (guard !== sessionGuard || epoch !== guard.getEpoch() || guard.getSnapshot().kind !== "authenticated")) {
      throw new ApiError("This request belongs to a previous session", 0, null);
    }
  };
  assertCurrent();
  const requestHeaders = new Headers(headers);

  const requestInit: RequestInit = {
    ...init,
    credentials: "same-origin",
    headers: requestHeaders,
  };

  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
    requestInit.body = JSON.stringify(body);
  }

  const response = await fetch(buildUrl(path, query), requestInit);
  assertCurrent();

  if (!response.ok) {
    const errorBody = await readJson<ApiErrorBody>(response);
    assertCurrent();
    if (response.status === 401 && epoch !== undefined) guard?.unauthorized(epoch);
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

  const result = await response.json() as T;
  assertCurrent();
  return result;
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
