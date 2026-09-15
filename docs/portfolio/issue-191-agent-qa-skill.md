# Issue191 — CreativeOps Agent QA 프로젝트 Skill

- [Issue191](https://github.com/bbungjun/AI_multimodal_platform/issues/191)
- Status: `Implemented / Discovery Verified`

## 배경과 문제

QA Contract, Impact Selector, Chrome DevTools Adapter와 aggregate Receipt gate가 구현됐지만,
새 Agent는 실행 명령과 결과 해석을 문서에서 다시 찾아야 했다. 특히 `complete=true`인
제품 FAIL을 실행 실패로 오해해 재시도하거나, 과거 revision의 Receipt를 현재 코드의
검증으로 사용하는 위험이 있었다.

## 해결 방법

저장소에 `.agents/skills/creativeops-agent-qa` Skill을 추가했다. Skill은 구현을 복제하지
않고 기존 deep Module의 Interface를 사용한다. 요청 의도에 따라 기존 Receipt review,
focused diagnosis, 전체 merge-readiness gate를 선택하며 다음 불변식을 유지한다.

- full gate는 committed clean HEAD와 서로 다른 immutable base/head SHA를 요구한다.
- live Vertex/Google을 호출하지 않고 owned mock runtime만 사용한다.
- resume은 같은 revision, source unchanged, process/cleanup0 결과만 재사용한다.
- 제품 FAIL을 BLOCKED와 구분하고 assertion을 완화해 PASS로 만들지 않는다.
- `ALLOW`는 evidence 판정이며 외부 push/PR/merge 권한이 아니다.

## 검증

- Skill Creator `quick_validate.py`: PASS
- Codex prompt input discovery: repository Skill root 및 `creativeops-agent-qa` 노출 확인
- `agent_qa_all.py --help`: base/head/resume Interface 일치
- `agent_qa_executor.py --help`: focused auth Interface 일치
- `git diff --check`: PASS
- QA focused test54, DevTools Node38, frontend lint/build: PASS
- Registry10 scenario/68 assertion, env-example Compose: PASS

Skill은 다음 새 Codex 작업부터 `$creativeops-agent-qa`로 명시 호출할 수 있고, QA·E2E·
Receipt·merge readiness 요청에는 description을 통해 자동 선택될 수 있다. 현재 단계는
Skill Interface 구현과 발견 검증이며, 실제 새 세션의 end-to-end 행동 평가는 후속
baseline 측정에서 수행한다.

이번 작업에는 제품 코드나 QA 실행 구현 변경이 없으므로 비용이 큰 전체 E2E를 반복하지
않았다. Skill discovery와 기존 QA Interface 회귀를 검증했으며, 다음 실제 제품 변경에서
Skill이 선택한 aggregate 실행의 탐색 시간, tool call 수, QA selection precision/recall을
before/after baseline으로 측정한다.

PR 전달 중 `main` protection은 backend/frontend supply-chain check 두 개를 항상 요구하지만
workflow는 제품 경로가 바뀐 PR에서만 실행되어 Skill·문서 PR이 영구 BLOCKED되는 기존
운영 결함을 확인했다. 관리자 merge로 우회하지 않고 `pull_request`에서 required job이
항상 생성되도록 trigger를 수정했다. `main` push의 제품 경로 filter는 그대로 유지한다.
