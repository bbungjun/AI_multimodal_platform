# krafton_assignment_14 요약

## 핵심 주제

최종 README 작성을 위해 구현 사실을 read-only로 검증하고, 문서에 넣어도 되는 표현과 빼야 할 표현을 분리한 세션입니다. API, Docker Compose, job runner, Vertex/retry, state/storage/pipeline, 주요 기능을 fact check 문서로 나누어 확인했고, AI_COLLABORATION.md의 큰 방향도 함께 정리했습니다.

## 주요 키워드

- final README
- read-only fact check
- Docker Compose
- `VITE_ALLOWED_HOSTS`
- API endpoint table
- `auto_enhance` 미지원 흐름
- in-process asyncio runner
- `FOR UPDATE SKIP LOCKED`
- single `google-genai`
- no GCS
- Veo polling resume
- state machine
- storage path safety
- pipeline linking
- feature fact check
- AI_COLLABORATION direction

## 복구에 중요한 내용

- 현재 README가 과제 원문 brief라면 최종 제출용으로는 위험하다는 판단이 명확해졌습니다.
  - 최종 README는 과제 설명 반복이 아니라 “이 앱을 어떻게 실행하고, 무엇을 구현했고, 어떤 기술 판단을 했는가”를 보여주는 프로젝트 문서여야 합니다.
  - README와 AI_COLLABORATION은 역할을 나누어야 합니다. README는 실행/구조/기능/테스트 중심, AI_COLLABORATION은 설계 판단과 AI 협업/검증 중심입니다.
- README 작성 전 read-only fact check를 여러 문서로 나누어 수행하는 전략이 확정되었습니다.
  - API surface: `docs/readme-api-factcheck.md`
  - runner/job lifecycle: `docs/readme-runner-factcheck.txt`
  - Vertex/retry/Veo/Gemini: `docs/readme-vertex-retry-factcheck.txt`
  - state/storage/pipeline/delete: `docs/readme-state-storage-pipeline-factcheck.txt`
  - feature surface: `docs/readme-features-factcheck.txt`
  - 이 문서들은 README 작성 근거로 남길 수 있는 자료이며, final README 자체에는 파일명을 나열하지 않는 편이 안전합니다.
- Docker Compose README 문구가 정리되었습니다.
  - Compose는 `db`, `backend`, `frontend`를 함께 실행합니다.
  - backend는 `8000`, frontend는 `5173`으로 노출되고 Postgres는 compose 내부 네트워크에서 사용합니다.
  - service account JSON은 host path를 `GOOGLE_APPLICATION_CREDENTIALS_HOST`로 지정하고 backend 컨테이너에서는 `/secrets/sa.json`로 read-only mount됩니다.
  - `VITE_API_BASE=`는 relative `/api`, `/files`를 사용하게 하고, `VITE_API_PROXY_TARGET=http://backend:8000`은 Vite dev proxy 대상입니다.
  - `VITE_ALLOWED_HOSTS`는 Docker Compose와 Vite config에서 실제 사용되므로 README에 넣어도 됩니다.
- API README 문구의 안전 기준이 정리되었습니다.
  - endpoint 표는 health, prompt enhance, generations create/list/detail/delete, pipelines create/detail, assets detail, files streaming을 중심으로 씁니다.
  - generation payload 예시에서 `auto_enhance`는 빼는 것이 안전합니다. 내부 schema에 남아 있어도 `true`는 지원 기능처럼 보이면 안 됩니다.
  - `/api/prompts/enhance`를 먼저 호출하고, 사용자가 수락/수정한 prompt와 선택적 `enhancement_id`로 `/api/generations`를 호출하는 흐름이 공식 지원 흐름입니다.
- runner/architecture README 문구가 확정되었습니다.
  - FastAPI application lifespan에서 storage/DB schema 초기화 후 in-process asyncio job runner를 시작합니다.
  - runner는 `pending`이고 `blocked=false`인 job을 Postgres에서 `FOR UPDATE SKIP LOCKED`로 claim하고 `queued`로 전이한 뒤 handler task를 실행합니다.
  - 별도 Celery/Redis 없이 단일 인스턴스 과제 범위에 맞춘 구조라는 점이 핵심입니다.
  - concurrency는 설정값과 `asyncio.Semaphore`로 제한하며, Imagen/Veo 호출 전 model별 sliding-window rate limiter를 통과합니다.
  - Veo job은 polling 단계에서 operation name을 저장하고, runner 재시작 시 resumable polling job은 저장된 operation name으로 재개할 수 있습니다.
