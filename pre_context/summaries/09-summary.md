# krafton_assignment_09 요약

## 핵심 주제

Phase 14 Live UX QA를 본격적으로 진행한 세션입니다. T2I 성공 이후 I2V/T2V/Pipeline 실제 Vertex-backed UX 검증, I2V source image 전달 버그, pipeline parent/child linkage 버그, Prompt Enhancement parser hardening, Creativity Mode, I2V-specific guidance, sectioned prompt template, P5 mode-scoped format exemplar까지 이어집니다.

## 주요 키워드

- Phase 14 Live UX QA, 실제 브라우저 QA
- I2V `Unexpected Vertex error`, `image_bytes`, Veo I2V payload
- T2V Live QA, Pipeline T2I -> I2V Live QA
- pipeline `parent_job_id`, `/api/pipelines/{parent_job_id}`
- Prompt Enhancement 502, malformed JSON, fenced JSON, longer responses
- Asset detail endpoint, retry coverage, History QA
- Creativity Mode, Faithful/Balanced/Imaginative
- I2V-specific enhancement guidance
- P4 sectioned prompt template, P5 mode-scoped format exemplar
- generic cinematic/photo vocabulary follow-up, AI_COLLABORATION deferred

## 복구에 중요한 내용

- 이 세션에서는 실제 브라우저 Live QA는 사용자가 직접 수행하고, Codex CLI는 준비/관찰/로그 판독/문서화/bugfix만 담당한다는 경계가 반복되었습니다.
- T2I Live QA 성공은 이미 문서화된 상태였고, 이후 I2V/T2V/Pipeline 순서로 core generation flow를 닫는 방향이 선택되었습니다.
- I2V Live QA에서 frontend에는 `Unexpected Vertex error`가 표시되었습니다. job 생성 자체는 201로 성공했고 state는 `queued -> generating -> failed`로 매우 빠르게 실패했습니다.
- I2V 실패 원인은 Veo 전체 접근 문제가 아니라 source image bytes가 실제 Veo I2V 요청 payload에 전달되지 않는 흐름으로 좁혀졌습니다. 복구 시 `backend/app/services/jobs/handlers.py`와 `backend/app/services/vertex/veo.py`에서 T2V/I2V 호출 경계를 확인해야 합니다.
- I2V bugfix의 핵심은 기존 T2V는 image input 없이 유지하고, I2V에서만 source image bytes를 Veo 요청에 전달하는 것입니다. 관련 테스트는 T2V 기존 경로 보존과 I2V image input 전달을 mock-only로 검증해야 합니다.
- I2V 재검증 후 실제 Veo I2V video/mp4 생성과 frontend playback/rendering 성공이 확인되었습니다.
- T2V Live UX QA도 prompt enhancement/auto-enhance를 끈 순수 T2V로 진행했고, video/mp4 생성 및 frontend playback 성공으로 판단되었습니다.
- Pipeline T2I -> I2V Live QA는 처음에는 최종 video 생성/재생은 성공했지만 backend linkage 결함이 발견되었습니다. child I2V의 `source_asset_id`는 parent image asset을 참조했으나 `parent_job_id`가 비어 있고 `/api/pipelines/{parent_job_id}`가 404였습니다.
- pipeline linkage bugfix의 핵심은 I2V 생성 시 source image asset의 `job_id`를 child job의 `parent_job_id`로 저장하여 `/api/pipelines/{parent}`에서 parent + child 관계를 찾을 수 있게 하는 것입니다.
- pipeline 재검증에서는 parent T2I completed, child I2V completed, child `source_asset_id -> parent image asset`, child `parent_job_id -> parent T2I job`, `/api/pipelines/{parent}` 200 OK with child가 확인되었습니다.
- Prompt Enhancement QA에서는 처음 `/api/prompts/enhance`가 502 `Prompt enhancement response was invalid`로 실패했습니다. 이후 Gemini 응답 파싱/검증을 여러 단계로 hardening했습니다.
- Prompt Enhancement parser hardening에서 확인해야 할 내용:
  - Gemini가 fenced JSON을 반환해도 파싱 가능한지
  - 앞뒤 설명문이 섞인 JSON에서 올바른 top-level object를 선택하는지
  - `{`로 시작하지만 닫히지 않는 truncated JSON을 진단 로그로 식별하는지
  - `max_output_tokens`가 너무 작아 긴 structured response가 잘리지 않는지
  - malformed response가 민감정보 없이 sanitized public error로 매핑되는지
