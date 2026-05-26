# krafton_assignment_11 요약

## 핵심 주제

Prompt Enhancement를 P6까지 안정화하고, 현재 설계를 실제 파일 기준으로 확인한 뒤, frontend UX polish와 Veo/T2V failure classification까지 진행한 세션입니다. 복구 시 prompt enhance 최종 형태, frontend polish 기준, Veo 실패 분류 개선의 핵심 단서를 제공합니다.

## 주요 키워드

- Prompt Enhancement P6
- anti-generic vocabulary guidance
- Faithful / Balanced / Imaginative
- `backend/app/prompt_enhancement.py`
- `backend/app/services/llm/enhancer.py`
- manual review-first
- original / enhanced draft / final prompt
- frontend UX polish, assignment 3.2
- JobDetail waiting/result, Generate review layout, History polish
- I2V motion guidance
- Veo operation error, empty/filtered output classification

## 복구에 중요한 내용

- P5 이후에도 generic cinematic/photo vocabulary가 일부 남아 있었지만, P5 format exemplar 자체가 새는 문제는 아니라고 판단했습니다.
- P6는 backend-only prompt strategy polish입니다. frontend/API/schema/DB/temperature/max_output_tokens를 건드리지 않고 `enhancer.py` system prompt 텍스트와 format exemplar/component guidance만 조정하는 방향이었습니다.
- P6에서 확인해야 할 내용:
  - generic vocabulary를 절대 금지하지 않고 default/filler로 남용하지 않게 유도
  - 원본 의도 보존 원칙을 add-only 기준으로 명확화
  - T2I exemplar component keys를 `subject`, `setting`, `composition`, `lighting`, `style`, `mood` 중심으로 정리
  - Video exemplar component keys를 `subject`, `motion`, `camera_work`, `continuity`, `duration`, `sound_cue` 중심으로 정리
  - `sound_cue`는 relevant할 때만 포함하고, 사용자가 음향을 언급/암시하지 않으면 생략 가능하게 함
- Live QA 판독에서 `underwater library` 프롬프트는 Balanced/Imaginative 차이가 잘 드러났고, generic cinematic/photo vocabulary 억제 기준에서도 통과로 판단되었습니다.
- `tiny robot repairing a moon rover` 프롬프트에서는 Balanced가 여전히 camera/shot/style vocabulary를 많이 붙였지만, 사용자는 Balanced가 Faithful보다 높은 temperature이므로 더 풍부한 detail/style이 붙는 것이 의도된 동작이라고 판단했습니다.
- 최종 결론은 Prompt Enhancement가 기능 안정성, 모드 차별화, 기본 QA까지 완료된 안정화 상태이며 추가 튜닝은 보류한다는 것입니다.
- Prompt Enhancement에서 의도적으로 보류한 항목:
  - P1 source-of-truth UI/History 표현 정리
  - auto_enhance API 노출/문서 정리 여부
  - strict component schema 강제
  - 모델별 세부 최적화
- 실제 파일 기준 Prompt Enhancement architecture가 확인되었습니다.
  - creativity preset과 temperature mapping은 `backend/app/prompt_enhancement.py`에 중앙 정의
  - `enhancer.py`는 T2I/T2V/I2V guidance와 format exemplar를 분기
  - `/api/prompts/enhance`는 original/enhanced/components를 `PromptEnhancement`에 저장
  - `/api/generations`는 `enhancement_id`를 검증하고, 최종 generation prompt를 `Job.prompt`에 저장
  - `Job.enhanced_prompt`는 Gemini draft snapshot이고, `Job.prompt`가 최종 생성 입력입니다.
- Frontend manual review-first 흐름도 확인되었습니다.
  - Enhance 결과는 즉시 main prompt를 덮어쓰지 않음
  - `editableEnhancedPrompt`에서 사용자가 수정 가능
  - Accept 시 main prompt state에 반영
  - mode/model/creativity/prompt 변경 시 stale enhancement 연결을 폐기
  - generation payload는 현재 main prompt state를 사용
