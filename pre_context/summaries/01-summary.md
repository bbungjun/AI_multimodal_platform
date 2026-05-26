# krafton_assignment_01 요약

## 핵심 주제

초기 과제 이해, 제출 방식 확인, 기술 스택 선택, Phase 0~6 기반 구현 흐름,
Phase 7 Imagen T2I 진입 직전 판단이 담긴 대형 세션입니다. 복구 시에는
프로젝트의 초기 설계 의도와 Phase별 책임을 확인하는 1차 근거로 사용합니다.

## 주요 키워드

- 과제 명세, Vertex AI, Imagen, Veo, Gemini
- FastAPI, PostgreSQL, React, Vite, Docker Compose
- Phase 0, Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7
- Job, Asset, PromptEnhancement
- state_machine, storage, runner, retry, rate limiter
- README, AI_COLLABORATION, AGENTS.md
- 실제 Vertex 호출 금지, mock/stub 테스트

## 복구에 중요한 내용

- 제출 방식은 개인 GitHub push가 아니라 제공 워크스페이스에서 작업하고
  필요한 경우 로컬 작업 기록을 남기는 방식으로 해석했습니다.
- 원래 `README.md`는 과제 명세였고, 최종 프로젝트 README는 Phase 17에서
  교체 예정이라는 판단이 반복됩니다.
- 기술 스택은 Python 3.11 + FastAPI + async SQLAlchemy + Postgres,
  Vite + React + TypeScript, `google-genai` 단일 SDK가 적합하다고 결정했습니다.
- Celery/Redis 없이 FastAPI 내부 asyncio job runner와 Postgres job table로
  처리하는 방향이 확정됩니다.
- 결과 파일은 로컬 `DATA_DIR`/asset storage에 저장하고, 안전한 path helper를
  통과해야 한다는 원칙이 세워집니다.
- Phase 4/5는 실제 Vertex 호출 완료가 아니라 Vertex client readiness,
  error mapping, retry/rate limiter 기반 완성으로 정리됩니다.
- Phase 7부터 Imagen 실제 호출 코드를 붙이되, 자동 테스트에서는 mock/stub만
  사용해야 한다는 경계가 분명합니다.

## 원문에서 찾아볼 위치

- 과제 요구사항과 모델/rate limit 표: 대략 431~518
- 기술 스택 비교와 FastAPI 선택 이유: 대략 590~640
- 현재 프로젝트 구조와 Phase 0 상태 확인: 대략 966~1100
- Phase 1 health skeleton 지시: 대략 1110~1200
- 아키텍처, 상태머신, rate limiter 설계 메모: 대략 1320~1415
- Phase 6 런타임 검증과 DB 없는 환경 대응: 대략 7500~7600
- Phase 7 Imagen T2I 시작 프롬프트 후보: 대략 7590~7645, 8450~8636
- Phase 4/5가 실제 Vertex 호출 완료가 아니라 readiness 계층임을 정리:
  대략 8479~8556
- 새 세션 인수인계 요약: 대략 8655~8694

## 복구 판단 메모

- 현재 복구 작업에서 프로젝트 원칙이 헷갈리면 이 파일을 먼저 봅니다.
- 특히 “실제 Vertex 호출은 자동 테스트에서 금지”, “Phase별로 작게 진행”,
  “README 원문은 보존 후 최종 README로 교체”는 이 세션의 핵심 판단입니다.
- 코드 조각 자체보다 설계 의도와 Phase 경계 확인용으로 유용합니다.
