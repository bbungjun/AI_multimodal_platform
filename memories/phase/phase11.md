제시해주신 **Phase 11 — 프론트엔드 계획(Frontend Plan)** 문서의 한글 번역본입니다. 작업 흐름과 기술 용어의 맥락을 살려 자연스럽게 번역했습니다.

# Phase 11 — 프론트엔드 계획

> 드래프트 저장일: 2026-05-23. Phase 11에서는 백엔드 변경 없이, 그리고 JSX 코드를 그대로 복사 붙여넣기 하지 않으면서, Claude 디자인 레퍼런스를 기존의 Vite + React + TypeScript 프론트엔드로 이식(Porting)합니다.
> 

## 범위 (Scope)

Phase 11은 현재 헬스 체크(Health-check)만 가능한 상태인 프론트엔드를 이미 완성된 백엔드 계약(API 엔드포인트)과 연동하여 실제로 사용할 수 있는 UI로 전환합니다:

- `POST /api/generations`, `GET /api/generations`, `GET /api/generations/{id}`
- `POST /api/prompts/enhance`
- `POST /api/pipelines`, `GET /api/pipelines/{parent_job_id}`
- `GET /api/health`

`uploads/*.jsx` 경로에 있는 Claude 디자인 파일들은 오직 **참고용**입니다. 실제 구현 시에는 기존 `frontend/src` 구조에 맞게 타입이 지정된 TSX 컴포넌트, 로컬 훅(Hooks), API 클라이언트 호출 코드로 새로 작성해야 합니다.

## 현재 프론트엔드 상태

- `frontend/src/App.tsx`는 헬스 체크 패널만 렌더링하고 있습니다.
- `frontend/src/api/client.ts`는 `getHealth()`만 노출하고 있습니다.
- `react-router-dom`과 `@tanstack/react-query`가 설치는 되어 있으나 아직 연결(Wiring)되지 않았습니다.
- Tailwind가 설치되어 있지만, `tailwind.config.*`나 `postcss.config.*` 파일이 없습니다.
- 기존 스타일링은 `frontend/src/index.css`에 일반 CSS(Plain CSS)로 작성되어 있습니다.

## Tailwind 관련 결정 사항

Phase 11에서는 **기존의 CSS 우선(CSS-first) 접근 방식을 유지**합니다.

- 단지 스택 라벨(Stack label)을 만족시키기 위해 필요하지도 않은 Tailwind 설정이나 PostCSS를 추가하지 마세요.
- 디자인 토큰, 레이아웃 규칙, 애니메이션은 `index.css`와 스코프가 지정된 컴포넌트 클래스 이름(scoped component class names)으로 이식합니다.
- 추후 다른 단계에서 유틸리티 클래스를 본격적으로 사용하게 될 경우를 대비해, 향후 최소한의 Tailwind 설정을 도입할 수 있는 여지는 남겨둡니다.
- 이렇게 함으로써 프론트엔드와 백엔드 계약을 연결하는 도중에 Claude 디자인의 인라인 스타일을 불완전한 Tailwind 시스템으로 억지로 변환하는 번거로움을 방지합니다.

## 이식할 디자인 요소

- `uploads/app.jsx`: 앱 셸(App shell), 사이드바, 상단 바, 루트 레벨 워크스페이스 레이아웃.
- `uploads/workspace.jsx`: 모드/모델 제어 장치, 프롬프트 콘솔, 시네마 프리뷰(Cinema preview).
- `uploads/primitives.jsx`: 버튼, 패널, 태그, 상태 표시 점(Status dot), 세그먼트 제어 장치(Segmented controls).
- `uploads/icons.jsx`: 타입이 지정된 TSX로 변환된 소형 인라인 아이콘 세트.
- `uploads/waiting.jsx`: 작업 상태 타임라인 및 실패 상태 표현 UI.
- `uploads/result.jsx`: 에셋 뷰어(Asset viewer), 메타데이터 레일(Metadata rail), I2V(이미지 투 비디오) 핸드오프 기능.
- `uploads/history.jsx`: 히스토리 테이블, 필터, 작업 상세 구성.
- `uploads/pipeline.jsx`: 상위 T2I(텍스트 투 이미지) 및 하위 I2V 단계 시각화.

