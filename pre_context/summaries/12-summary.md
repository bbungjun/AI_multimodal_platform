# krafton_assignment_12 요약

## 핵심 주제

이전 세션의 최신 상태를 다음 세션으로 넘기기 위한 handoff 성격이 강한 세션입니다. Prompt Enhancement 최종 요약, frontend UX polish 상태, Veo/T2V failure classification 상태, 남은 작업 순서가 압축되어 있습니다.

## 주요 키워드

- recovered workspace handoff
- Prompt Enhancement stabilized
- manual review-first
- Faithful / Balanced / Imaginative
- P6 anti-generic guidance
- frontend UX polish completed
- I2V motion prompt guidance remaining
- Veo/T2V failure classification
- docs/memories
- AI_COLLABORATION.md deferred
- README/final docs later

## 복구에 중요한 내용

- 실제 작업 repo는 `/home/user/recovered_workspace`이고, `/home/user` 루트는 손상된 repo이므로 수정/git 작업 금지라는 전제가 다시 반복됩니다.
- 새 문서화 산출물은 `.codex/`가 아니라 `docs/` 하위에 둔다는 규칙이 유지됩니다.
- Prompt Enhancement 최종 상태:
  - stabilized, further tuning deferred
  - Faithful/Balanced/Imaginative가 의도대로 동작
  - Balanced가 higher temperature 때문에 richer composition/style detail을 붙일 수 있으며 이는 허용 가능한 동작
  - components는 schema-enforced가 아니라 prompt/exemplar로 유도되는 free-form dict
- Prompt Enhancement architecture facts:
  - `backend/app/prompt_enhancement.py`: preset과 temperature mapping의 중앙 정의
  - `backend/app/services/llm/enhancer.py`: T2I/T2V/I2V guidance split, sectioned prompt, delimiter, JSON-only response, validation
  - `/api/prompts/enhance`: original/enhanced/components 저장
  - `/api/generations`: `enhancement_id` 검증, `Job.prompt`는 최종 generation prompt, `Job.enhanced_prompt`는 Gemini draft snapshot
  - frontend: Enhance result는 `editableEnhancedPrompt`로 들어가고 Accept 전까지 main prompt를 덮어쓰지 않음
- Frontend UX polish 상태:
  - Generate hero copy와 primary UI의 developer-facing copy가 정리됨
  - Generate layout이 더 compact해짐
  - Enhance review/components가 더 잘 보임
  - I2V source handoff에서 source image가 잠겨 있다는 점이 더 명확해짐
  - History는 전반적으로 양호하고, video는 backend thumbnail 생성 없이 의도적인 placeholder로 표시
- 남은 frontend UX 이슈:
  - I2V에서 source image에 없는 새 물체/행동을 추가하려는 prompt가 reject될 수 있으므로 helper/recovery copy가 필요
  - 권장 방향은 frontend-only로 I2V source locked 영역과 error helper에 “선택된 이미지의 기존 내용을 보존하며 motion 중심으로 작성하라”는 안내를 추가하는 것입니다.
- Veo/T2V failure investigation 상태:
  - T2V Live QA에서 submit은 성공하고 polling까지 갔지만 failed 상태로 끝난 사례가 있었습니다.
  - 조사 결과 `veo.poll_operation()`이 operation error나 empty/filtered output을 세분화하지 못하고 generic unexpected error로 보여줄 수 있었습니다.
  - operation error와 empty/filtered output 분류가 보강되었고, 이후 T2V Live QA가 다시 성공했습니다.
  - 결론은 T2V pipeline 자체는 건강하며, 기존 실패는 provider-side operation failure 또는 empty/filtered output을 더 잘 분류하지 못한 문제였습니다.
- 남은 문서화:
  - Veo failure classification과 T2V re-QA를 `docs/memories`에 기록
  - frontend UX polish QA를 최종 브라우저 QA 후 기록
  - AI_COLLABORATION.md는 최종 시간대에 작성
- AI_COLLABORATION.md에 기억할 포인트:
  - Creativity Mode는 사용자 제안
  - generic words는 절대 금지가 아니라 default/filler 남용 방지로 조정
  - Balanced 결과 해석에서 사용자가 preset 목적과 temperature 차이를 근거로 AI의 과도한 회귀 판단을 보정
  - manual review-first는 핵심 제품 판단
  - 좋은 장애 사례는 Gemini JSON/parser stability 또는 Veo operation failure classification

## 원문에서 찾아볼 위치

- 최신 handoff 전체: 대략 120~340
- Prompt Enhancement 최종 요약: 대략 860~925, 2680~2720
- P6 안정화와 deferred 판단: 대략 1012~1121
- Prompt Enhancement architecture 확인: 대략 1266~1894
- AI_COLLABORATION.md용 서사: 대략 1903~1946
- frontend UX polish 상태와 남은 I2V guidance: 대략 1961~2720
- 마지막 Prompt Enhancement 요약 답변: 대략 2650~2718

## 복구 판단 메모

- 이 파일은 새 기능 구현 근거보다 “최신 상태 압축본”으로 보면 됩니다.
- 복구 시 `11-summary.md`가 상세 근거이고, `12-summary.md`는 현재 어디까지 완료/보류됐는지 빠르게 확인하는 색인 역할입니다.
- 다음 작업 후보는 I2V motion guidance frontend-only patch, Veo failure classification 문서화, frontend UX polish QA 문서화, 최종 README/AI_COLLABORATION 작성입니다.
