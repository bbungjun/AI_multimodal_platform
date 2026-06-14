# Frontend UI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `C:\Users\PC\Downloads\take-hom-assign (1)`의 프론트 UI 시안을 현재 `frontend`에 반영하되, 백엔드 API contract와 배포 설정은 깨지지 않게 유지한다.

**Architecture:** API boundary는 `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/hooks/*`에 고정하고, 새 UI는 view/component 계층에서만 교체한다. 다운로드 폴더의 `src/*.jsx`는 mock 기반 프로토타입이므로 그대로 복사하지 않고, TypeScript/React Router/React Query 구조에 맞게 필요한 레이아웃과 문구만 이식한다. 깨진 한글이나 혼재된 문구는 별도 copy registry로 정리해 화면 컴포넌트가 문자열을 흩뿌리지 않게 한다.

**Tech Stack:** Vite, React 18, TypeScript strict mode, React Router, TanStack React Query, existing CSS, existing FastAPI contract.

## Execution Status - 2026-06-14

- 완료: `frontend/src/ui/copy.ts`, `frontend/src/ui/viewModels.ts`, `frontend/src/ui/viewModels.test-d.ts`를 추가했다.
- 완료: `App`, `Generate`, `History`, `JobDetail`, `Pipeline`, `Ops` 화면의 주요 문구를 정상 한국어 기준으로 정리했다.
- 완료: `frontend/src/api/*`, `frontend/src/hooks/*`, `frontend/vite.config.ts`는 수정하지 않아 API contract를 유지했다.
- 검증: `npm run lint`, `npm run build`, API boundary diff 확인, mojibake 문자 검색을 통과했다.
- 브라우저 확인: `http://127.0.0.1:5173/generate`, `/history`, `/ops` 라우트 렌더링을 확인했다.
- 제한: Docker Desktop이 실행 중이 아니어서 `docker compose up -d db backend`가 실패했다. 따라서 실제 backend 데이터 기반 smoke test는 Docker Desktop 실행 후 다시 해야 한다.

다음 계획:

1. Docker Desktop을 켠 뒤 `docker compose up -d db backend`를 다시 실행한다.
2. `/generate`, `/history`, `/ops`에서 API 연결 상태와 실제 데이터 렌더링을 확인한다.
3. 필요한 경우 screenshot 기준으로 문구가 너무 길거나 겹치는 부분만 추가 조정한다.

---

## Current Findings

- 현재 프로젝트 위치: `C:\Users\PC\Desktop\AI_multimodal_platform`
- 현재 프론트 위치: `C:\Users\PC\Desktop\AI_multimodal_platform\frontend`
- 교체 후보 위치: `C:\Users\PC\Downloads\take-hom-assign (1)`
- `take-hom-assign (1)\App.tsx`, `main.tsx`, `index.css`, `api\*`, `pages\*`, `hooks\*`, `components\*`, `utils\*`는 현재 `frontend/src`와 같은 계열이다.
- `take-hom-assign (1)\src\*.jsx`는 별도 mock UI 프로토타입이다. 이 파일들은 실제 API를 호출하지 않고 `window` 전역과 mock data를 사용하므로 production 코드로 직접 복사하지 않는다.
- `take-hom-assign (1)\uploads\claude-design.md`에는 mojibake가 있으므로 문구 출처로 쓰지 않는다.
- 콘솔 출력 인코딩이 한글을 깨뜨려 보일 수 있으므로 최종 문구 검수는 브라우저 렌더링과 UTF-8 파일 저장 기준으로 한다.

## API Contract Safety Rules

이 리팩터 중 아래 파일은 API contract 기준선이다.

- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/api/asset.contract.ts`
- `frontend/src/api/history.contract.ts`
- `frontend/src/api/ops.contract.ts`
- `frontend/src/hooks/useAsset.ts`
- `frontend/src/hooks/useJob.ts`
- `frontend/src/hooks/usePipeline.ts`
- `frontend/vite.config.ts`

다음 export와 payload shape는 UI 작업에서 변경하지 않는다.

```ts
getHealth(): Promise<HealthResponse>
getOpsHealth(): Promise<OpsHealthResponse>
createGeneration(payload: GenerationCreateRequest): Promise<GenerationResponse>
retryGeneration(jobId: UUID): Promise<GenerationResponse>
listGenerations(params?: GenerationListParams): Promise<GenerationResponse[]>
getGeneration(jobId: UUID): Promise<GenerationResponse>
getAsset(assetId: UUID): Promise<AssetResponse>
deleteGeneration(jobId: UUID): Promise<void>
enhancePrompt(payload: PromptEnhanceRequest): Promise<PromptEnhancementResponse>
createPipeline(payload: PipelineCreateRequest): Promise<PipelineResponse>
getPipeline(parentJobId: UUID): Promise<PipelineResponse>
```

UI에서 필요한 표시 형식은 API type을 바꾸지 말고 view-model adapter로 흡수한다.

```ts
// frontend/src/ui/viewModels.ts
import type { JobResponse, JobState } from "../api/client";

export type JobCardViewModel = {
  id: string;
  shortId: string;
  mode: string;
  state: JobState;
  stateLabel: string;
  prompt: string;
  createdAt: string;
  assetCount: number;
};

export function toJobCardViewModel(job: JobResponse): JobCardViewModel {
  return {
    id: job.id,
    shortId: job.id.slice(0, 8),
    mode: job.mode.toUpperCase(),
    state: job.state,
    stateLabel: JOB_STATE_COPY[job.state],
    prompt: job.prompt,
    createdAt: new Date(job.created_at).toLocaleString("ko-KR"),
    assetCount: job.assets.length,
  };
}