- Vertex/retry README 문구가 정리되었습니다.
  - Imagen, Veo, Gemini 모두 `google-genai`의 shared Vertex client 경로를 사용합니다.
  - Imagen은 inline image bytes를 asset으로 저장합니다.
  - Veo는 `output_gcs_uri` 없이 operation 결과의 video bytes를 읽어 로컬 `DATA_DIR`에 저장합니다.
  - 초기 Imagen 생성 호출과 초기 Veo submit 호출은 bounded retry helper를 사용합니다.
  - Veo polling은 generic retry helper가 아니라 operation error, safety-filtered result, missing output을 public error code로 분류하는 쪽이 핵심입니다.
  - Gemini prompt enhancement는 runner job이 아니라 별도 API 흐름이며, malformed JSON에 대한 1회 strict retry가 있습니다.
- state/storage/pipeline/delete README 문구가 정리되었습니다.
  - Job lifecycle은 명시적인 state machine으로 관리하고 runner/handler의 상태 변경은 `transition(...)`으로 검증 및 `state_history` 기록을 남깁니다.
  - asset 파일은 `DATA_DIR/{job_uuid}/{filename}` 형태이며 storage helper를 통해 UUID job directory, filename, containment를 검증합니다.
  - T2I -> I2V pipeline은 parent T2I job과 blocked I2V child job을 함께 생성합니다.
  - parent image asset이 준비되기 전에는 child가 runner 대상이 아니며, parent 완료 후 image asset을 child `source_asset_id`로 연결하고 `blocked=false`로 바꿉니다.
  - deletion은 terminal job 중심이고, active dependent job이 있는 경우 보호해야 합니다.
- README에 쓰면 안 되는 표현도 정리되었습니다.
  - 모든 Vertex 호출이 retry된다고 쓰면 안 됩니다.
  - Gemini가 active rate limiter로 보호된다고 쓰면 안 됩니다.
  - Veo가 GCS를 사용한다고 쓰면 안 됩니다.
  - prompt enhancement가 runner job으로 처리된다고 쓰면 안 됩니다.
  - pipeline child가 생성 즉시 실행 가능하다고 쓰면 안 됩니다.
  - progress percent/queue position/ETA가 실제 구현되어 있다고 쓰면 안 됩니다.
- AI_COLLABORATION.md 방향도 정리되었습니다.
  - Q1 후보는 Veo long-running operation 실패 분류가 가장 강합니다.
  - Q2는 state machine, API contract, credential/path safety, mock-only tests, provider error classification, DB/file consistency, 실제 UX 검증을 중심으로 합니다.
  - Q3는 Creativity Mode와 prompt enhancement review-first 흐름을 사용자가 조정한 사례가 가장 적합합니다.

## 원문에서 찾아볼 위치

- 최신 상태 handoff와 문서 방향: 대략 134~310
- README가 project docs로 바뀌어야 한다는 판단: 대략 475~498
- Docker Compose/환경 변수 문구 정리: 대략 806~1057
- README read-only fact check 지시와 결과: 대략 1063~1231
- API section 정리: 대략 1421~1806
- runner/job lifecycle fact check와 README 문구: 대략 2004~2497
- Vertex/retry fact check와 README 문구: 대략 2517~2867
- state/storage/pipeline fact check와 README 문구: 대략 2873~3267
- feature fact check 방향: 대략 3288~3464

## 복구 판단 메모

- 이 파일은 코드 복구보다는 README 복구의 기준 파일입니다.
- README를 다시 만들어야 한다면 원문 README보다 `14-summary.md`와 `docs/readme-*factcheck*` 계열 문서를 먼저 보는 것이 빠릅니다.
- README 문장은 “구현된 것만, 과장 없이, 실행자가 따라 할 수 있게”라는 기준으로 복구해야 합니다.
