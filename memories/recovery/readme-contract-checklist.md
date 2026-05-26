# README 기능 계약 체크리스트

작성일: 2026-05-27

이 문서는 현재 복구된 workspace가 `README.md`에 적힌 주요 기능/API 설명과
얼마나 맞는지 확인한 체크리스트입니다. 목표는 화면을 원래 제출본과 똑같이
맞추는 것이 아니라, 기능 흐름과 검증 가능한 계약이 살아 있는지 확인하는 것입니다.

## 기준 상태

- Branch: `main`
- 이 문서 작성 전 기준 commit: `38a569b fix: restore history frontend parity`
- 최근 follow-up 반영 기준 commit: `33c7f83 docs: confirm cancel scope`
- 검증 기준 provider: `AI_PROVIDER=mock`
- 비용이 발생하는 Vertex/Gemini/Imagen/Veo live QA: 실행하지 않음
- 이 체크 중 Compose 상태: db/backend/frontend가 mock mode로 실행 중

## 판정 기준

- `검증됨`: 구현이 있고, 최근 mock 자동 테스트/API/browser smoke 중 하나로 확인됨
- `구현됨`: 코드 경로가 있고 lint/build 또는 테스트 근거가 있지만, 이 체크에서 해당
  사용자 흐름을 새로 끝까지 누르지는 않음
- `부분`: 관련 구현은 있으나 README 문장 기준으로 완전히 맞지는 않음
- `live 전용`: 실제 Vertex provider 실행이 필요해서 이번 복구 범위에서 제외함

## README 주요 기능 대조

| README 기능 | 현재 상태 | 근거 | 남은 확인 |
|---|---|---|---|
| Text-to-Image, Text-to-Video, Image-to-Video, T2I to I2V Pipeline | 검증됨 | `POST /api/generations`, `POST /api/pipelines`, job handler, mock T2I/T2V/I2V provider, mock pipeline smoke가 있음 | 실제 provider 결과 품질은 live 전용 |
| Imagen 4 / Veo 3 모델 선택 | 구현됨 | `GeneratePage.tsx` 모델 선택 UI, `generations.py`/`pipelines.py` 모델 family 검증 | 모든 모델 옵션을 브라우저에서 하나씩 누르는 smoke는 필요할 때만 진행 |
| 생성 옵션: image aspect ratio, image count, video duration, I2V source image | 검증됨 | Pydantic request schema, Generate 화면 옵션, pipeline payload, source asset 검증. T2I `number_of_images=4` mock smoke에서 4개 image asset 표시 확인 | 옵션 조합 전체 permutation smoke는 아직 안 함 |
| Prompt Enhancement review/edit/accept | 검증됨 | `POST /api/prompts/enhance`, mock enhancer, `EnhanceReviewPanel`, editable draft, keep original, accept draft, components 표시. Browser smoke에서 enhance -> draft edit -> accept -> generation submit with `enhancement_id` 확인 | 실제 Gemini 결과 품질은 live 전용 |
| Creativity Mode | 구현됨 | `faithful`, `balanced`, `imaginative` 옵션이 있고 `creativity_preset`으로 enhancer에 전달됨 | 실제 Gemini 결과 차이는 live 전용 |
| Job Detail polling/timeline/request summary/asset preview | 검증됨 | `useJob`이 active job을 2초 polling, `JobDetailPage.tsx`가 timeline/request summary/error/asset viewer를 렌더링함 | 실제 Vertex MP4 video detail playback은 live 전용 |
| I2V Source Context | 검증됨 | Pipeline detail은 child I2V가 대기/진행 중일 때 source image context를 보여줌. Generate 화면도 `source_asset_id`로 source image preview를 표시함. `JobDetailPage.tsx`는 standalone I2V non-completed job에서 `GET /api/assets/{source_asset_id}`로 source image를 조회해 preview로 보여줌 | 실제 live I2V 진행 중 상태는 비용 때문에 제외 |
| Result Preview와 image-to-I2V handoff | 검증됨 | `AssetViewer`가 image/video asset을 표시하고, 완료된 image job에는 `Start I2V` 버튼이 있음. T2I multi-image gallery smoke에서 4개 image card와 각 image별 I2V handoff를 확인함 | 실제 Vertex image/video 품질은 live 전용 |
| Pipeline parent/child linkage | 검증됨 | parent T2I와 blocked child I2V 생성, parent image asset 준비 후 child unblock, mock pipeline parent/child completed 확인 | 실제 Veo pipeline 품질은 live 전용 |
| History filters/previews | 검증됨 | mode/state/model/page size/asset type filter가 있고, browser smoke에서 `Asset type -> Videos` 필터와 terminal `Delete` 버튼을 확인함 | mock MP4는 실제 재생 영상이 아니라 `No thumbnail` fallback이 보일 수 있음 |
| Terminal job deletion과 active dependent 보호 | 검증됨 | backend delete API가 terminal-only, active dependent 차단, terminal dependent detach를 처리하고 테스트가 있음. History delete UI도 복구됨. Browser smoke에서 disposable completed job을 History에서 삭제하고 API 404를 확인함 | 기존 review job은 삭제하지 않음 |