- AI_COLLABORATION.md에 쓸 핵심 서사가 정리되었습니다.
  - Creativity Mode는 사용자 주도 설계 포인트
  - AI가 generic words를 과하게 금지하려는 방향으로 해석할 수 있었지만, 사용자는 default/filler 방지로 조정
  - Balanced 결과가 Faithful보다 풍부한 것은 preset/temperature 목적상 정상일 수 있다고 사용자가 판단
  - Prompt Enhancement는 AI 자동 실행이 아니라 review-first UX로 설계됨
- Frontend UX polish는 평가항목 3.2 기준으로 정리되었습니다. “예쁘게 전체 수정”이 아니라 Generate, Enhance review, waiting experience, result display, History가 평가자에게 잘 보이도록 하는 것이 목표입니다.
- 한국어 UI 전환은 마지막 polish 후보로 미뤘습니다. 현재 UI는 영어 중심이므로 먼저 UX 구조를 안정화하고, 필요하면 마지막에 전체/부분 한국어화 여부를 판단하는 전략입니다.
- Frontend 구조 read-only audit 후 주요 대상 파일은 `GeneratePage.tsx`, `JobDetailPage.tsx`, `HistoryPage.tsx`, `index.css`로 정리되었습니다.
- 1차 UX polish는 generation/enhancement 흐름, JobDetail waiting progress, result display, History display를 나누어 진행했습니다. 각 단계에서 frontend lint/build를 검증하는 흐름이었습니다.
- manual QA 이후 추가 polish가 잡혔습니다.
  - developer-facing copy 제거
  - Generate review layout 개선
  - I2V source handoff 명확화
  - History video placeholder 개선
- 남은 UX 이슈로 I2V rejection case 안내가 도출되었습니다. source image에 없는 새 물체/장면을 추가하려는 prompt는 실패할 수 있으므로, I2V는 “선택된 이미지에 이미 보이는 내용을 자연스럽게 움직이게 하라”는 helper/recovery copy를 추가하는 frontend-only patch가 권장되었습니다.
- T2V Live QA에서 `Unexpected Vertex error`가 발생했고, 조사 결과 T2V submit/payload 문제가 아니라 Veo operation이 provider 쪽에서 실패/무출력/필터 처리되었을 때 backend가 generic error로 뭉개는 문제가 의심되었습니다.
- Veo failure classification에서 확인해야 할 내용:
  - `veo.poll_operation()`이 `current.error`를 먼저 확인하는지
  - done=True 이후 `generated_videos`가 비어 있거나 `video_bytes`가 없을 때 명확한 error로 분류하는지
  - filtered/no-output reason이 raw provider detail 없이 안전한 public error로 매핑되는지
- Veo operation error와 empty/filtered output 분류를 보강한 뒤, T2V는 다시 성공했습니다. 결론은 T2V pipeline 자체는 건강하고, 기존 실패는 provider-side operation failure 또는 empty/filtered output을 generic unexpected error로 보여준 문제였습니다.

## 원문에서 찾아볼 위치

- P6 prompt strategy polish와 Live QA 판독: 대략 362~858
- Prompt Enhancement 안정화 결론과 P6 문서화: 대략 874~1052
- source-of-truth/deferred 항목 판단: 대략 1058~1148
- AI_COLLABORATION.md용 prompt enhancement 서사: 대략 1156~1254
- 실제 파일 기준 Prompt Enhancement architecture 확인: 대략 1266~1894
- AI_COLLABORATION.md 내용 정리: 대략 1903~1946
- frontend UX polish 계획과 한국어화 판단: 대략 1961~2913
- UX polish 구현 단위와 manual QA 후속: 대략 2975~5459
- T2V/Veo failure classification: 대략 5484~6283
- 다음 세션 handoff 요약: 대략 6347~6480

## 복구 판단 메모

- Prompt Enhancement 복구에서는 `Job.prompt`와 `Job.enhanced_prompt`의 의미를 혼동하면 안 됩니다. 최종 생성 입력은 `Job.prompt`입니다.
- P6는 strict schema 강제가 아니라 prompt text와 exemplar key guidance 중심입니다.
- Frontend polish는 기능 추가가 아니라 평가자가 FE 3.2 요구사항을 빠르게 확인하도록 만드는 표면 정리입니다.
- Veo/T2V 실패가 다시 보이면 먼저 provider operation error, empty output, filtered output 분류가 살아 있는지 확인합니다.
