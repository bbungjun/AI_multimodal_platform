# CreativeOps Screenshot UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 첨부 screenshot의 CreativeOps Studio 화면을 기준으로 `/generate` UI를 실제 production React 화면에 반영한다.

**Architecture:** backend, API client, React Query hooks는 고정하고, App shell과 Generate view 계층만 재구성한다. mock prototype의 reducer, `window` 전역, fake history data는 가져오지 않고, 현재 `createGeneration`, `enhancePrompt`, `createPipeline`, `useAsset` 호출을 그대로 사용한다.

**Tech Stack:** Vite, React 18, TypeScript strict mode, React Router, TanStack React Query, existing CSS, existing FastAPI contract.

---

## Non-Negotiable Constraints

- `backend/**` 수정 금지.
- `frontend/src/api/**` 수정 금지.
- `frontend/src/hooks/**` 수정 금지.
- `frontend/vite.config.ts`, Docker, infra 설정 수정 금지.
- screenshot 기준의 큰 구조 변경은 Task 단위로 사용자 승인 후 진행한다.
- mock prototype의 `src/*.jsx`를 그대로 복사하지 않는다.
- API payload shape는 기존 구현 그대로 유지한다.

## Current Target

사용자가 기대한 화면은 다음 구조다.

- 좌측 고정 sidebar: `CreativeOps Studio`, 작업공간 nav, 시스템 nav, Vertex 상태 카드, 사용자 카드.
- 상단 bar: `CREATIVEOPS / 생성`, 검색 input 스타일, 모델 선택 pill, 설정 icon.
- 중앙 preview: 넓은 검은 cinema stage, 중앙 prompt title, 모드/비율/상태 metadata.
- 상단 mode tabs: T2I, T2V, I2V, Pipeline.
- 하단 composer: prompt text, 비율/style chips, 향상 버튼, 생성 버튼.
- 우측 별도 설정 panel은 screenshot에는 없으므로 제거하거나 fold/chip 형태로 흡수한다.

## Existing Baseline

- 현재 `/generate`는 `frontend/src/pages/GeneratePage.tsx`에서 `page-grid--generate`를 사용한다.
- 현재 App shell은 `frontend/src/App.tsx`의 `AppShell`에서 sidebar/topbar를 그린다.
- 현재 API 호출은 `GeneratePage.tsx` 안의 `submitGeneration`, `runEnhance`, `acceptEnhancement`가 담당한다.
- 1차 시도에서 `studio-generate` CSS와 command bar가 추가되었지만 screenshot과 다른 2-column panel 구조가 남아 있다.

## Execution Status - 2026-06-14

- 완료: Task 1 App shell을 CreativeOps sidebar/topbar 구조로 변경했다.
- 완료: Task 2 `/generate`를 mode tabs, single cinema stage, bottom composer 구조로 재구성했다.
- 완료: Task 3 Prompt Enhance review를 composer 아래 drawer 형태로 변경했다.
- 완료: Task 4 desktop/tablet/mobile responsive CSS를 추가했다.
- 완료: Task 5 `npm run lint`, `npm run build`, protected-file guard, `/api/health` smoke check를 통과했다.
- 재확인: 2026-06-14에 `npm run lint`, `npm run build`, `git diff -- backend frontend/src/api frontend/src/hooks frontend/vite.config.ts docker-compose.yml docker-compose.vertex.yml`, `http://127.0.0.1:5173/api/health`를 다시 실행했다.
- 완료: Task 6 사용자 승인 후 History, Ops, Pipeline, Job Detail에 CreativeOps hero/status surface를 적용했다. backend/API/hooks는 수정하지 않았다.

## Verification Evidence - 2026-06-14

