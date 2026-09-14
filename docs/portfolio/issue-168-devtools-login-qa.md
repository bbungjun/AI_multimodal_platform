# Issue168 — Agent-operated Chrome DevTools login QA

후속 상태: [Issue170](issue-170-favicon-qa.md)에서 favicon을 수정하고 같은 검사를9/9로
재검증했다. 아래 내용과 receipt는 수정 전 Issue168의 실패 증거를 그대로 보존한다.

## 결과와 범위

2026-09-14에 에이전트가 Chrome DevTools MCP로 QA 전용 Chrome을 조작하여
실제 mock OAuth 로그인과 Network/Console 관측, 실행 환경 정리를 수행했다.
**연결·로그인·관측·정리는 검증됨. 제품 전체 QA PASS는 아니다.**
`/favicon.ico` 404가 예상 밖 Console 오류로 탐지되어 엄격한 QA 결과는
`complete=false`, exit code 1로 보존했다. 이 오류를 숨기거나 제품을 수정하지 않았다.

- Issue: [#168](https://github.com/bbungjun/AI_multimodal_platform/issues/168)
- 실행 코드: `85581133fa2d3223efd974bcac70ce12c9463db9`
- 도구: Chrome `153.0.8010.37`, Chrome DevTools MCP `1.9.0`, MCP SDK `1.30.0`.
- 최종 실행: `devtools-login-2073c7943176`, 준비·에이전트 조작·정리 포함 85.563초.
  이 값은 사용자 로그인 latency나 성능 benchmark가 아니다.
- [실행기가 생성한 정제 receipt](../evidence/issue-168/devtools-login-receipt.json).

## 배경과 판단

기존 mock OAuth verifier는 고정된 Playwright driver로 로그인한다. 이번 목적은
에이전트가 화면을 관측하고 다음 도구 호출을 결정할 수 있는지 직접 증명하는 것이다.
따라서 기존 test-only Google Adapter와 owned Compose runtime을 재사용하고,
브라우저 제어는 공식 DevTools MCP의 STDIO 도구 호출로 수행했다.

`scripts/devtools_login_qa.py`가 환경과 정리를 소유하고,
`qa/devtools/agent.mjs`가 대화형 명령을 검증해 MCP 서버에 전달한다.
에이전트는 터미널 stdin에 JSON 명령을 한 단계씩 전달한다. 전역 Codex MCP 설정이나
Hook은 추가하지 않았다. 세션의 MCP 도구 목록에 자동 등록한 것이 아니라,
로컬 MCP client를 통해 같은 서버의 `tools/list`, `tools/call`을 실제 실행했다.

Puppeteer는 Chrome 프로세스 시작/종료, 페이지 요청 차단 및 수동 조작과 독립적인
응답 관측에 사용한다. 제품 페이지 이동과 로그인 클릭은 DevTools MCP로 실행했다.
로그인 POST 직접 호출, 쿠키 주입, 고정 selector로 자동 클릭하는 코드는 없다.

## 실제 검증 과정

1. `.env.example`만 사용하는 격리 Postgres/Redis/backend/dispatcher/worker를 실행.
2. 임시 프로필의 headless Chrome을 시작하고 로컬 디버깅 포트로 MCP 연결.
3. `list_pages` 결과에서 page 1을 선택하고 `navigate_page`로 `/login` 이동.
4. `take_snapshot`에서 실제 로그인 버튼 UID `1_34`를 관측한 뒤 `click` 호출.
   UID는 해당 실행의 snapshot에만 유효하며 재실행 시 새로 관측해야 한다.
5. 로그인 뒤 snapshot에 계정 정보 버튼이 나타나고, 고정된 읽기 전용 DevTools
   DOM probe가 `/generate`의 작업 공간이 표시됨을 확인.
6. `list_network_requests`와 `list_console_messages`로 실행 결과를 검사.
7. `finish`로 검사 결과를 기록하고 MCP/Chrome/Vite를 닫은 뒤 owned Compose 정리.

| 관측 | 실제 결과 | 의미 |
|---|---|---|
| 로그인 전 `/api/auth/me` | 401 | 익명 사용자에게 예상된 응답 |
| 로그인 버튼 클릭 → `/api/auth/google/start` | 307 | 실제 로그인 시작 경로 실행 |
| `/api/auth/google/callback` | 303 | mock Google Adapter를 거친 앱 복귀 |
| 로그인 후 `/api/auth/me` | 200, active user 확인 | 실제 세션 인증 성공; profile 원문 미저장 |
| `/generate` | 작업 공간 표시 | URL뿐 아니라 DOM 영역 크기/visibility 검사 |
| `/favicon.ico` | 404 및 resource-load Console 오류 | 예상 밖 오류 1건; QA FAIL 유지 |
| React Router | future-flag 경고 2종 | 경고로 분류; 로그인 전후 반복 관측 |
| 브라우저 페이지 외부 HTTP 요청 | 0 | 페이지 interception 관측 범위 |
| Chrome/MCP 프로세스 및 Compose cleanup | 모두 0 | 이번 실행이 소유한 자원 정리 |

최종 판정 9개 중 8개가 true이며 `no_unexpected_console_errors`만 false다.
DevTools Network와 Puppeteer 응답 관측이 로그인 status/경로에 대해 일치한다.
`request_id`는 브라우저 DevTools ID이며 backend/worker를 관통하는 trace ID는 아니다.
API health와 이미지 생성, logout/re-login 전체 회귀를 이번 범위의 성공으로 확대하지 않는다.

## 증거·안전 장치

- 패키지 버전과 lockfile은 QA 전용 디렉터리에서 관리; production dependency 변경 없음.
- snapshot은 로그인/계정 버튼의 UID와 label만 모델에 반환. 전체 DOM, 입력값,
  profile 이름, OAuth query, 쿠키, 요청/응답 헤더와 body는 출력·저장하지 않는다.
- Network는 허용한 경로·status·DevTools ID만 저장하고 Console은 종류·status로 정제.
- `/me` 응답은 메모리에서 active user 여부만 비교. 인증 상태를 바꾸지 않는다.
- 임의 JS, 외부 URL 이동, 파일 출력, 관측하지 않은 UID 클릭과 성공 클릭 반복을 거절.
- `verify`의 JS는 고정된 읽기 전용 DOM probe다. 사용자가 임의 스크립트를 전달할 수 없다.
- 페이지 외부 요청을 차단하고 MCP telemetry/CrUX를 비활성화. 이 수치는 Chrome 자체의
  모든 background 통신이나 backend egress 전체에 대한 네트워크 격리 증명이 아니다.
- 제품 소스와 verifier의 hash 및 Git revision을 실행 전후 대조. 문서는 runtime hash에서
  제외한다. hash/receipt는 자체 실행 기록이지 독립된 서명이나 병합 권한 증명이 아니다.
- 이 실행의 자원만 정리한다. 2026-09-07 생성된 다른 stopped verifier 컨테이너와 기존
  다른 프로젝트의 컨테이너를 발견했지만 삭제하지 않았다.

## 실패 기록과 환경 복구

Docker Desktop이 시작 전부터 stale AF_UNIX 소켓 오류로 기동하지 못했다.
오류 창과 해당 소켓의 메타데이터를 확인하고, 이번 시도에서 시작한 Docker 프로세스를
종료한 뒤 런타임 폴더를 백업 이름으로 옮겨 정상 기동을 확인했다.

- `%LOCALAPPDATA%/Docker/run`의 첫 오류는 `dockerInference`; 이후에는
  `%LOCALAPPDATA%/docker-secrets-engine/engine.sock`에서 같은 오류가 나타났다.
- socket-only 폴더임을 확인했으며 파일 내용을 읽지 않았다. 두 번의 `run` 백업과
  `docker-secrets-engine` 백업을 보존했다. Docker 데이터 VHDX, 볼륨, 이미지와 설정은
  초기화하지 않았다. 기존 다른 프로젝트 컨테이너 일부는 엔진 기동 시 자동 시작됐다.
- 백업 이름은 `run.qa168-backup-20260914`, `run.qa168-backup2-20260914`,
  `docker-secrets-engine.qa168-backup-20260914`. 자동 삭제는 하지 않았다.
- 원상 복원이 필요하면 먼저 Docker를 정상 종료하고 현재 socket-only 폴더를 별도
  이름으로 보존한 뒤 해당 백업을 원래 이름으로 옮긴다. 다만 stale socket을 복원하면
  시작 오류가 재발할 수 있다. 데이터 reset/unregister를 복구 절차로 사용하지 않는다.
- 관련 upstream 사례: [Docker Desktop #527](https://github.com/docker/desktop-feedback/issues/527).
  이 호스트에서 OS 내부 원인까지 증명한 것은 아니다.

하네스의 초기 두 시도는 Vite ESM import와 잘못된 plugin import 괄호로 실패했다.
각 실패 후 Compose cleanup 0을 확인했고 수정 후 새 revision으로 재실행했다.
첫 브라우저 실행은 로그인 성공 후 Console 오류를 탐지했으며 Network parser가
`[303]` 형식을 읽지 못해 status 0으로 기록했다. 고정한 MCP 버전의 formatter를 확인하고
parser regression을 추가했다. 마지막 실행에서 `/favicon.ico` 404를 Network와 Console
양쪽으로 특정했다. 기대값을 변경하거나 favicon 요청을 차단해 통과시키지 않았다.

## 재현

필수 조건: Docker 엔진, 로컬 Chrome stable, Node 24 계열, Python 3.11,
frontend 의존성 설치, loopback 18156 사용 가능. `.env`를 읽거나 전달하지 않는다.

```powershell
npm ci --prefix qa/devtools --ignore-scripts --no-audit --no-fund
npm test --prefix qa/devtools
python scripts/devtools_login_qa.py
```

`ready` 이후 같은 터미널에 JSON을 한 줄씩 입력한다. 도구 호출 사이 결과를 확인한다.

```json
{"op":"tools"}
{"op":"call","name":"list_pages","arguments":{}}
```

반환된 pageId로 `/login`을 열고 snapshot을 조회한다. 다음 예시의 pageId는 이 실행의
관측값일 뿐 고정 계약이 아니다.

```json
{"op":"call","name":"navigate_page","arguments":{"pageId":1,"type":"url","url":"http://127.0.0.1:18156/login"}}
{"op":"call","name":"take_snapshot","arguments":{"pageId":1}}
```

그 snapshot에서 받은 로그인 UID로 `click`을 호출한다. 이후:

```json
{"op":"call","name":"take_snapshot","arguments":{"pageId":1}}
{"op":"call","name":"list_network_requests","arguments":{"pageId":1,"includePreservedRequests":true}}
{"op":"call","name":"list_console_messages","arguments":{"pageId":1,"types":["error","warn"],"includePreservedMessages":true}}
{"op":"verify"}
{"op":"finish"}
```

실행별 `output/playwright/devtools-login-*/receipt.json`과 `browser.json`을 확인한다.
Issue168의 favicon 결함이 남은 revision에서는 exit 1이 예상된다. `complete=false`는 엄격한 QA
gate 실패이며, `runtime_cleanup=0`과 `browser.cleanup=0`은 별도로 확인한다.
`finish` 또는 stdin EOF로 종료한다. 10분 대화형 제한과 40개 명령 제한이 있다.

## 검증 명령과 결과

| 검증 | 결과 |
|---|---|
| `npm test --prefix qa/devtools` | 5 PASS: 출력 정제, 클릭 제한, 임의 동작 거부, false PASS 방지, Network format |
| backend focused DevTools/mock OAuth/auth/Google Adapter pytest | 72 PASS / 2 guarded skips |
| 최종 변경 후 DevTools/mock OAuth focused pytest | 6 PASS |
| frontend `npm run lint` / `npm run build` | PASS |
| `.env.example` Compose config / `git diff --check` | PASS |
| `npm audit --prefix qa/devtools --omit=dev --audit-level=high` | 0 vulnerabilities at this run |
| Agent DevTools 실실행 | 로그인 및 관측 성공; favicon 404로 8/9, exit 1; browser/runtime cleanup 0 |

전체 backend suite와 기존 전체 Chromium suite는 이 좁은 test-only 변경에서 로컬 재실행하지
않았다. GitHub 기존 CI는 별도 결과이며 이 대화형 MCP 시나리오를 자동 실행하지 않는다.

## 남은 위험과 다음 작업

- 다음 제품 수정 후보: favicon 404. 별도 변경과 재검증이 필요하다.
- 다음 QA slice: 이미지 생성까지 확장, snapshot/probe 출력 자체의 구조화된 보존,
  명령별 제한과 중단·비정상 종료 cleanup의 fault injection, 시나리오 Skill.
- timeout과 강제 프로세스 종료 복구는 코드가 있지만 실제 fault-injection 검증은 하지 않았다.
  OS 강제 종료 때 임시 프로필/프로세스가 반드시 정리된다고 보장하지 않는다.
- 현재 18156 origin은 기존 test-only OAuth 계약이라 동시 실행을 거부한다.
- 실제 Google, Vertex, 배포 TLS, cross-service trace, 주기적 무인 QA, 자동 병합은 미검증/미구현.
- rollback은 이 Issue의 test-only 파일과 문서 변경을 revert하는 것이다. 제품 schema 변경 없음.
