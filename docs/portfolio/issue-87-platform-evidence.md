# Issue #87 Platform Evidence Design And Record

## 배경과 문제

CreativeOps Studio의 기존 `README.md`는 이미지·영상 생성 사용자 흐름을 먼저
설명한다. 제품은 이해하기 쉽지만, AI Platform Engineer 포트폴리오에서 중요한
Kubernetes 운영, 비동기 job 신뢰성, IaC, 관측성, 배포 rollback, provider failure
처리가 첫 화면에서 드러나지 않는다.

운영 증거도 `docs/current-work.md`, runbook, Terraform, GitHub Actions에 분산되어 있다.
그 결과 다음 문제가 있다.

- 구현된 코드와 실제 클라우드에서 검증한 범위를 빠르게 구분하기 어렵다.
- 과거에 라이브 검증한 스택과 현재 실행 중인 스택을 혼동할 수 있다.
- 장애, 해결 과정, 정량 결과가 긴 handoff 문서에 묻혀 있다.
- 새 polishing 작업이 동일한 문제-해결-결과 구조를 재사용하기 어렵다.

## 목표

1. `README.md` 첫 화면에서 플랫폼 문제, 시스템 구조, 신뢰성 설계, 검증 수준을
   설명한다.
2. 핵심 주장마다 코드, 테스트, runbook 또는 검증 기록으로 이동할 수 있게 한다.
3. `Implemented`, `Live Verified`, `Planned`를 일관된 기준으로 판정한다.
4. Issue별 문제-해결-결과 기록을 위한 `docs/portfolio/` 구조를 만든다.
5. 현재 handoff와 최신 `main`의 상태 차이를 정리한다.

## 제외 범위

- 애플리케이션, API, Terraform 또는 Kubernetes 동작 변경
- 실제 GCP, AWS 또는 Vertex 호출
- 새로운 제품 기능이나 마케팅 랜딩 페이지 추가
- 과거 검증 결과를 현재 라이브 상태처럼 표현하는 것

## 증거 등급

| 등급 | 판정 기준 | 허용되는 표현 |
|---|---|---|
| `Implemented` | 현재 소스에 구현이 있고 관련 자동 테스트, build 또는 정적 검증 근거가 있다. | 구현됨, 자동 검증됨 |
| `Live Verified` | 특정 시점과 revision에서 실제 Compose 또는 cloud runtime을 실행했고 명령, 관측값, 결과가 기록되어 있다. | 해당 날짜/revision에서 실검증됨 |
| `Planned` | 설계, Terraform extension point 또는 Issue만 있고 실제 실행 증거가 없다. | 계획됨, 미검증 |

증거 등급과 현재 운영 상태는 별개다. 예를 들어 과거 GKE 실검증은
`Live Verified`지만, 현재 replica와 node pool이 0이면 상태는 `Paused`로 표시한다.
제거된 AWS 스택도 과거 증거는 유지하되 현재 상태는 `Destroyed`로 표시한다.

## 정보 구조

### README

1. 제품과 플랫폼 문제를 결합한 한 문장
2. 운영 아키텍처 다이어그램
3. 플랫폼 신뢰성 설계
4. 구현·실검증·계획 매트릭스
5. 대표 정량 결과와 장애 사례
6. 제품 생성 흐름과 스크린샷
7. 로컬 실행, API, 문서 링크

### Portfolio Evidence Index

`docs/portfolio/README.md`는 다음 항목의 진입점이 된다.

- Issue별 기록 목록
- 증거 등급 정의
- 플랫폼 capability별 코드/검증/runbook 링크
- 현재 runtime 상태
- 기록 보안 규칙

### Issue Record Template

`docs/portfolio/TEMPLATE.md`는 모든 후속 polishing 작업에서 다음 구조를 사용한다.

1. 배경과 문제
2. 기대 동작과 실제 동작
3. 관측과 원인 분석
4. 해결 방법과 판단 근거
5. 검증 환경, 명령, 정량 결과
6. 결과와 영향
7. rollback 또는 복구
8. 남은 위험과 다음 단계

## Source Of Truth 우선순위

서로 다른 문서의 설명이 충돌할 때는 다음 순서로 판정한다.