- `frontend`에서 `npm run lint` 실행: `tsc --noEmit` exit code 0.
- `frontend`에서 `npm run build` 실행: `tsc -b && vite build` exit code 0.
- repo root에서 `git diff -- backend frontend/src/api frontend/src/hooks frontend/vite.config.ts docker-compose.yml docker-compose.vertex.yml` 실행: 출력 없음.
- `http://127.0.0.1:5173/api/health` smoke check: `ok: true`, `ready: true`, `db: up`, `vertex.status: mock_provider`.
- Playwright snapshot으로 `/generate` 확인: CreativeOps sidebar/topbar, T2I/T2V/I2V/PIPELINE tabs, cinema stage, composer, API badge가 렌더링됨.
- Playwright console 확인: React Router future warning 2개와 `favicon.ico` 404만 확인됨. UI refactor로 인한 React runtime error 또는 TypeError는 없음.

## File Boundaries

### Allowed To Modify

- `frontend/src/App.tsx`
  - CreativeOps screenshot과 맞는 sidebar/topbar shell로 변경한다.
  - 기존 route 목록은 유지한다.
  - `HealthIndicator`의 `getHealth` query는 유지한다.

- `frontend/src/pages/GeneratePage.tsx`
  - 화면 구조를 screenshot형 single-workspace layout으로 재구성한다.
  - 기존 mutation과 payload builder는 유지한다.
  - `mode`, `model`, `prompt`, `aspectRatio`, `durationSec`, `numberOfImages`, `creativityPreset`, `enhanceReview` state는 유지한다.

- `frontend/src/index.css`
  - CreativeOps shell, screenshot-style generate layout, responsive behavior를 추가한다.
  - 기존 History/Ops/Pipeline 화면이 크게 깨지지 않도록 class scope를 분리한다.

- `frontend/src/ui/copy.ts`
  - 필요한 표시 문구만 추가한다.

### Not Allowed To Modify

- `backend/**`
- `frontend/src/api/**`
- `frontend/src/hooks/**`
- `frontend/vite.config.ts`
- `docker-compose*.yml`
- `infra/**`

## API Contract Guard

구현 전후에 다음 diff가 비어 있어야 한다.

```powershell
git diff -- backend frontend/src/api frontend/src/hooks frontend/vite.config.ts docker-compose.yml docker-compose.vertex.yml
```

예외:

- 이미 존재하던 `infra/aws/ecs-cluster.tf`의 CloudWatch container insights 비활성화 diff는 이번 UI 작업과 무관하므로 건드리지 않는다.
- infra diff는 별도로 확인하되, 이번 UI 구현에서 새 infra 변경을 추가하지 않는다.

## Task 1: App Shell을 CreativeOps Layout으로 변경

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/index.css`

- [x] **Step 1: App shell 변경 전 API guard를 실행한다**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
git diff -- backend frontend/src/api frontend/src/hooks frontend/vite.config.ts docker-compose.yml docker-compose.vertex.yml
```

Expected:

```text
No output.
```

Existing unrelated infra diff can be checked separately:

```powershell
git diff -- infra/aws/ecs-cluster.tf
```

Expected:

```text
Only the existing containerInsights disabled change, with no new UI-related infra edits.
```

- [x] **Step 2: Sidebar copy와 nav 구조를 screenshot 기준으로 바꾼다**

Required visible labels:

```text
CreativeOps
STUDIO · v1.0
작업공간
생성
기록
운영
시스템
모델
템플릿
설정
VERTEX · 정상
S. Kim
personal workspace
```

Implementation rule:

```ts
const navItems = [
  { to: "/generate", label: "생성", icon: SparkleIcon },
  { to: "/history", label: "기록", icon: HistoryIcon },
  { to: "/ops", label: "운영", icon: CpuIcon },
];
```

Routes remain unchanged:

```tsx
<Route path="generate" element={<GeneratePage />} />
<Route path="history" element={<HistoryPage />} />
<Route path="ops" element={<OpsPage />} />
<Route path="jobs/:jobId" element={<JobDetailPage />} />
<Route path="pipelines/:pipelineId" element={<PipelinePage />} />
```

- [x] **Step 3: Topbar를 breadcrumb + search + model/status area로 바꾼다**

Generate route should display:

```text
CREATIVEOPS / 생성
작업, 프롬프트, asset 검색...
```

Health indicator remains powered by:

```ts
useQuery({
  queryKey: ["health"],
  queryFn: getHealth,
  refetchInterval: 5000,
  retry: false,
});
```

- [x] **Step 4: Shell CSS를 추가한다**

Add scoped classes:

```css
.creative-shell { }
.creative-sidebar { }
.creative-brand { }
.creative-nav { }
.creative-system-card { }
.creative-main { }
.creative-topbar { }
.creative-search { }
.creative-workspace { }
```

The shell must still support `/history`, `/ops`, `/jobs/:jobId`, and `/pipelines/:pipelineId`.

## Task 2: Generate 화면을 Screenshot Layout으로 재구성

**Files:**
- Modify: `frontend/src/pages/GeneratePage.tsx`
- Modify: `frontend/src/index.css`

- [x] **Step 1: 기존 payload builder를 그대로 보존한다**

Do not change:

```ts
createGeneration(payload)
createPipeline(payload)
enhancePrompt(payload)
```

Valid T2I payload remains:

```ts
{
  mode: "t2i",
  prompt,
  model,
  auto_enhance: false,
  aspect_ratio: aspectRatio,
  number_of_images: numberOfImages,
  enhancement_id: usableEnhancementId,
}
```

Valid T2V payload remains:

```ts
{
  mode: "t2v",
  prompt,
  model,
  auto_enhance: false,
  aspect_ratio: aspectRatio,
  duration_sec: durationSec,
  enhancement_id: usableEnhancementId,
}
```

Valid I2V payload remains:

```ts
{
  mode: "i2v",
  prompt,
  model,
  auto_enhance: false,
  source_asset_id: sourceAssetId,
  aspect_ratio: aspectRatio,
  duration_sec: durationSec,
  enhancement_id: usableEnhancementId,
}
```

Valid Pipeline payload remains:

```ts
{
  image_prompt: prompt,
  video_prompt: pipelineVideoPrompt,
  image_model: pipelineImageModel,
  video_model: pipelineVideoModel,
  image_aspect_ratio: pipelineImageAspectRatio,
  video_aspect_ratio: pipelineVideoAspectRatio,
  duration_sec: durationSec,
}
```

- [x] **Step 2: Layout을 screenshot의 single workspace로 바꾼다**

Target DOM structure:

```tsx
<div className="creative-generate">
  <div className="creative-mode-tabs">...</div>
  <section className="creative-stage">...</section>
  <form className="creative-composer">...</form>
</div>
```

Do not keep the old two-column visual split:

```text
cinema panel left + request configuration panel right
```

- [x] **Step 3: Mode tabs를 상단 compact pill 형태로 만든다**

Visible tab labels:

```text
T2I
T2V
I2V
PIPELINE
```

Each tab still calls:

```ts
setMode(item.mode)
```

- [x] **Step 4: Cinema stage를 중심 UI로 만든다**

Stage must show:

```text
대기
prompt preview title
T2I · 16:9 · 대기
```

Rules:

- `prompt.trim()`이 있으면 한국어/영어 그대로 표시한다.
- prompt가 비어 있으면 `제목 없는 장면` 표시.
- `mode === "i2v" && sourceAssetId`인 경우 `SourceImageCinema` preview를 사용한다.
- 생성 중 상태는 mutation pending으로만 표현한다. fake progress timer를 만들지 않는다.

- [x] **Step 5: Bottom composer로 prompt와 action을 이동한다**

Composer must include:

```text
prompt textarea
비율 chip/select
스타일 chip 또는 creativity select
향상 button
생성 button
```

The composer submit remains:

```tsx
<form onSubmit={(event) => {
  event.preventDefault();
  submitGeneration();
}}>
```

- [x] **Step 6: Advanced settings를 compact controls로 흡수한다**

Screenshot에는 우측 설정 panel이 없으므로 기존 설정은 아래처럼 배치한다.