## README API 표 대조

| API | 현재 상태 | 근거 |
|---|---|---|
| `GET /api/health` | 검증됨 | frontend proxy 기준 `ok=true`, `ready=true`, `vertex.status=mock_provider` 확인 |
| `POST /api/prompts/enhance` | 검증됨 | backend 테스트와 mock enhancer 경로가 있고, 실제 Vertex 호출 없이 동작 |
| `POST /api/generations` | 검증됨 | T2I 생성, enhancement 연결, model/source 검증 테스트가 있고 mock T2I/T2V/I2V provider 경로가 있음 |
| `GET /api/generations` | 검증됨 | `mode`, `state`, `model`, `asset_kind`, `limit`, `offset` query를 지원하고 API smoke에서 최근 job 목록 확인 |
| `GET /api/generations/{job_id}` | 검증됨 | asset DTO와 404 테스트가 있고 Job Detail이 이 route를 사용함 |
| `DELETE /api/generations/{job_id}` | 구현됨 | terminal 삭제, non-terminal 거절, active dependent 보호, terminal dependent detach 테스트가 있음 |
| `POST /api/pipelines` | 검증됨 | backend 테스트와 mock pipeline smoke가 parent/blocked-child 생성 및 완료 흐름을 확인 |
| `GET /api/pipelines/{parent_job_id}` | 검증됨 | parent/child 응답과 404 테스트가 있고 Pipeline page가 polling함 |
| `GET /api/assets/{asset_id}` | 검증됨 | asset DTO/404 backend route와 테스트가 있음. Generate/JobDetail source preview가 `useAsset`으로 이 route를 사용함 |
| `GET /files/{job_uuid}/{filename}` | 검증됨 | safe streaming, unsafe path 차단, delete helper, single byte-range `206 Partial Content` 테스트가 있음 |
| `POST /api/generations/{job_id}/cancel` | 복구 제외 | README API 표에 없고, 후반 제출 문맥에서 user-facing cancel API/UI는 구현하지 않는 것으로 확인됨. `cancelled`는 state machine terminal state로만 유지 |

## 이번 체크에서 실행한 비용 없는 확인

```powershell
git status --short --branch
git diff --cached --name-only

Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health" -Method Get
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations?limit=3" -Method Get

cd frontend
npm run lint
npm run build
```

확인 결과:

- 시작 시 git 상태는 `main...origin/main`, staged 파일 없음
- `/api/health`는 mock provider readiness를 반환함
- `/api/generations?limit=3`는 asset을 가진 최근 completed T2I/I2V job을 반환함
- History 복구 후 `npm run lint` 통과
- History 복구 후 `npm run build` 통과
- Browser History smoke에서 확인한 내용:
  - `Asset type` 필터 표시
  - `Videos` 선택 시 video asset job만 표시
  - terminal row에 `Delete` 표시
  - blocking console error 없음