- `max_output_tokens` 상향, fenced JSON/설명 섞인 JSON/parsed response 처리, malformed 응답 진단 로그 개선을 거쳐 Korean prompt enhancement review/edit/apply와 실제 T2I 생성 성공까지 확인되었습니다.
- Asset detail endpoint도 추가되었습니다. 복구 시 asset detail API가 job/asset metadata를 안전하게 반환하고 `/files` serving과 일관되는지 확인합니다.
- retry coverage도 보강되었습니다. T2I/T2V/I2V submit retry, rate limit retry, multi-image asset persistence 등은 실제 Vertex 호출 없이 fake service로 검증하는 흐름입니다.
- `.codex/memories`의 durable 문서는 `docs/` 하위로 복사/관리하는 방향이 정리되었습니다. 이후 제출/복구에 필요한 문서는 `docs/` 아래에 두는 규칙이 생겼습니다.
- History QA는 사용자가 직접 확인했고, recent generations list/display 레벨에서 통과로 판단되었습니다. pipeline parent/child가 History에서 시각적으로 그룹화되지 않는 것은 blocker가 아니라 UX polish 후보입니다.
- `AI_COLLABORATION.md`는 prompt enhancement 설계 원칙과 strategy를 최종 5시간에 집중해 작성하기로 보류했습니다. 이 세션에서는 현재 구현 분석과 future improvements 정리만 했습니다.
- Prompt Enhancement improvement plan은 `docs/memories/prompt_enhancement_plan.md` 흐름으로 정리되었습니다. 이후 P2/P3/P4/P5 개선 기준이 이 문서에 연결됩니다.
- P2 Creativity Mode:
  - presets: Faithful `0.2`, Balanced `0.5`, Imaginative `0.8`
  - Imagen/Veo generation temperature가 아니라 Gemini enhancer creativity control입니다.
  - frontend에서 Faithful/Balanced/Imaginative control이 보이고, review metadata에 반영되는지 확인합니다.
  - Live QA에서는 Faithful은 원문 보존 중심, Balanced는 자연스러운 디테일 보강, Imaginative는 더 강한 visual hook을 주는 경향으로 판단되었습니다.
- P3 I2V-specific enhancement guidance:
  - I2V에서는 source image의 subject/identity/scene/composition 보존을 명시합니다.
  - motion/camera/atmosphere를 보강하되 source image를 덮어쓰지 않도록 해야 합니다.
  - I2V + Imaginative 조합에서도 image preservation guidance와 creativity strategy가 같이 유지되는지 확인합니다.
- P4 sectioned prompt template:
  - persona/objective/instructions/constraints/context/output format/user prompt delimiter 구조
  - prompt injection 방어와 JSON output 안정성을 높이기 위한 구조화입니다.
  - few-shot은 이 단계에서 넣지 않았고, Creativity Mode가 창의성 조절을 담당한다는 판단이 유지되었습니다.
- P5 mode-scoped format exemplar:
  - global few-shot이 아니라 response format exemplar로 재정의되었습니다.
  - T2I 요청에는 T2I exemplar만, T2V/I2V 요청에는 video exemplar만 포함합니다.
  - example subject/style/mood/lighting/camera/palette/phrasing을 복붙하지 말라는 지시가 들어갑니다.
  - 목적은 창작 스타일 고정이 아니라 response structure 안정화입니다.
- P5 Live QA에서는 exemplar leakage는 크게 보이지 않았지만, Balanced/Imaginative가 여전히 `photorealistic`, `cinematic`, `close-up`, `low-angle`, `dramatic`, `long shadows` 같은 generic cinematic/photo vocabulary로 수렴하는 문제가 남았습니다. 결론은 P5 rollback이 아니라 Creativity strategy wording을 더 다듬는 것입니다.

## 원문에서 찾아볼 위치

- I2V Live QA 준비/host allowlist/Unexpected Vertex error: 대략 162~930
- I2V bugfix와 live success: 대략 930~1358
- T2V Live QA와 문서화: 대략 1370~1935
- Pipeline QA, linkage bug, fix, 재검증: 대략 1947~2888
- Prompt Enhancement parser hardening: 대략 7613~10361
- Asset detail endpoint, retry coverage, docs migration: 대략 10479~12550
- History QA와 AI_COLLABORATION 보류 판단: 대략 12656~13120
- Prompt Enhancement improvement plan / Creativity Mode: 대략 13140~14835
- I2V-specific guidance: 대략 14895~15702
- P4 sectioned prompt template: 대략 15725~16523
- P5 mode-scoped format exemplar와 generic phrasing follow-up: 대략 16539~17649

## 복구 판단 메모

- I2V가 실패하면 credentials나 Veo 접근 문제로 단정하지 말고, source image bytes가 `veo.py` 요청 payload까지 전달되는지 먼저 확인합니다.
- Pipeline은 video 생성 성공만으로 완료가 아닙니다. `child.parent_job_id`, `source_asset_id`, `/api/pipelines/{parent}` 조회까지 살아 있어야 복구가 맞습니다.
- Prompt Enhancement는 parser hardening이 빠지면 실제 Gemini 응답에서 쉽게 502가 재발할 수 있습니다.
- Creativity Mode/P3/P4/P5는 모두 prompt enhancement 품질 개선 흐름이지만, DB schema 변경 없이 API/service/frontend/문서 중심으로 진행되었습니다.
- P5 이후 남은 개선은 format exemplar 제거가 아니라 generic cinematic/photo phrasing 기본값을 줄이는 작은 prompt strategy polish입니다.