## 레퍼런스 적용 시 위험 요소 (Reference Risks)

- 모의 리듀서(Mock reducer), 가짜 타이머, 가짜 히스토리, 가짜 진행률 및 `mockEnhance()` 코드를 모두 제거하세요.
- 디자인에 사용된 임시 모델 ID를 백엔드가 지원하는 실제 ID로 교체하세요:
    - `imagen-4.0-fast-generate-001`
    - `imagen-4.0-generate-001`
    - `imagen-4.0-ultra-generate-001`
    - `veo-3.0-fast-generate-001`
    - `veo-3.0-generate-001`
- 파이프라인(Pipeline)은 백엔드의 `GenerationMode`가 아니라, `/api/pipelines`를 기반으로 작동하는 **프론트엔드 워크플로우**로 취급하세요.
- 백엔드 상태를 직접 매핑하세요:
`pending`, `enhancing`, `queued`, `generating`, `polling`, `downloading`, `completed`, `failed`, `cancelled`.
- 백엔드에서 제공하는 에셋 URL과 ID만 사용하세요. 사용자 입력을 기반으로 파일 시스템 경로를 직접 빌드하지 마세요.

## Phase 11에서 제외 및 비활성화되는 기능

현재 백엔드에서 지원하지 않는 기능이므로, 프론트엔드에서 마치 구현된 것처럼 보여서는 안 됩니다:

- 업로드(Upload): 제외.
- 취소(Cancel): 비활성화 또는 숨김 처리.
- 글로벌 검색 / 커맨드 팔레트(Command palette): 제외.
- 설정(Settings) 및 라이브러리(Library) 섹션: 레이아웃 균형을 위해 필요한 경우에만 비활성화된 플레이스홀더로 숨김 또는 유지.
- 실시간 진행률 백분율(%): 가짜 퍼센트를 표시하는 대신 상태 기반의 타임라인을 사용하세요.
- 리믹스(Remix) 편의 기능: 명확하게 스코프가 정의되기 전까지는 제외.

## 구현 단위 (Implementation Units)

### Unit 1 — 프론트엔드 코어 + 디자인 셸 (Shell)

- 라우터(Router) 및 쿼리 클라이언트 프로바이더(Query client providers)를 추가합니다.
- 다음 라우트를 추가합니다:
    - `/` 및 `/generate`
    - `/jobs/:jobId`
    - `/history`
    - `/pipelines/:pipelineId`
- API 타입을 `src/api/types.ts`로 분리합니다.
- `src/api/client.ts`에 타입이 지정된 fetch 래퍼를 구현하고 헬스 체크, 생성(Generations), 프롬프트 향상, 파이프라인 관련 함수를 확장합니다.
- 디자인 레퍼런스로부터 앱 셸 컴포넌트(사이드바, 상단 바, 워크스페이스 프레임, 공통 UI 프리미티브, 아이콘)를 추가합니다.
- 셸의 링크는 실제 구현된 라우트로만 제한합니다.

### Unit 2 — 생성 (Generate) + 프롬프트 향상 (Prompt Enhance)

- 모드 선택기, 모델 피커, 프롬프트 입력창(Textarea), 모드별 파라미터가 포함된 `GeneratePage`를 구축합니다.
- `POST /api/generations`를 통한 T2I 및 T2V 생성을 지원합니다.
- I2V는 작업 상세 또는 히스토리 핸드오프를 통해 **실제로 완료된 이미지 에셋이 선택되었을 때만** 지원합니다.
- 프롬프트 향상(Enhancement) 흐름을 추가합니다:
    - `POST /api/prompts/enhance`를 호출합니다.
    - 원본/향상된 프롬프트/구성 요소를 검토하는 UI를 보여줍니다.
    - 향상된 프롬프트를 수정할 수 있도록 허용합니다.
    - 수락된 프롬프트 향상 결과가 선택한 모드/모델과 일치할 때만 `enhancement_id`를 전달합니다.
