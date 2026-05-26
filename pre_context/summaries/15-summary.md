# krafton_assignment_15 요약

## 핵심 주제

최종 README 검토, AI_COLLABORATION.md 작성, 제출 직전 안정화까지 이어진 마무리 세션입니다. 최종 문서 서사, Prompt Enhancement Strategy, Q1/Q2/Q3 답변, 마지막 기능 polish, root 제출 위치 동기화, secret 노출 확인, 마지막 build/compose 점검, 제출 완료 기록이 들어 있습니다.

## 주요 키워드

- final README
- AI_COLLABORATION.md
- Prompt Enhancement Strategy
- Creativity Mode
- Faithful / Balanced / Imaginative
- review/edit/accept
- final prompt source of truth
- Veo long-running operation
- operation error / safety filtered / missing output
- Q2 verification checklist
- API contract
- pipeline model validation
- T2I multi-image gallery
- root sync
- secret grep
- final build
- submission complete

## 복구에 중요한 내용

- README는 내용과 형식 모두 제출 가능 수준으로 정리되었습니다.
  - 한국어 README는 overview, Quick Start, 환경 변수, Docker Compose, architecture, features, API, tests, constraints 순서가 적절하다고 판단되었습니다.
  - `VITE_ALLOWED_HOSTS`는 실제 Docker Compose/Vite config에서 사용되므로 README에 유지해도 됩니다.
  - README는 CRLF/trailing whitespace 이슈를 피하기 위해 LF 정규화와 `git diff --check` 통과가 권장되었습니다.
  - `docs/readme-*factcheck*` 문서는 삭제 대상이 아니라 README 작성 근거 문서로 유지하는 판단이 있었습니다.
- AI_COLLABORATION.md의 최종 구조가 확정되었습니다.
  - 시스템 기능 명세를 어떻게 해석하고 구현했는가
  - Prompt Enhancement Strategy
  - Q1: 가장 까다로운 엣지케이스/장애 시나리오
  - Q2: AI 코드 반영 시 검증 기준
  - Q3: AI와 복잡한 문제를 해결하거나 한계를 극복한 사례
- 시스템 기능 명세 해석의 핵심 서사가 정리되었습니다.
  - 과제를 단순한 Vertex API 호출 예제가 아니라 prompt 기반 image/video generation service로 해석했습니다.
  - T2I, T2V, I2V, pipeline, history, deletion은 모두 `Job`, `Asset`, `PromptEnhancement`와 그 상태 전이 위에 올라간다고 보았습니다.
  - 따라서 job lifecycle, state machine, background job runner, storage path safety를 먼저 안정화해야 후속 기능이 흔들리지 않는다고 판단했습니다.
  - background job runner와 state transition은 후속 기능이 모두 의존하는 기반이므로 TDD와 QA를 병행했다는 근거가 확인되었습니다.
  - Vertex/Gemini는 비용, quota, 권한, safety filter, operation failure, empty output, malformed JSON이 발생할 수 있으므로 자동화 테스트에서는 mock/fake로 검증합니다.
- Pipeline 서사의 위치가 정리되었습니다.
  - Pipeline은 Prompt Enhancement Strategy가 아니라 “job lifecycle 설계를 검증한 대표 기능”으로 시스템 기능 명세 쪽에 넣는 것이 자연스럽습니다.
  - parent T2I와 blocked child I2V를 함께 만들고, parent image asset이 저장된 뒤에만 child를 unblock합니다.
  - parent 실패 또는 정상 image asset 부재 시 child도 실패로 정리해 pipeline 실패 원인을 추적할 수 있게 합니다.
- Prompt Enhancement Strategy 최종 재료가 정리되었습니다.
  - Prompt Enhancement는 Gemini가 prompt를 대신 결정하는 기능이 아니라, 사용자가 더 좋은 generation prompt를 만들도록 돕는 검토 가능한 초안입니다.
  - Gemini 결과는 바로 generation prompt로 덮어쓰지 않고, 사용자가 review/edit/accept를 거친 뒤에만 반영됩니다.
  - 수락된 enhancement는 `enhancement_id`로 연결되고, generation API는 target mode/model mismatch를 다시 검증합니다.
  - 최종 generation prompt의 source of truth는 사용자가 화면에서 확인한 `payload.prompt`입니다.
  - Google prompt design strategy를 sectioned prompt로 번역해 role/objective/instructions/constraints/context/output format/example/user input/summary를 나누었습니다.
  - T2I, T2V, I2V는 mode별 guidance가 다릅니다. I2V는 T2V motion guidance에 source image 보존 제약이 추가됩니다.
  - Creativity Mode는 Gemini prompt enhancement에만 적용되는 AI 개입 강도 조절 장치입니다.
  - 실제 preset은 Faithful/Balanced/Imaginative이고 temperature는 각각 `0.2 / 0.5 / 0.8`로 확인되었습니다.
  - 세 mode 모두 사용자가 명시한 주어/동작/배경/스타일을 삭제하거나 교체하지 않는 ADD-only 원칙을 공유합니다.
  - Gemini 응답은 JSON schema validation을 통과해야 하며 malformed JSON에 한해 1회 strict retry를 수행합니다.
  - raw provider output, credential, service account 내용은 노출하지 않고 safe diagnostics만 전달합니다.