- model: topbar 또는 composer compact select
- aspect ratio: composer chip/select
- duration: composer chip/select when mode is not `t2i`
- number of images: composer chip/select when mode is `t2i`
- pipeline image/video model: pipeline mode에서 compact grid로만 표시

## Task 3: Prompt Enhance Review를 Screenshot 톤에 맞춘다

**Files:**
- Modify: `frontend/src/pages/GeneratePage.tsx`
- Modify: `frontend/src/index.css`

- [x] **Step 1: 기존 enhance behavior를 유지한다**

Required behavior:

```text
사용자가 초안을 수락하기 전까지 main prompt는 변경되지 않는다.
초안 textarea는 편집 가능하다.
수락 시 enhancement_id가 다음 generation payload에 연결된다.
```

- [x] **Step 2: Review panel을 composer 아래 drawer로 표시한다**

Target structure:

```tsx
{enhanceReview && (
  <section className="creative-enhance-drawer">
    ...
  </section>
)}
```

Visible actions:

```text
버리기
원본 유지
초안 수락
```

## Task 4: Responsive Behavior

**Files:**
- Modify: `frontend/src/index.css`

- [x] **Step 1: Desktop 기준을 screenshot에 맞춘다**

Desktop target:

```text
sidebar width: about 226px
topbar height: about 52px
stage min-height: 520px
composer fixed below stage within same page flow
```

- [x] **Step 2: Tablet/mobile에서는 stack한다**

Rules:

- sidebar becomes horizontal/top section under `920px`.
- stage height reduces under `640px`.
- composer buttons remain visible and do not overflow.
- text must not overlap inside buttons, tabs, or chips.

## Task 5: Verification

**Files:**
- No source files unless fixes are needed.

- [x] **Step 1: Static verification**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform\frontend
npm run lint
npm run build
```

Expected:

```text
tsc --noEmit passes
vite build exits with code 0
```

- [x] **Step 2: API/backend guard**

Run:

```powershell
cd C:\Users\PC\Desktop\AI_multimodal_platform
git diff -- backend frontend/src/api frontend/src/hooks frontend/vite.config.ts docker-compose.yml docker-compose.vertex.yml
```

Expected:

```text
No output.
```

- [x] **Step 3: Browser QA**

Open:

```text
http://127.0.0.1:5173/generate
```

Expected:

```text
CreativeOps screenshot와 같은 shell/stage/composer 구조가 보인다.
API badge가 연결됨으로 표시된다.
T2I/T2V/I2V/PIPELINE tab 전환이 된다.
Prompt Enhance button이 기존 API를 호출한다.
Generate button이 기존 generation/pipeline API를 호출한다.
```

- [x] **Step 4: Console check**

Allowed console noise:

```text
React Router future flag warning
favicon.ico 404
```

Not allowed:

```text
React runtime errors
TypeError
API payload validation errors caused by UI refactor
```

## Task 6: Approval Gate Before Next Pages

**Files:**
- No source changes.

- [x] **Step 1: User QA for `/generate`**

User reviews `/generate` live.

Proceed only after user says the Generate page is directionally correct.

- [x] **Step 2: Plan next page separately**

Next page order:

```text
1. History
2. Ops
3. Pipeline
4. Job Detail
```

Each page gets a short approval checkpoint before large layout changes.

## Rollback Plan

If the screenshot UI direction is rejected, rollback only frontend visual files:

```powershell
git diff -- frontend/src/App.tsx frontend/src/pages/GeneratePage.tsx frontend/src/index.css
```

Do not rollback unrelated existing changes:

```text
infra/aws/ecs-cluster.tf
frontend/src/ui/*
ui_refactor_plan.md
other page copy changes
```

## Execution Notes

- The screenshot target is visually closer to `C:\Users\PC\Downloads\take-hom-assign (1)\screenshots\01-generate.png` than the current production screen.
- Use the screenshot as visual reference, not the mock JSX as source code.
- Keep implementation incremental: shell first, generate layout second, enhance drawer third, responsive polish last.