- `auto_enhance=false` 설정을 유지하며, 자동 향상 기능은 구현하지 않습니다.

### Unit 3 — 작업 상세 + 대기 + 결과 + I2V 소스 핸드오프

- 작업이 완료(터미널 상태)되기 전까지 2초 간격으로 React Query 폴링을 수행하는 `useJob(jobId)` 훅을 추가합니다.
- 상태 타임라인, 요청 메타데이터, 에러 표시, 완료된 에셋 뷰어가 포함된 `JobDetailPage`를 구축합니다.
- 백엔드 에셋 메타데이터와 URL을 사용하여 이미지/비디오를 렌더링합니다.
- 이미지 에셋이 있는 **완료된 T2I 작업에 대해서만** "I2V 소스로 사용(Use as I2V source)" 기능을 추가합니다.
- 핸드오프 시 생성 페이지로 다시 이동하며, 이때 `mode=i2v` 및 선택된 `source_asset_id`를 함께 넘겨줍니다.

### Unit 4 — 히스토리 + 파이프라인 UI

- `GET /api/generations`를 기반으로 `HistoryPage`를 구축합니다.
- 백엔드 쿼리 파라미터를 사용하여 모드, 모델, 상태별 필터를 추가합니다.
- `limit`와 `offset`을 사용하여 간단한 페이지네이션(Pagination)을 추가합니다.
- 생성 페이지 또는 별도의 컴팩트한 라우트 레벨 패널에 파이프라인 런처를 추가합니다:
`image_prompt`, `video_prompt`, 이미지/비디오 모델, 종횡비, 재생 시간 포함.
- `POST /api/pipelines`가 성공하면 `/pipelines/:parentJobId`로 이동합니다.
- `GET /api/pipelines/{parent_job_id}`를 사용하여 파이프라인 상세 폴링을 추가하고 상위/하위 단계 카드를 표시합니다.

### Unit 5 — 빌드 검증 + 문서 마무리

- `cd frontend && npm run build`를 실행합니다.
- `package.json`에 `lint` 스크립트가 포함되어 있는 경우에만 `cd frontend && npm run lint`를 실행합니다. (현재 프론트엔드에는 포함되어 있습니다.)
- 프론트엔드 빌드 검증을 위해 실제 Vertex, Gemini, Imagen, Veo 자격 증명(Credentials), `.env` 파일 또는 서비스 계정 값이 작동하거나 필요하지 않아야 합니다.
- 커밋 전 수행 사항:
    - `git status --short`를 실행합니다.
    - Phase 11 프론트엔드/문서 파일만 스테이징(Stage)합니다.
    - `git diff --cached --name-only`를 실행합니다.
    - 자동 생성된 빌드 산출물, 자격 증명, `.env`, `dist`, `node_modules`, `tsconfig.tsbuildinfo`, 또는 런타임 에셋이 스테이징되지 않았는지 확인합니다.

## 백엔드 변경 불가 정책 (Backend-No-Change Policy)

- 이후에 명시적인 스코프 변경 요청이 없는 한, Phase 11에서는 `backend/` 코드를 **절대 수정하지 마세요.**
- 프론트엔드 동작을 기존 백엔드 스키마 및 상태에 맞추어 어댑터 형태로 구현하세요.
- 자격 증명, 환경 변수 값, 서비스 계정 내용을 요구하거나 로그에 출력하지 마세요.
- 명확한 블로커(Blocker)가 발생하지 않는 한 새로운 프론트엔드 의존성(라이브러리)을 추가하지 마세요. 현재 사용 중인 React, Router, React Query, TypeScript, CSS를 우선하여 사용하세요.

## 권장하는 첫 번째 구현 단위

**Unit 1부터 시작하는 것을 권장합니다.** API 클라이언트, 타입이 정의된 DTO, 라우터, 쿼리 프로바이더, 그리고 셸(Shell) 구조가 단단히 잡혀야만 이후 Generate 페이지, 폴링 기능, History 및 파이프라인 UI를 안전하게 구현할 수 있습니다.