- Browser Job Detail smoke에서 disposable failed I2V job을 만들어 확인한 내용:
  - standalone I2V Job Detail에 `Source image context` 표시
  - source asset이 `/files/.../output.png` 이미지로 렌더링됨
  - blocking console error 없음
  - smoke 후 disposable job 삭제 확인
- Browser Prompt Enhancement smoke에서 확인한 내용:
  - `Enhance prompt` 클릭 후 `Review Enhanced Prompt` 패널 표시
  - enhanced draft를 직접 수정한 뒤 `Accept draft` 클릭
  - accepted prompt가 Request Builder main prompt로 반영됨
  - `Generate` 제출 후 Job Detail로 이동
  - 생성 job `07a82dbc-12fe-400c-bcbe-2c2ac7c5aad5`가 `completed` 상태가 됨
  - API 응답에서 `enhancement_id=bb7509b1-3911-4067-b7de-ba612737d0b7` 연결 확인
  - 최종 job prompt가 accepted edited prompt와 일치함
  - image asset 1개 생성 및 `/files/.../output.png` 로드 확인
  - blocking console error 없음
- Browser History Delete smoke에서 확인한 내용:
  - disposable T2I job `d068f55e-7483-4dd6-aaaf-918bb32f98cf` 생성
  - job이 `completed`, image asset 1개 상태가 될 때까지 확인
  - History에서 해당 row의 `Delete` 버튼 표시 확인
  - 실제 Delete 클릭 후 확인창 승인
  - History row가 사라짐
  - `GET /api/generations/d068f55e-7483-4dd6-aaaf-918bb32f98cf`가 `404` 반환
  - blocking console error 없음
- Browser T2I multi-image / per-image I2V smoke에서 확인한 내용:
  - mock T2I job `092d2907-56e2-49f7-9bdb-0b75c9eeb97a`가 image asset 4개 반환
  - Job Detail에 `4 Image Results Ready`, Image 1~4, 각 `Start I2V` 표시
  - Image 2의 `Start I2V` 클릭 후
    `/generate?mode=i2v&source_asset_id=da2b17d8-6cf9-4872-a779-2a92d90c22aa`
    이동 확인
  - Generate 화면에 선택한 source image preview 표시
  - motion prompt 입력 후 I2V `Generate` 버튼 enabled 확인
- Cancel scope 확인 결과:
  - `cancelled` state는 terminal state와 deletion 대상 상태로 유지
  - `POST /api/generations/{job_id}/cancel`과 cancel button은 최종 제출 확인 범위에
    없으므로 복구 제외

최근 backend 회귀 검증 근거:

- latest full backend pytest: `98 passed`
- latest frontend lint/build: 통과
- `/files` Range edge, Veo failure classification, model validation, retry/rate limiter
  contract 테스트가 mock/fake-only로 복구됨

## 이번 체크에서 제외한 것

- 실제 Vertex/Gemini/Imagen/Veo 호출
- 실제 provider 인증, quota, billing, region/model access
- 실제 Imagen/Veo 결과 품질과 latency
- 원래 제출 UI와의 pixel-perfect 비교
- 현재 review data를 지우는 브라우저 delete 클릭

## 다음 후보 작업

추천 순서:

1. 과거 pytest 229개와의 차이는 숫자 자체보다 계약 영역별로 봅니다. 지금은 테스트 수를
   무작정 맞추기보다 빠진 고가치 contract를 찾는 쪽이 더 중요합니다.
2. 추가 비용 없는 후보는 Prompt Enhancement/History browser smoke 절차를 별도
   runbook으로 분리하거나, 남은 P2 backend edge case 중 우선순위를 다시 정하는 것입니다.
