# krafton_assignment_02 요약

## 핵심 주제

과제 원문 명세를 바탕으로 전체 아키텍처, 작업 일정, prompt enhancement용
LLM 선택 전략을 정리한 세션입니다. 복구 시에는 요구사항 해석과 Gemini 기반
enhance 설계 근거를 확인할 때 사용합니다.

## 주요 키워드

- 과제 명세, 필수 구현, Step 1, Step 2, Step 3
- Imagen 4, Veo 3, Gemini 2.5 Flash, Claude
- Rate Limit, 비용, Docker Compose
- FastAPI, SQLAlchemy, PostgreSQL, React, Vite
- prompt enhancement, original_prompt, enhanced_prompt, final_prompt
- PromptEnhancer, VertexGeminiPromptEnhancer, FakePromptEnhancer
- GenerationProvider, FakeGenerationProvider

## 복구에 중요한 내용

- 필수 기능은 T2I/T2V/I2V API, DB 저장, 로컬 파일 저장, prompt enhancement,
  retry 전략, T2I -> I2V pipeline, 자동화 테스트, frontend 생성/대기/결과/히스토리 UI입니다.
- Imagen은 동기 이미지 생성 흐름, Veo는 long-running operation/polling 흐름으로
  다루는 것이 자연스럽다고 정리됩니다.
- Vertex 호출을 API handler에서 직접 오래 기다리지 말고, job으로 저장한 뒤
  background runner가 처리해야 한다는 판단이 나옵니다.
- prompt enhancement는 사용자가 바로 생성에 쓰는 자동 대체가 아니라,
  원본/개선본 비교 후 사용자가 수정/수락하는 구조로 설계합니다.
- prompt 저장 구조는 `original_prompt`, `enhanced_prompt`, `final_prompt`를
  분리하는 방향이 제안됩니다.
- enhance LLM은 Gemini via Vertex가 기본 선택입니다. 이유는 Imagen/Veo와 같은
  `google-genai` SDK, 같은 service account 인증, 채점 환경 재현성이기 때문입니다.
- Claude는 품질상 장점이 있지만 기본 경로로 두기에는 SDK/키/채점 환경 리스크가
  크므로 내부 인터페이스로 교체 가능하게 열어두는 정도가 적절하다고 판단합니다.

## 원문에서 찾아볼 위치

- 과제 원문 요구사항: 대략 31~118
- 초기 추천 아키텍처와 worker/job 판단: 대략 151~207
- prompt enhancement JSON 구조와 프롬프트 분해 전략: 대략 209~227
- 3일 작업 일정과 테스트 가능한 provider 분리: 대략 231~235
- Gemini via Vertex 선택 근거: 대략 241~288
- Gemini와 Claude 품질/재현성 비교: 대략 294~339
- README/AI_COLLABORATION에 쓸 문장 후보: 대략 377~388

## 복구 판단 메모

- `app/services/llm/enhancer.py`나 prompt enhancement API를 복구할 때 이 파일을
  먼저 확인합니다.
- Gemini 기본, Claude 선택 가능 구조라는 설명은 최종 문서와
  `AI_COLLABORATION.md`에도 연결됩니다.
- 실제 구현이 Claude provider를 포함하지 않더라도, 설계상 교체 가능한 경계로
  설명한 근거가 이 파일에 있습니다.