1. 현재 코드, Terraform, workflow와 Git 상태
2. 날짜와 revision이 포함된 검증 기록
3. 관련 runbook과 ADR
4. README 요약
5. 향후 계획과 열린 Issue

`docs/current-work.md`는 handoff source of truth지만, 오래된 “다음 작업”이 이미 병합된
경우 현재 Git 이력과 GitHub Issue 상태에 맞춰 갱신한다.

## 보안과 공개 범위

- `.env`, credential, Secret payload, prompt 원문, provider raw response를 읽거나
  포트폴리오 artifact에 복사하지 않는다.
- 포트폴리오 index와 Issue 기록에는 개인 이메일, cloud account number, 실제 project
  ID, 개인 PC absolute path를 넣지 않는다.
- 운영 guard에 필요한 실제 식별자가 별도 설정이나 코드에 존재하더라도 포트폴리오
  요약에서는 `<personal-gcp-project>` 같은 placeholder를 사용한다.
- 긴 로그 대신 재현 명령, 핵심 metric, 안전한 오류 코드와 결과 요약을 보존한다.

## 구현 계획

1. `docs/portfolio/README.md`와 `docs/portfolio/TEMPLATE.md`를 만든다.
2. `README.md`를 플랫폼 중심 순서로 재구성하고 capability matrix를 추가한다.
3. `docs/current-work.md`의 최신 병합 상태와 P0~P3 후속 순서를 정리한다.
4. 포트폴리오 문서에서 계정 식별자와 absolute path 노출 여부를 점검한다.
5. Markdown 링크, `git diff --check`, repository verification을 실행한다.
6. 이 문서에 실제 변경, 검증 결과, 남은 위험을 추가한다.

## 설계 수용 기준

- 한 capability에 하나의 등급과 하나 이상의 근거 링크가 있다.
- “라이브 검증”에는 시점 또는 revision과 관측 결과가 있다.
- 현재 꺼진 인프라를 운영 중이라고 표현하지 않는다.
- 계획 항목은 완료 항목과 같은 문장이나 표 셀에 섞지 않는다.
- README의 제품 사용 흐름과 스크린샷은 제거하지 않는다.

## 구현 결과

### 변경 전과 후

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| README 첫 설명 | 생성 제품과 스크린샷 중심 | 플랫폼 문제, 운영 아키텍처, 신뢰성 설계 중심 |
| 운영 증거 | 긴 handoff와 runbook에 분산 | capability matrix와 evidence index에서 연결 |
| 검증 표현 | 구현과 과거 live 결과가 같은 문맥에 혼재 | evidence level과 현재 runtime state를 분리 |
| Issue 기록 | 공통 구조 없음 | `docs/portfolio/TEMPLATE.md` 추가 |
| 현재 handoff | Issue #49와 #79의 병합 전 문구가 남음 | 최신 `main`과 P0~P3 순서로 갱신 |

### 변경 파일

- `README.md`: 운영 아키텍처, 신뢰성 설계, capability matrix, 대표 정량 증거와
  현재 runtime 상태를 제품 스크린샷보다 앞에 배치했다.
- `docs/portfolio/README.md`: capability별 evidence level, 근거 링크, 현재 상태와
  대표 운영 사례의 진입점을 만들었다.
- `docs/portfolio/TEMPLATE.md`: 후속 Issue가 문제-원인-해결-검증-결과-위험을 같은
  구조로 기록할 수 있게 했다.
- `docs/current-work.md`: 최신 `main` revision, Issue #79 병합 상태, GCP pause 상태,
  Issue #87 작업과 P0~P3 후속 순서를 반영했다.
- `AGENTS.md`: 문서화가 빠진 polishing 작업은 완료로 간주하지 않고 정량 증거와
  실패/No-Go를 보존하도록 규칙을 추가했다.

## 검증

### 환경과 전제조건

- Branch: `codex/issue-87-platform-evidence`
- Base revision: `ec86e91`
- Provider mode: `AI_PROVIDER=mock`
- Cloud/Vertex write: 실행하지 않음

### 명령과 결과