- Q1의 최종 핵심은 Veo long-running operation입니다.
  - Veo는 request/response API처럼 submit 성공이 곧 generation 성공이 아닙니다.
  - operation name을 받으면 요청 접수는 성공했지만 실제 영상 생성은 polling 단계에서 실패할 수 있습니다.
  - 해결은 operation error, safety-filtered result, missing video bytes를 구분해 `vertex_safety_blocked`, `vertex_output_unavailable` 같은 public error code로 저장/응답하는 방향입니다.
  - 서버 재시작 시 저장된 operation name으로 polling을 이어갈 수 있다는 점도 Q1의 강한 근거입니다.
  - Gemini malformed JSON retry는 같은 원칙을 prompt enhancement에 적용한 보조 사례로만 두는 편이 좋습니다.
- Q2의 최종 핵심은 “AI 코드가 기존 시스템의 아키텍처 구조와 실제 사용자 흐름을 해치지 않는지”입니다.
  - 검증 항목은 state transition, API contract, provider failure handling, mock/live QA 분리, credential/path safety, DB/file consistency, 사용자 흐름입니다.
  - API contract는 사용자가 직접 OpenAPI를 봤다고 쓰기보다, Codex CLI 검증 기준을 FastAPI OpenAPI/Swagger로 지정해 frontend type/client와 backend schema/route drift를 확인하게 했다고 쓰는 것이 정확합니다.
  - `/api/pipelines`도 `/api/generations`처럼 image_model은 Imagen, video_model은 Veo만 허용하도록 검증/차단한 것이 Q2의 API contract 사례로 추가되었습니다.
- Q3의 최종 핵심은 Prompt Enhancement Creativity Mode입니다.
  - AI agent는 일관성을 위해 낮은 Gemini temperature 고정을 제안했지만, 사용자는 실제 image/video generation 서비스의 사용자가 항상 보수적인 결과만 원하지 않는다고 판단했습니다.
  - Faithful/Balanced/Imaginative로 AI 개입 강도를 선택하게 하고, Gemini 결과를 자동 적용하지 않고 사용자가 수락하도록 만든 것이 핵심 협업 사례입니다.
  - AI가 빠르게 초안을 만들 수는 있지만, 제품이 어떤 선택권과 통제권을 제공해야 하는지는 사람이 QA와 trade-off 판단으로 결정해야 한다는 결론이 남았습니다.
- 제출 직전 기능 polish도 AI_COLLABORATION/README에 반영할 재료로 정리되었습니다.
  - Pipeline model validation: 잘못된 model family 조합을 API 단계에서 차단합니다.
  - T2I multi-image gallery: backend에는 여러 image asset이 저장되는데 Job Detail이 첫 번째 asset만 보여주던 문제를 고쳐 모든 image result와 각 image별 I2V 시작 흐름을 제공합니다.
  - History deletion, asset type filter, video preview, I2V source handoff는 사용자 흐름 검증 사례로 Q2/시스템 기능 명세에 넣을 수 있습니다.
- 제출 위치와 root sync 판단이 중요합니다.
  - 평가자가 `/home/user` root 기준으로 README/AI_COLLABORATION을 볼 수 있으므로 `/home/user/recovered_workspace`의 최종 README/AI_COLLABORATION을 `/home/user`에도 동기화해야 한다는 판단이 있었습니다.
  - root에서는 git 작업을 하지 않고, `cmp -s`로 두 파일이 같은지만 확인합니다.
  - service account JSON은 존재할 수 있지만 절대 열거나 출력하지 않고, README/AI_COLLABORATION에 key 내용이나 민감한 파일명이 들어가지 않았는지 grep으로 확인합니다.
- 마지막 검증과 제출 판단이 남아 있습니다.
  - frontend production build 성공이 확인되었습니다.
  - 제출 직전에는 README를 더 수정하지 말고, root 문서 동기화와 Docker Compose 실행/상태/log 확인에 집중하는 것이 권장되었습니다.
  - 마지막 기록상 KRAFTON take-home 제출은 완료되었고, 최종 README/AI_COLLABORATION 작성 및 root 동기화도 완료된 것으로 정리되었습니다.

## 원문에서 찾아볼 위치

- README 최종 검토와 LF 정리: 대략 948~1088
- fact check 문서 유지 판단과 README 작업 마무리: 대략 1108~1338
- AI_COLLABORATION 구조와 초반 방향: 대략 1390~1618
- 시스템 기능 명세/runner/state/storage 서사: 대략 2069~2382, 11015~11448
- Q1 Veo long-running operation 초안과 최종 방향: 대략 2414~2608, 11980~12096
- Q2 검증 기준과 API contract: 대략 3131~3499, 8690~8711
- Q3 Creativity Mode와 AI 한계 극복: 대략 3537~3715, 10782~10826, 12197~12374
- Prompt Enhancement Strategy fact check와 압축: 대략 7550~8646, 11526~11832
- T2I multi-image gallery와 pipeline validation 반영: 대략 9823~10436
- root README/AI_COLLABORATION sync와 secret 확인: 대략 10443~10730, 12417~12706
- 마지막 build/compose/제출 완료: 대략 12712~13027

## 복구 판단 메모

- 이 파일은 최종 산출물 복구의 기준입니다. README/AI_COLLABORATION을 다시 만들어야 하면 15번이 가장 중요합니다.
- AI_COLLABORATION은 코드 세부 목록보다 “왜 그렇게 판단했는가”를 중심으로 압축해야 합니다.
- 제출 직전 상태를 재현해야 하면 root sync, secret grep, frontend build, Docker Compose 실행 확인 순서가 핵심입니다.
