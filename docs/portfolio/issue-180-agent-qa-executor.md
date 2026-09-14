# Issue180 — Agent QA Chrome DevTools Executor 첫 수직 slice

- [Issue180](https://github.com/bbungjun/AI_multimodal_platform/issues/180)
- [일반 PR181](https://github.com/bbungjun/AI_multimodal_platform/pull/181)
- [정제 evidence](../evidence/issue-180/executor-summary.json)
- 선행 merge: [PR177](https://github.com/bbungjun/AI_multimodal_platform/pull/177),
  [PR179](https://github.com/bbungjun/AI_multimodal_platform/pull/179)

## 결과

`auth_login`을 Selection Manifest부터 owned runtime, 실제 Chrome DevTools MCP 행동,
contract assertion과 cleanup까지 연결한 첫 완전한 실행 Adapter로 구현했다. Core
`0e1f48c1b87b03505aaaa9a6e18b8c9bd1b21a1e`에서 동일 revision 2회가 PASS했다.

이 결과는 전체 10개 QA 자동화가 아니다. 현재 Adapter는 `auth_login` 하나만 실행하며,
FULL_E2E 선택의 나머지9개는 아직 실행되지 않았으므로 전체 QA PASS나 merge 승인으로
표현하지 않는다.

## 문제와 설계

기존 `scripts/devtools_login_qa.py`는 Agent가 stdin으로 MCP 명령을 선택하는 연결 proof와
이미지 journey를 제공했지만 Impact Selection, Registry assertion ID, 자동화된 logout,
실행 전후 revision/source, scenario 단위 결과가 하나의 Interface로 연결되지 않았다.

새 외부 Interface는 다음 명령 하나다.

```powershell
python scripts/agent_qa_executor.py `
  --base <40자리-base-SHA> `
  --head <현재-HEAD-40자리-SHA> `
  --scenario auth_login
```

Python Module이 immutable revision, clean tracked source, Registry/Policy/Selection SHA,
owned Docker lifecycle과 최종 판정을 소유한다. Node Adapter는 Chrome을 실행하고
Chrome DevTools MCP의 navigation, accessibility snapshot, click, wait, read-only probe,
Network/Console 도구만 사용한다. Puppeteer는 Chrome 시작과 외부 요청 차단/response
cross-check에만 사용하며 사용자 행동을 대신하지 않는다.

브라우저가 쓴 JSON은 그대로 신뢰하지 않는다. Python seam이 허용된 route/status/method,
boolean, count, 버전, 정확한 assertion field만 다시 정제한다. extra identity field,
unknown route와 raw body는 거부한다. DevTools assertion false는 `FAIL`, 도구/evidence/
source/cleanup 실패는 `BLOCKED`다.

## 실행 흐름

1. 현재 HEAD가 입력 head와 같은지, tracked source가 clean인지 검사한다.
2. base/head diff로 Impact Selection을 재생성하고 `auth_login` 선택을 확인한다.
3. fresh mock OAuth Postgres/Redis/backend/dispatcher/worker를 시작한다.
4. Vite와 fresh Chrome profile, Chrome DevTools MCP를 시작한다.
5. `/login`에서 실제 Google 계속하기 control을 snapshot으로 찾고 클릭한다.
6. start307, callback303, me200과 `/generate`를 확인한다.
7. 실제 계정 정보와 로그아웃 control을 차례로 클릭한다.
8. browser context에서 `/api/auth/me`를 다시 읽어401, 최종 `/login`을 확인한다.
9. Network/Console과 browser response를 정제·cross-check한다.
10. browser/MCP/Vite/runtime을 모두 정리한 뒤 runtime evidence를 assertion에 결합한다.

## 실패 이력과 원인 분석

성공 전 BLOCKED 9건을 삭제하거나 PASS로 다시 쓰지 않고 원인 범주와 조치를 기록했다.

| 단계 | 관측 | 원인/조치 |
|---|---|---|
| 첫 실행 | browser/MCP/Vite0, runtime cleanup1 | Temporary Compose 파일 삭제 후 cleanup 호출. cleanup을 디렉터리 생존 구간 안으로 이동 |
| 초기 navigation | `login_navigation` BLOCKED | 초기 탭 `about:blank`에 서비스 origin을 요구. navigation 전에는 page ID만 읽도록 수정 |
| 로그인 완료 후 | `authenticated_page` BLOCKED | `list_pages` 문자열 형식 의존. 고정 read-only pathname probe로 교체 |
| 반복 runtime | Docker `ps`/Engine API 실패 | Docker daemon이 응답 불가와500을 반환하고 Desktop이 종료됨 |
| Docker 시작 | `dockerInference` ReparsePoint 제거 실패 | Docker 프로세스0과 socket-only 내용을 확인 후 두 socket directory를 timestamp backup으로 이동 |
| 복구 | Engine29.2.1 ready | factory reset과 image/volume 삭제 없이 동일 revision 재실행 |

개별 AF_UNIX socket 파일은 Windows에서 이동이 거부돼 변경되지 않았다. 이후 socket-only
부모 directory2개를 recoverable backup으로 이동했고 Docker가 새 directory를 만들었다.
백업은 개인 PC 로컬 상태이며 repo 문서에는 absolute path를 기록하지 않는다.

## 검증 결과

### 실제 Chrome DevTools 실행

| Metric | Run1 | Run2 |
|---|---:|---:|
| Contract assertion | 7/7 | 7/7 |
| 정제 Network 행 | 6 | 6 |
| External page request | 0 | 0 |
| Unexpected Console error | 0 | 0 |
| DevTools/browser response cross-check | true | true |
| Cleanup browser/MCP/Vite/runtime | 0/0/0/0 | 0/0/0/0 |
| 실행 시간 | 31.422s | 29.875s |

관측한 핵심 응답은 login start307, callback303, authenticated me200, logout204,
logout 후 me401이다. 최종 route는 `/login`이다. OAuth query, cookie, profile/identity,
header/body는 raw evidence에 저장하지 않았다.

### 자동 회귀

| 검증 | 결과 |
|---|---|
| Registry/Selector/Executor focused | 56 PASS |
| Node DevTools parser·contract | 22 PASS |
| backend 전체 | 1862 PASS, 3 guarded SKIP, 기존 Windows/Bash path 1 FAIL |
| backend 기존 path 검사만 제외 | 1862 PASS, 3 SKIP, 1 deselected |
| frontend lint/build | PASS |
| `.env.example` Compose config | PASS |
| `git diff --check` | PASS |

전체 backend의 유일한 실패는 기존 Windows absolute path를 `bash -n`에 전달하는
host-path 검사다. 이번 Executor/제품 회귀와 무관하며 동일 검사만 제외한 전체1862개는
통과했다. Unit fake report가 실제 output에 섞이던 결함도 발견해 pytest temp directory로
격리했다. 기존 local raw artifact19개는 삭제 대신 repo-relative tmp backup으로 이동했다.

## 결과와 남은 위험

- Evidence level: `Mock Verified` for `auth_login` only.
- Selection SHA와 실행 revision에 묶인 실제 Chrome 행동 증거가 생겼다.
- source 변경, 외부 요청, Console 오류, Network 불일치, cleanup 미확인은 PASS 불가다.
- Docker 장애와 harness 결함을 제품 FAIL과 구분해 BLOCKED로 처리했다.

다음은 prompt/T2I, T2V, I2V, Pipeline, History, Usage, failure/retry, role/Master Adapter다.
그 뒤 10개 scenario 결과를 Issue176 Receipt로 집계하고 CI required gate를 연결한다.
실제 Google/Vertex, cloud ingress, mobile과 concurrency는 별도 live profile 없이는 증명하지
않는다.