| 명령 또는 시나리오 | 결과 | 판정 |
|---|---|---|
| Markdown local-link 검사 | 수정 문서 6개, local 56개와 external 8개 확인, missing 0개 | Pass |
| GitHub Markdown API render | architecture heading, tables 2개, code block, product images 4개 렌더링; 플랫폼 설명이 제품 흐름보다 먼저 배치됨 | Pass |
| GitHub Actions CI run `33332531974` | Linux `verify` job이 dependency install과 repository quality gate를 33초에 완료 | Pass |
| `git diff --check` | whitespace 오류 없음 | Pass |
| `python scripts/verify_local.py` | Compose 통과, backend 352 통과 후 기존 Windows `/bin/bash` 경로 테스트 1개 실패 | Known environment failure |
| `AI_PROVIDER=mock python -m pytest -k "not test_release_script_guards_plan_scope_and_uses_terraform_rollback"` | 352 passed, 1 deselected | Pass |
| `python scripts/verify_local.py --skip-backend` | Compose config, frontend TypeScript lint, production build 통과 | Pass |
| `npm audit --omit=dev --json` | React Router 계열 production dependency에서 moderate 3건, fix available | Follow-up required |

첫 전체 검증은 로컬 환경에 선언 dependency인 `prometheus-client`가 설치되지 않아
collection 단계에서 중단됐다. `python -m pip install -e ".\\backend[dev]"`로 현재
`pyproject.toml` 의존성을 동기화한 뒤 재실행했다. Frontend도 `node_modules`가 없어
`npm ci`로 lockfile 기준 의존성을 복원했다. 코드나 테스트를 변경해 검증을 우회하지
않았다.

남은 backend 실패는 문서 변경과 무관하며 기존 handoff에도 기록된 Windows native
Python에서 bare `bash`가 WSL `/bin/bash`로 해석되고 Windows absolute path를 변환하지
못하는 문제다. 동일 suite의 나머지 352개 테스트는 통과했다.

## 결과와 영향

- 저장소 첫 화면에서 제품이 아니라 AI Platform Engineer 관점의 운영 문제와 검증
  수준을 먼저 판단할 수 있다.
- GKE, observability, HPA, rollback, provider failure 주장이 실제 코드와 runbook으로
  연결된다.
- 과거 `Live Verified` 결과와 현재 `Paused`/`Destroyed` 상태가 분리되어 과장된
  운영 주장을 방지한다.
- GPU와 분산학습은 `Planned`로 명시되어 실제 구현 전이라는 경계가 유지된다.
- 후속 P1~P3 작업은 동일 template으로 문제, 해결, 정량 결과와 남은 위험을 남길 수
  있다.

이 Issue의 문서 체계 evidence level은 `Implemented`다. 이 변경은 기존 capability의
과거 live evidence를 정리했을 뿐 새로운 cloud live verification을 수행하지 않았다.

## 보안 점검

- 새 `README.md`, `AGENTS.md`, `docs/portfolio/` 문서에는 개인 이메일, cloud account
  number, 실제 project ID와 개인 PC absolute path를 추가하지 않았다.
- `.env`, credential, Terraform state, local tfvars, Secret payload, prompt 원문과
  provider raw response를 읽거나 기록하지 않았다.
- 기존 운영 guard 문서와 non-secret release profile의 project binding은 이
  documentation-only Issue에서 변경하지 않았다. 포트폴리오 index는 해당 값을 노출하지
  않고 일반화된 근거 링크만 제공한다.

## 남은 위험과 다음 단계

- GitHub draft PR에서 실제 Markdown table, code block, image 순서를 최종 확인해야 한다.
- `docs/current-work.md`는 긴 역사 기록이므로 후속 Issue에서 dated evidence를 별도
  portfolio record로 옮겨 검색 비용을 줄일 수 있다.
- Windows bare-bash 테스트 실패는 별도 bug Issue에서 Windows Git Bash path를 명시하는
  방식으로 해결해야 하며 P0 문서 범위에는 포함하지 않는다.
- 2026-08-31 `npm audit --omit=dev`는 React Router 계열 production dependency에서
  moderate 3건을 보고했다. P0 문서 변경에 dependency upgrade를 섞지 않고, 공급망
  후속 Issue #89에서 호환성 검토와 runtime image 재스캔을 수행한다.
- P1~P3의 새로운 live 검증은 각각 Issue #88, #89, #90에서 비용·권한 guard 후 진행한다.
