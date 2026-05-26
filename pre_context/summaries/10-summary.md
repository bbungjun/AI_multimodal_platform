# krafton_assignment_10 요약

## 핵심 주제

전략 파트너 역할을 명확히 정하고, 현재 작업 환경이 기업 서버 + E2B 기반이며 Git remote가 없는 로컬 작업 공간이라는 점을 확인한 세션입니다. 또한 원본 과제 README를 평가 루브릭으로 다시 읽고, 남은 작업 우선순위를 정리했습니다.

## 주요 키워드

- 전략 파트너, 직접 구현 금지, Codex CLI 결과 판독
- `/home/user/recovered_workspace`
- Git remote 없음, 기업 서버 + E2B 환경
- 손상된 `/home/user` 루트 repo 수정 금지
- 원본 과제 README, 평가 루브릭
- BE 3.1, FE 3.2, Infra 3.3
- README.md, AI_COLLABORATION.md
- retry edge coverage, multi-image T2I asset persistence

## 복구에 중요한 내용

- 이 세션의 역할 정의는 명확합니다. 사용자는 실제 구현/코드 수정을 Codex CLI에 맡기고, 이 대화는 결과 판독, 위험 지점 식별, 다음 작업 순서/프롬프트 제안만 담당합니다.
- 사용자가 “프롬프트 줘/제공해줘”라고 요청하기 전에는 Codex CLI용 프롬프트를 먼저 작성하지 않는 운영 규칙이 정리되었습니다.
- 실제 작업 repo는 `/home/user/recovered_workspace`이며, `/home/user` 루트는 Git object 손상 및 read-only `.git` mount가 있어 git 작업/파일 수정 금지입니다.
- Git remote/push가 없는 공간이고, 기업 서버 + E2B 평가/브라우저 환경에서 과제를 진행 중이라는 점을 확인했습니다.
- credential, `.env`, service-account JSON, API key 내용은 절대 요청/출력하지 않는 원칙이 반복되었습니다.
- 자동화 테스트에서는 Vertex/Gemini/Imagen/Veo 실제 호출을 금지하고, 실제 호출은 명시적 Live UX QA에서만 허용한다는 경계가 유지됩니다.
- 사용자가 붙여준 과제 README는 평가 루브릭 원문으로 해석되었습니다. 핵심 요구사항은 다음입니다.
  - BE: T2I/T2V/I2V API, 모델 선택, asset DB/로컬 저장, asset detail API, prompt enhance review/edit, retry, T2I -> I2V pipeline, 자동화 테스트
  - FE: 생성 인터페이스, prompt enhance 확인/편집 흐름, 유의미한 대기 경험, 결과 표시, 히스토리
  - Infra: `docker compose up` 한 번으로 전체 실행
  - 산출물: README.md, AI_COLLABORATION.md, AI 도구 컨텍스트/plan/session history
- 현재 상태에서 BE 필수 기능은 대부분 충족된 것으로 보고, retry edge coverage와 multi-image T2I asset persistence 테스트 보강이 좋은 마무리 작업으로 판단되었습니다.
- `AI_COLLABORATION.md`는 Step 3 답변뿐 아니라 prompt enhancement 설계 원칙과 프롬프트 전략도 반드시 담아야 한다고 정리했습니다.
- 최종 README는 과제 원문이 아니라 프로젝트 구동 방법, 기술 스택, Docker Compose, 환경변수/credential 배치, 주요 기능, 테스트 방법 중심 문서여야 한다고 판단했습니다.
- 선택 기능으로는 동시 요청 및 Rate Limit 관리가 이미 강점이 될 수 있으므로, 채팅 에이전트/예산/모델 비교까지 무리하게 확장하지 않아도 된다는 전략이 정리되었습니다.

## 원문에서 찾아볼 위치

- 운영 규칙과 현재 repo/환경 전제: 대략 128~337
- Git remote 없는 기업 서버 + E2B 환경 확인: 대략 360~381
- 원본 과제 README 전체: 대략 390~620
- README를 평가 루브릭으로 해석한 판단: 대략 630~660

## 복구 판단 메모

- 이 파일은 코드 복구보다 “작업 운영 원칙”과 “평가 기준”을 확인하는 용도입니다.
- 복구 중 어떤 기능을 우선해야 할지 헷갈리면 과제 README의 3.1/3.2/3.3과 이 요약을 기준으로 봅니다.
- README/AI_COLLABORATION을 작성할 때는 원본 과제 설명을 반복하지 말고, 실제 구현/검증/AI 협업 판단을 프로젝트 문서로 정리해야 합니다.