export const JOB_STATE_COPY: Record<JobState, string> = {
  pending: "대기 중",
  enhancing: "프롬프트 향상 중",
  queued: "대기열",
  generating: "생성 중",
  polling: "결과 확인 중",
  downloading: "결과 저장 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};
```

## File Plan

- Create: `frontend/src/ui/copy.ts`
  - 화면 문구, 상태 라벨, 모드 라벨을 UTF-8 한국어로 관리한다.
- Create: `frontend/src/ui/viewModels.ts`
  - API response를 화면 표시용으로 변환한다.
- Create: `frontend/src/ui/viewModels.test-d.ts`
  - `tsc --noEmit`에서 contract drift를 잡기 위한 type-only guard를 둔다.
- Modify: `frontend/src/App.tsx`
  - 기존 라우터와 health check는 유지하고, shell copy와 layout만 정리한다.
- Modify: `frontend/src/pages/GeneratePage.tsx`
  - mock UI의 workspace 감성을 이식하되 `createGeneration`, `enhancePrompt`, `createPipeline` 호출은 기존 contract 그대로 사용한다.
- Modify: `frontend/src/pages/HistoryPage.tsx`
  - history table/card UI를 정리하고 `listGenerations`, `deleteGeneration`, `retryGeneration` contract를 유지한다.
- Modify: `frontend/src/pages/JobDetailPage.tsx`
  - 결과 preview, prompt diff, retry/I2V source flow를 view-model 기반으로 정리한다.
- Modify: `frontend/src/pages/PipelinePage.tsx`
  - parent/child job flow를 새 UI의 2단계 시각 구조로 반영한다.
- Modify: `frontend/src/pages/OpsPage.tsx`
  - dead-letter/repair 관련 현황을 유지하되 운영 화면 문구를 정상 한국어로 정리한다.
- Modify: `frontend/src/components/ui.tsx`, `frontend/src/components/icons.tsx`
  - 필요한 primitive만 현재 구조에 맞춰 추가한다. JSX 프로토타입의 전역 `I.*` 아이콘 방식은 가져오지 않는다.
- Modify: `frontend/src/index.css`
  - 기존 CSS를 유지하고 필요한 class만 추가한다. 외부 CDN, 이미지 asset, 새 binary는 추가하지 않는다.

## Task 1: Baseline Contract Guard

**Files:**
- Read: `frontend/src/api/client.ts`
- Read: `frontend/src/api/types.ts`
- Read: `frontend/src/api/*.contract.ts`
- Modify: none

- [ ] **Step 1: 현재 프론트 타입/빌드 기준선을 확인한다**

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform\frontend
npm run lint
npm run build
```

Expected:

```text
tsc --noEmit
tsc -b && vite build
```

둘 중 실패하면 UI 리팩터 전에 실패 원인을 기록한다. API contract 파일은 리팩터 중 임의 수정하지 않는다.

- [ ] **Step 2: API export 목록을 변경 금지 체크리스트로 고정한다**

검토 대상:

```powershell
rg -n "export async function|export type" C:\Users\PC\Desktop\AI_multimodal_platform\frontend\src\api
```

Expected:

```text
client.ts에 getHealth, getOpsHealth, createGeneration, retryGeneration, listGenerations,
getGeneration, getAsset, deleteGeneration, enhancePrompt, createPipeline, getPipeline이 남아 있어야 한다.
```

## Task 2: Korean Copy Registry

**Files:**
- Create: `frontend/src/ui/copy.ts`
- Modify: `frontend/src/App.tsx`
- Modify: page files only where they currently contain inline labels

- [ ] **Step 1: copy registry를 만든다**

Create `frontend/src/ui/copy.ts`:

```ts
import type { GenerationMode, JobState } from "../api/client";

export const APP_COPY = {
  brandName: "Vertex Studio",
  brandMeta: "크리에이티브 작업공간",
  nav: {
    generate: "생성",
    history: "기록",
    ops: "운영",
  },
  routes: {
    generate: { title: "생성", eyebrow: "작업공간 / 생성" },
    history: { title: "기록", eyebrow: "작업공간 / 기록" },
    ops: { title: "운영", eyebrow: "작업공간 / 운영" },
    jobDetail: { title: "작업 상세", eyebrow: "작업공간 / 작업" },
    pipeline: { title: "Pipeline", eyebrow: "작업공간 / Pipeline" },
  },
  health: {
    checking: "API 확인 중",
    unavailable: "API 연결 불가",
    connected: "API 연결됨",
    degraded: "API 저하됨",
  },
};

export const MODE_COPY: Record<GenerationMode | "pipeline", { title: string; short: string; description: string }> = {
  t2i: {
    title: "텍스트 → 이미지",
    short: "T2I",
    description: "텍스트 프롬프트로 Imagen 이미지 작업을 만듭니다.",
  },
  t2v: {
    title: "텍스트 → 영상",
    short: "T2V",
    description: "텍스트 프롬프트로 Veo 영상 작업을 만듭니다.",
  },
  i2v: {
    title: "이미지 → 영상",
    short: "I2V",
    description: "완성된 이미지 결과에 움직임을 더합니다.",
  },
  pipeline: {
    title: "T2I → I2V Pipeline",
    short: "PIPELINE",
    description: "이미지 parent 작업과 I2V child 작업을 함께 만듭니다.",
  },
};

export const JOB_STATE_COPY: Record<JobState, string> = {
  pending: "대기 중",
  enhancing: "프롬프트 향상 중",
  queued: "대기열",
  generating: "생성 중",
  polling: "결과 확인 중",
  downloading: "결과 저장 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};
```

- [ ] **Step 2: 깨진 문자열 검색을 정례화한다**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
rg -n "�|鍮|遺|怨|湲|二|洹|吏|移|쨌" frontend\src
```

Expected:

```text
No matches.
```

콘솔 인코딩 때문에 정상 한글이 깨져 보이는 경우가 있으므로, 최종 판단은 브라우저 화면과 UTF-8 파일 내용을 기준으로 한다.

## Task 3: View Model Adapter

**Files:**
- Create: `frontend/src/ui/viewModels.ts`
- Create: `frontend/src/ui/viewModels.test-d.ts`
- Modify: page files to consume adapters

- [ ] **Step 1: API response를 화면 전용 모델로 변환한다**

Create `frontend/src/ui/viewModels.ts`:

```ts
import type { AssetResponse, GenerationMode, JobResponse, JobState, PipelineResponse } from "../api/client";
import { JOB_STATE_COPY, MODE_COPY } from "./copy";

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

export function toAssetPreviewViewModel(asset: AssetResponse): AssetPreviewViewModel {
  const dimensions =
    asset.width && asset.height
      ? `${asset.width} × ${asset.height}`
      : asset.duration_sec
        ? `${asset.duration_sec}s`
        : "metadata pending";

  return {
    id: asset.id,
    kind: asset.kind,
    url: asset.url,
    label: asset.kind === "image" ? "Image Asset" : "Video Asset",
    meta: `${asset.mime} · ${dimensions}`,
  };
}

export function toJobSummaryViewModel(job: JobResponse): JobSummaryViewModel {
  return {
    id: job.id,
    shortId: job.id.slice(0, 8),
    mode: job.mode,
    modeLabel: MODE_COPY[job.mode].title,
    state: job.state,
    stateLabel: JOB_STATE_COPY[job.state],
    prompt: job.prompt,
    createdAt: new Date(job.created_at).toLocaleString("ko-KR"),
    updatedAt: new Date(job.updated_at).toLocaleString("ko-KR"),
    assets: job.assets.map(toAssetPreviewViewModel),
    isTerminal: ["completed", "failed", "cancelled"].includes(job.state),
    canRetry: job.state === "failed" || job.state === "cancelled",
    canUseAsI2V: job.mode === "t2i" && job.assets.some((asset) => asset.kind === "image"),
  };
}

export type PipelineViewModel = {
  id: string;
  parent: JobSummaryViewModel;
  child: JobSummaryViewModel;
};

export function toPipelineViewModel(pipeline: PipelineResponse): PipelineViewModel {
  return {
    id: pipeline.id,
    parent: toJobSummaryViewModel(pipeline.parent),
    child: toJobSummaryViewModel(pipeline.child),
  };
}
```

- [ ] **Step 2: type-only guard를 추가한다**

Create `frontend/src/ui/viewModels.test-d.ts`:

```ts
import type { JobResponse, PipelineResponse } from "../api/client";
import { toJobSummaryViewModel, toPipelineViewModel } from "./viewModels";

declare const job: JobResponse;
declare const pipeline: PipelineResponse;

const jobView = toJobSummaryViewModel(job);
const pipelineView = toPipelineViewModel(pipeline);

void jobView.id;
void jobView.stateLabel;
void pipelineView.parent.assets;
void pipelineView.child.canRetry;
```

- [ ] **Step 3: contract guard를 실행한다**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform\frontend
npm run lint
```

Expected:

```text
tsc --noEmit
```

No TypeScript errors.

## Task 4: App Shell Copy and Routing

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 라우팅은 유지하고 문구만 copy registry로 교체한다**

Rules:

```text
Keep routes:
/generate
/history
/ops
/jobs/:jobId
/pipelines/:pipelineId
```

Do not replace `BrowserRouter`, `QueryClientProvider`, `Routes`, `Route`, `Outlet`, or health query wiring.

- [ ] **Step 2: HealthIndicator의 API 호출은 그대로 둔다**

Required implementation behavior:

```ts
const health = useQuery({
  queryKey: ["health"],
  queryFn: getHealth,
  refetchInterval: 5000,
  retry: false,
});
```

`getHealth` signature와 response type은 바꾸지 않는다.

## Task 5: Generate Workspace Refactor

**Files:**
- Modify: `frontend/src/pages/GeneratePage.tsx`
- Read only: `C:\Users\PC\Downloads\take-hom-assign (1)\src\workspace.jsx`
- Read only: `C:\Users\PC\Downloads\take-hom-assign (1)\src\primitives.jsx`

- [ ] **Step 1: mock reducer를 production으로 가져오지 않는다**

Do not copy:

```js
const initialState = { ... };
function appReducer(state, action) { ... }
Object.assign(window, { MODELS, ASPECTS, DURATIONS, STYLES, HISTORY, MODE_META, STATE_META, mockEnhance });
```

Production source of truth remains React Query mutations:

```ts
const generationMutation = useMutation({ mutationFn: createGeneration });
const enhanceMutation = useMutation({ mutationFn: enhancePrompt });
const pipelineMutation = useMutation({ mutationFn: createPipeline });
```

- [ ] **Step 2: payload builders must emit existing API shapes**

Valid T2I payload:

```ts
{
  mode: "t2i",
  model,
  prompt,
  aspect_ratio: aspectRatio,
  number_of_images: numberOfImages,
  auto_enhance: false,
  enhancement_id: acceptedEnhancementId,
}
```

Valid T2V payload:

```ts
{
  mode: "t2v",
  model,
  prompt,
  aspect_ratio: aspectRatio,
  duration_sec: durationSec,
  auto_enhance: false,
  enhancement_id: acceptedEnhancementId,
}
```

Valid I2V payload:

```ts
{
  mode: "i2v",
  model,
  prompt,
  source_asset_id: sourceAssetId,
  aspect_ratio: aspectRatio,
  duration_sec: durationSec,
  auto_enhance: false,
  enhancement_id: acceptedEnhancementId,
}
```

Valid Pipeline payload:

```ts
{
  image_prompt: prompt,
  video_prompt: videoPrompt,
  image_model: imageModel,
  video_model: videoModel,
  image_aspect_ratio: imageAspectRatio,
  video_aspect_ratio: videoAspectRatio,
  duration_sec: durationSec,
}
```

- [ ] **Step 3: Prompt Enhance review UX는 유지한다**

Required behavior:

```text
사용자가 초안을 수락하기 전까지 main prompt는 바뀌지 않는다.
초안 textarea는 편집 가능해야 한다.
수락 시 enhancement_id가 다음 generation payload에 연결되어야 한다.
```

## Task 6: History and Job Detail Refactor

**Files:**
- Modify: `frontend/src/pages/HistoryPage.tsx`
- Modify: `frontend/src/pages/JobDetailPage.tsx`
- Read only: `C:\Users\PC\Downloads\take-hom-assign (1)\src\history.jsx`
- Read only: `C:\Users\PC\Downloads\take-hom-assign (1)\src\result.jsx`
- Read only: `C:\Users\PC\Downloads\take-hom-assign (1)\src\waiting.jsx`

- [ ] **Step 1: History query contract를 유지한다**

Required query:

```ts
listGenerations({
  mode,
  asset_kind,
  model,
  state,
  limit,
  offset,
});
```

Do not rename query params. Filters may change visually, but the `GenerationListParams` keys remain unchanged.

- [ ] **Step 2: delete/retry는 기존 mutations만 사용한다**

Required calls:

```ts
deleteGeneration(job.id);
retryGeneration(job.id);
```

Delete confirmation text can be rewritten, but the delete scope must remain single job plus stored assets.

- [ ] **Step 3: Job detail polling remains in `useJob`**

Do not implement custom `setInterval` polling in page code. Keep:

```ts
const jobQuery = useJob(jobId);
```

Polling behavior remains controlled by `useJob`.

## Task 7: Pipeline Refactor

**Files:**
- Modify: `frontend/src/pages/PipelinePage.tsx`
- Read only: `C:\Users\PC\Downloads\take-hom-assign (1)\src\pipeline.jsx`

- [ ] **Step 1: parent/child flow must use backend pipeline response**

Required query:

```ts
const pipelineQuery = usePipeline(parentJobId);
const view = pipelineQuery.data ? toPipelineViewModel(pipelineQuery.data) : null;
```

Do not synthesize child job state from local timers.

- [ ] **Step 2: visual stage labels are view-only**

Allowed labels:

```ts
const PIPELINE_STAGE_COPY = {
  parent: "1단계 · Imagen 이미지 생성",
  child: "2단계 · Veo I2V 영상 생성",
  done: "Pipeline 완료",
};
```

These labels must not alter `PipelineResponse`.

## Task 8: Ops Page Refactor

**Files:**
- Modify: `frontend/src/pages/OpsPage.tsx`

- [ ] **Step 1: Ops health contract를 유지한다**

Required query:

```ts
const opsHealth = useQuery({
  queryKey: ["ops-health"],
  queryFn: getOpsHealth,
  refetchInterval: 5000,
});
```

Do not rename `dispatch`, `jobs`, `outbox`, or `recent_failures` fields.

- [ ] **Step 2: Dead-letter/repair wording is UI-only**

Allowed display labels:

```ts
const OPS_COPY = {
  deadLetter: "Dead-letter",
  repair: "Repair",
  recentFailures: "최근 실패 작업",
  outbox: "Outbox",
};
```

No backend endpoint shape changes are allowed in this UI refactor.

## Task 9: Styling Migration

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/ui.tsx`
- Modify: `frontend/src/components/icons.tsx`

- [ ] **Step 1: CSS class names are added, not globally renamed**

Safe approach:

```css
.studio-panel { }
.studio-panel__header { }
.studio-control-row { }
.studio-status-timeline { }
.studio-result-preview { }
```

Avoid renaming existing high-traffic classes such as:

```text
app-shell
sidebar
topbar
workspace-frame
panel
badge
status-dot
```

- [ ] **Step 2: no external visual assets**

Do not add:

```text
remote CDN scripts
remote image URLs
binary videos
large screenshots
new font files
```

Use CSS tokens, existing SVG/icon components, and lightweight layout changes.

## Task 10: Verification

**Files:**
- No source files unless fixes are needed

- [ ] **Step 1: Static verification**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform\frontend
npm run lint
npm run build
```

Expected:

```text
tsc --noEmit
vite build exits with code 0
```

- [ ] **Step 2: API contract scan**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
git diff -- frontend/src/api frontend/src/hooks frontend/vite.config.ts
```

Expected:

```text
No diff, except optional type-only guard additions that do not change exported API calls.
```

- [ ] **Step 3: Korean copy scan**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
rg -n "�|鍮|遺|怨|湲|二|洹|吏|移|쨌" frontend\src
```

Expected:

```text
No matches.
```

- [ ] **Step 4: Browser smoke test**

Run backend and frontend, then verify:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
docker compose up -d db backend
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173/generate
http://localhost:5173/history
http://localhost:5173/ops
```

Expected:

```text
Generate 화면이 바로 열린다.
API health badge가 정상 표시된다.
Prompt Enhance가 기존 /api/prompts/enhance로 호출된다.
Generation 생성 payload가 기존 /api/generations contract를 따른다.
History, Job detail, Pipeline, Ops 화면에서 API error 없이 렌더링된다.
```

## Non-Goals

- Backend API endpoint 변경
- `frontend/src/api/client.ts` public function signature 변경
- `frontend/src/api/types.ts` response/request shape 변경
- Docker/Vite proxy 설정 변경
- Vertex/GCP/AWS credential 출력
- 외부 이미지, CDN, 새 binary asset 추가
- mock-only `src/*.jsx`를 production entry로 직접 사용

## Execution Order

1. Task 1로 기준선 확인
2. Task 2와 Task 3으로 copy/view-model 안전망 추가
3. Task 4로 shell 문구와 라우팅 정리
4. Task 5, Task 6, Task 7을 화면별로 하나씩 적용
5. Task 8 운영 화면 정리
6. Task 9 스타일 정리
7. Task 10 전체 검증

## Rollback Plan

문제가 생기면 API/hook 파일은 건드리지 않았다는 전제에서 UI 변경 파일만 되돌린다.

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
git diff -- frontend/src
```

롤백 대상은 다음 범위로 제한한다.

```text
frontend/src/App.tsx
frontend/src/pages/*
frontend/src/components/*
frontend/src/index.css
frontend/src/ui/*
```

`frontend/src/api/*`, `frontend/src/hooks/*`, `frontend/vite.config.ts`에 diff가 있으면 먼저 검토하고, API contract 변경이 아니라는 증거가 있을 때만 유지한다.
