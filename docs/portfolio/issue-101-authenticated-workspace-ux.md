# Issue #101 — 기존 UI를 유지하는 로그인·Session UX

- Issue: [#101](https://github.com/bbungjun/AI_multimodal_platform/issues/101)
- 상태: **Mock Verified**, [Draft PR #102](https://github.com/bbungjun/AI_multimodal_platform/pull/102)
  전달. 구현 head `3b82c12` 필수 CI 모두 PASS; merge/Live Verified 아님.
- 기준: G3 병합 `edd7208`; 구현/브라우저 검증 `58542f5`; CI 연결 `6aaf3ad`.
- 범위: non-document 17개, 상한 20개 중 여유 미사용, migration 0개.
- 설계: [accepted spec](../initiatives/g3-1-authenticated-workspace-ux-spec.md).

## 배경과 문제

G3는 Google OAuth·Session backend를 제공했지만 첫 화면은 인증을 확인하지 않고
작업 페이지를 mount했다. sidebar 사용자 표시는 고정 값이었고 920px 이하에서는
footer 자체가 숨겨져 계정 기능을 단순 교체하는 것만으로 모바일 접근을 제공할 수 없었다.
전역 QueryClient는 사용자 수명과 무관했다. 계정 A의 늦은 응답이 계정 B의 화면으로
넘어가거나, 로그아웃 timeout을 성공처럼 안내하면 신뢰할 수 없는 UX가 된다.

## 관측과 원인 분석

- App/main에서 모든 route와 전역 query cache의 수명을 확인했다. 생성 성공 콜백은
  작업 상세로 이동하므로 query cache만 비워서는 늦은 mutation의 화면 이동을 막지 못한다.
- CSS 뒤쪽 `.creative-*`가 실제 보라색/어두운 스타일을 정의했고, <=920px 규칙이
  footer를 숨겼다. 첫 root 색상만 보고 새로운 디자인을 만드는 접근은 제외했다.
- bootstrap/복귀 경로/늦은 응답/활동 검증의 RED 계약 4개를 먼저 만들었다. import나
  테스트 수집 오류가 아닌 실제 assertion 실패였으며 구현 후 모두 통과했다.
- 최초 확장 browser matrix는 **30 PASS / 4 FAIL**이었다. 920px 계정 panel 오른쪽
  끝이 958.1px로 화면 밖에 있었고, 나머지 세 viewport는 outside pointerdown 처리 후
  브라우저 기본 focus 이동이 trigger focus를 덮어썼다. 실패를 생략하지 않았다.
- Windows 전체 backend의 단일 Bash 경로 실패는 baseline `edd7208` 추출본에서도
  동일하게 재현됐다. 해당 script/test는 변경되지 않았으며 Linux에서는 통과했다.

## 해결 방법과 판단 근거

하나의 deep browser Session module이 확인/오류/복귀 경로/epoch를 숨기고 UI에는
`useSession()`의 view와 login/retry/logout만 제공한다. HTTP·navigation·clock seam에
실제 adapter와 deterministic test adapter를 연결했다.

- `/me`가 검증되기 전 작업 페이지/query를 mount하지 않는다. 401과 서비스 장애,
  로그아웃 결과 불명 상태를 구분하며 일반 작업 403/5xx를 모두 logout으로 바꾸지 않는다.
- 사용자 admission epoch마다 QueryClient를 새로 만들고 이전 cache를 취소·폐기한다.
  HTTP 응답도 요청 시작 epoch를 검사하여 오래된 mutation의 성공 콜백까지 차단한다.
- timer 인증 heartbeat를 넣지 않는다. visible focus/실제 pointer·keyboard 활동이
  5분 이상 간격일 때만 재확인하고 동시 요청을 합친다. logout 신호에는 비밀값이 없다.
- 전체 OAuth 이동·잠금 때 미제출 입력은 초기화하며 UI에 알린다. profile/prompt를
  브라우저 저장소에 보존하는 편의 구현은 제외했다. 저장 가능한 것은 10분 TTL의
  allowlist 복귀 경로 한 항목뿐이며 저장소가 차단돼도 로그인 흐름은 유지한다.
- desktop footer/mobile topbar를 재사용했다. 계정 정보는 disclosure로 제공하고
  외부 avatar 요청, 신규 UI library, Plan/Master 기능은 추가하지 않았다.
- 920px panel은 오른쪽 기준, 좁은 mobile은 왼쪽 기준으로 배치했다. outside close는
  native focus 이동 후 click에서 처리하여 trigger로 복귀시킨다.
- backend는 정확히 한 개 `ui=1`에서만 start 오류를 설정된 frontend로 303 redirect한다.
  기존 503 JSON/307 성공, callback/me/logout, OAuth 정책과 schema는 그대로다.

## 실행 검증

| 검증 | 실제 결과 |
|---|---|
| `npm ci`, `npm run lint`, `npm run build` | PASS |
| `npm run test:auth` | 48 PASS (최종 review에서 4개 보강) |
| `npm run test:auth:browser` | 수정 후 34 PASS |
| focused G3 auth suite | 56 PASS / 기존 guarded integration 3 SKIP |
| Windows 전체 pytest | 466 PASS / 3 SKIP / 기존 Bash 경로 1 FAIL |
| baseline의 해당 Bash test 재현 | 같은 실패 1개 / 5 deselected |
| clean Linux container 전체 pytest (`58542f5` archive) | 467 PASS / 기존 guarded integration 3 SKIP |
| `tests/test_ci_workflow.py` | 7 PASS |
| Compose example config quiet / diff hygiene | PASS |
| 격리 mock golden 및 cleanup | PASS / 해당 containers·volumes 0 |

Frontend 명령은 `frontend`에서 실행하며 Chromium 설치는
`npx playwright install chromium`, CI는 `--with-deps chromium`을 사용한다.
Backend focused 명령은 `AI_PROVIDER=mock`에서 다음과 같다:

```powershell
python -m pytest tests/test_auth_api.py tests/test_auth_service.py tests/test_google_identity_adapter.py tests/test_oauth_flow_store.py -q
```

Linux는 tracked source의 `git archive`만 새 Python 3.11 container에 전달하고
`python -m pip install ".[dev]"` 후 `python -m pytest -q`로 검증했다. host dotenv나
credential을 mount하지 않았다. 세 opt-in skip은 G3의 real Postgres/Redis 검증용이다.
이번 변경에서 core를 바꾸지 않았으므로 두 cycle을 재실행한 것처럼 주장하지 않는다.

Browser는 Chromium 실제 frontend + test-only HTTP fixture다. 모든 외부 origin과
미처리 API/files 요청을 차단했고 credential·Google·profile image를 사용하지 않았다.
1440x900, 920x900, 390x844, 320x720에서 기존 화면/로그인/계정/장애 화면을 직접
확인했다. 초기 private 요청 0, idle 12시간 자동 auth 요청 0, single-start, timeout,
숨은 탭, sibling logout, A→B의 늦은 조회/401/생성 응답, 키보드 focus와 clipping을 검사했다.

실제 Postgres/Redis/worker를 사용한 생성 회귀는 별도다. fresh project
`g31-verify-93f50e9bfa31`에서 mock health → enhancement → generation → polling →
asset metadata/bytes/Range → cleanup이 통과했다. 자체 DB/assets volume과 container만
정리했고 기존 개발 project는 변경하지 않았다. 실행 명령/guard는
[local-mock runbook](../runbooks/local-mock.md#isolated-g31-generation-regression)에 있다.

## 결과와 영향

인증 확인 전 작업 화면 노출을 막고 모바일에도 계정·로그아웃 경로가 생겼다. 장애를
로그아웃 성공으로 잘못 표시하지 않으며, 계정 전환 뒤 이전 응답이 새 화면을 바꾸지
않는 것을 검증했다. 사용자 전환율·시간 절감·실제 운영 장애 감소는 측정하지 않았으므로
성과 수치로 주장하지 않는다. 전체 비교는 기존 UI 유지와 새 상태 처리의 차이다.

로컬 masked captures: `.omo/evidence/issue-101/screens/`의 `baseline-*`,
`authenticated-*`, `login-*`, `account-*`, `unavailable-*`. 원본 식별정보/prompt/trace/
HAR/cookie dump는 보존하지 않는다. 이 경로와 progress receipt는 **untracked/local**이며
GitHub에서 다운로드할 수 있는 artifact가 아니다. 공유 문서에는 재현 절차와 요약만 남긴다.

## Rollback과 남은 위험

- G3.1 frontend/CI와 opt-in redirect 변경을 review된 revert PR로 되돌린다. DB migration은
  없고 G3 기본 계약은 유지된다. UI rollback이 이미 발급된 Session을 폐기하지는 않는다.
- 로그인 gate는 backend 접근 통제가 아니다. G4의 Job/Prompt/Asset ownership 이전에는
  공개 배포를 허용할 수준의 사용자별 보호가 아니다.
- 실제 Google 로그인·cookie/proxy 환경 검증, 긴급 폐기 #99, 비용/크레딧/Master는 별도다.
- 입력 초안 영속화는 의도적으로 제외했다. 불확실한 logout은 명시적으로 재확인해야 한다.
- npm audit의 advisory는 현재/기존 `edd7208` 모두 9개, 신규 advisory 패키지 0개였다.
  광범위 업그레이드로 숨기지 않았으며 runtime image의 required security scans와 구분한다.
- 로컬 F1-F4는 아래 근거로 APPROVE했다. Draft PR의 current-head 필수 CI가 완료돼야
  Goal을 종료한다. 이번 Goal은 ready/auto-merge/merge 권한을 포함하지 않는다.

## 최종 review

| Gate | 결정 / 근거 |
|---|---|
| F1 scope | APPROVE — 17 non-document paths, migration 0, generation page/core/ownership/cloud 변경 없음 |
| F2 state/security | APPROVE — module 48, browser races/idle/logout, backend 호환 test 통과; bundle에서 fixture identity/endpoint/test marker 없음 |
| F3 runtime/UX | APPROVE (local) — Chromium 34, 네 viewport와 keyboard 직접 검토, Linux 467/3 conditional skip, isolated golden과 cleanup 통과 |
| F4 documentation | APPROVE — 문제/실패/수정/검증/한계와 local-only artifact를 spec/runbook/testing/current-work에 구분 기록 |

## Remote CI delivery

구현 head `3b82c12`에서 다음 필수 check가 모두 통과했다.

- [verify](https://github.com/bbungjun/AI_multimodal_platform/actions/runs/33663156208):
  Linux backend 467 PASS / guarded3 SKIP, module48 PASS, Chromium34 PASS, lint/build PASS.
- [backend/frontend Scan and SBOM](https://github.com/bbungjun/AI_multimodal_platform/actions/runs/33663156200):
  두 runtime image 모두 PASS. scan 기준이나 branch protection을 낮추지 않았다.

이 결과를 기록하는 마지막 변경은 문서-only이며 해당 head의 세 required check도 다시
확인한다. 이후 상태는 [PR #102](https://github.com/bbungjun/AI_multimodal_platform/pull/102)의
current-head checks를 기준으로 한다. Draft 유지, auto-merge off, Issue #101 open이다.
