# Issue172 — Agent가 실행하는 프롬프트 검토·이미지 생성 E2E

## 결과와 검증 범위

**Mock Verified.** 에이전트가 Chrome DevTools MCP로 로그인부터 향상·편집·수락,
이미지 생성, 새로고침, 기록에서 동일 작업 재조회까지 하나의 사용자 시나리오를
직접 수행했다. 제품 코드는 수정하지 않았다.

- [Issue172](https://github.com/bbungjun/AI_multimodal_platform/issues/172)
- 선행 draft PR171(favicon), PR169(DevTools 실행기)에 의존한다. 이번 main 대상
  draft PR에는 선행 PR이 병합되기 전까지 해당 변경도 포함된다.
- 실제 실행 코드: `e262d6b78e0d1c6604f12019d8cd94dc8f9e246a`.
- [최종 receipt](../evidence/issue-172/image-journey-receipt.json):
  `complete=true`, source/revision unchanged, browser/runtime cleanup0.
- Chrome153 / MCP1.9.0, 실제 mock OAuth/backend/Postgres/Redis/dispatcher/worker,
  QA 전용 임시 Chrome 프로필. 실제 Google/Vertex는 사용하지 않았다.

**시나리오는1개다.** 그 안에9개 순서별 checkpoint가 있으며, image checks14개는
9개 checkpoint와5개 요청/관측 조건이다. 기존 공통 checks9개는 로그인과 운영 확인을
포함하고 image login과 중복된다. 이 숫자들을 합쳐 독립적인23개 E2E라고 표현하지 않는다.

## 배경과 구현 판단

기존 DevTools QA는 로그인까지만 확인했다. 실제 콘텐츠 생성에서는 화면에 보이는
프롬프트가 최종 요청에 사용되는지, 비동기 작업과 파일 전달이 완료되는지,
새로고침 뒤에도 결과가 유지되는지를 함께 검증해야 한다.

기존 `scripts/devtools_login_qa.py`에 `--scenario image`를 추가하고 기본 로그인 모드는
유지했다. 기존 Chrome/MCP/Compose 수명 관리를 재사용하며, 새
`qa/devtools/image-journey.mjs`가 이미지 시나리오의 순서·메모리 내 비교·허용 동작을
관리한다. 임의 URL/JS 실행기나 범용 에이전트 프레임워크를 추가하지 않았다.

에이전트는 매번 snapshot의 UID를 읽고 다음 동작을 결정했다. 입력은 fixture 이름만
받으며 실제 텍스트는 로컬 메모리에서 구성한다. DevTools의 클릭 → 전체 선택 →
키보드 입력을 사용한다. 요청은 제품 UI에서 발생하고 직접 POST나 Session 주입은 없다.

## 실제로 확인한 사항

| Checkpoint | 확인한 사용자 동작과 근거 |
|---|---|
| login | 로그인 버튼 클릭, 인증된 작업 공간 표시, start307/callback303/me200 |
| original | 프롬프트 입력란에 원본 fixture 입력, 실제 DOM 값 일치 |
| draft | 향상 버튼 클릭, POST201, 원본 유지와 서버 초안의 화면 표시 일치 |
| edited | 초안 입력란을 키보드로 편집, 원본 입력은 여전히 유지 |
| accepted | 수락 버튼 클릭, 편집 값이 메인 프롬프트에 반영되고 검토 패널 닫힘 |
| completed | 생성 버튼 클릭, 실제 POST의 prompt/enhancement_id/mode/장수/auto_enhance 검사; 저장된 Job 완료와 이미지 디코딩 |
| reloaded | 실제 브라우저 reload, 새 Job 조회 응답, 동일 Job·이미지 경로·파일 hash·디코딩 |
| history | 기록 링크 클릭, 목록 응답과 화면에 이번 실행의 작업 행이 존재 |
| revisited | 관측한 작업 행 클릭, 새 Job 조회 응답, 동일 작업/이미지 재표시·디코딩 |

추가 요청 검사는 향상 입력 일치, 수락한 값과 최종 generation payload 일치,
향상 POST1건, generation POST1건, 응답 관측 실패0이다.

이미지는 PNG header와 MIME/파일 hash를 확인하고 실제 DOM image의 `decode()` 성공,
자연 크기640×360, 표시 영역 존재를 검사했다. 저장된 Job과 asset ID, URL은 메모리에서
비교하고 evidence에는 원문 식별자를 남기지 않는다. 브라우저 관측만으로 정확한
DB 예약/과금이나 outbox 개수를 검증했다고 주장하지 않는다.

## 수치와 증거

| 항목 | 최종 실행 결과 |
|---|---|
| 사용자 시나리오 | 1개 완료, 순서별 checkpoint9/9 |
| 향상/생성 POST | 각각1건 |
| Job 상세 GET 관측 | 4회 |
| PNG 파일 응답 관측 | 2회; 재방문은 브라우저 캐시를 재사용할 수 있음 |
| 생성 이미지 | mock PNG,640×360,556,940 bytes |
| 생성·reload·재방문 이미지 | 동일 asset 경로, 동일 파일 hash, 각각 decode 확인 |
| 예상 밖 Console 오류 | 0; 예상 익명401과 React Router 경고는 별도 분류 |
| 브라우저 페이지 외부 HTTP 요청 | 0; 전체 Chrome/backend egress 측정은 아님 |
| 종료 정리 | browser/MCP/Vite/owned Compose0; QA Chrome 프로세스0,18156 listener 없음 |
| 실행 시간 | 준비·에이전트 입력 간격·정리 포함174.297초; 성능 benchmark 아님 |

최종 실행의32개 action 기록은 UI 행동, snapshot, checkpoint, 진단 명령을 포함한다.
32번 클릭이나32개 사용자 테스트를 뜻하지 않는다. 각 checkpoint마다 DevTools Network
결과를 누적 저장하여 브라우저 탐색 기록의 만료로 초기 인증 증거가 사라지지 않게 했다.

## 관측된 실패와 수정

### 입력 도구의 성공과 제품 상태 반영은 달랐다

첫 시도 `b5f2e61`은 MCP `fill` 이후 초안 DOM 값이 바뀌었지만 수락 후 메인 입력값이
편집한 기대값과 달랐다. 재확인에서도 accepted=false였다. generation을 진행하지 않고
실패 결과와 cleanup0을 남겼다.
[첫 실패 receipt](../evidence/issue-172/initial-input-failure.json).

고정된 프롬프트 계약과 제품 코드를 유지한 채 입력 방식을 DevTools의
`click` → `press_key(Control+A)` → `type_text`로 바꾸자 수락 및 최종 payload 검사가
통과했다. 이는 직접 fill 경로의 입력 반영 문제를 지지하는 실행 증거다. React 내부
원인이나 upstream 결함까지 확정한 것은 아니며 제품 버그로 집계하지 않는다.
입력 중 도구 실패가 나면 후속 입력을 수행하지 않는 focused test도 추가했다.

### 마지막 Network 조회만으로는 전체 여정을 증명할 수 없었다

중간 시도 `d3c8c77`은 이미지 여정은 모두 통과했지만 reload 후 마지막 Network 조회에
초기 로그인 요청이 없었다. DevTools의 preserved requests가 최근 탐색 몇 개만 보존하는
특성으로 공통 `devtools_network_inspected=false`가 되어 전체 실행은 실패했다.
[정제한 중간 실패 요약](../evidence/issue-172/network-retention-failure.json).

각 checkpoint에서 MCP Network를 즉시 수집하고, 반환된 request ID/정규화 경로/status를
누적하도록 수정했다. 최종 판정은 실제 DevTools가 관측한 인증·향상·생성·파일 응답을
모두 요구한다. Puppeteer가 본 응답을 DevTools의 누락된 결과로 대신 채우지 않았다.
마지막 실행 `e262d6b`에서 동일 제품 흐름과 증거 요건이 함께 통과했다.

## 실행·재현

기존 [Issue168 실행 조건](issue-168-devtools-login-qa.md#재현)을 따른다.

```powershell
npm ci --prefix qa/devtools --ignore-scripts --no-audit --no-fund
npm test --prefix qa/devtools
python scripts/devtools_login_qa.py --scenario image
```

`ready` 이후 에이전트는 `list_pages`, `/login` navigate, snapshot, 관측한 로그인 UID로
click을 수행한다. 각 단계에서 snapshot을 다시 읽는다. 아래는 명령 형식이며 UID는
실제 snapshot에서 얻은 값으로 대체해야 한다.

```json
{"op":"checkpoint","phase":"login"}
{"op":"call","name":"take_snapshot","arguments":{"pageId":1}}
{"op":"call","name":"fill","arguments":{"pageId":1,"uid":"OBSERVED_UID","fixture":"original"}}
{"op":"checkpoint","phase":"original"}
```

향상 클릭 후 `draft`, 초안 입력(`fixture=reviewed`) 후 `edited`, 수락 클릭 후 `accepted`,
생성 클릭 후 `completed`를 확인한다. 각 성공은 다음 단계의 전제조건이다.
이미지 생성 완료는 비동기이므로 checkpoint가 아직 false면 화면/요청을 다시 관측하고
같은 checkpoint를 재확인한다. 실패한 제품 동작을 통과로 바꾸지 않는다.

```json
{"op":"call","name":"navigate_page","arguments":{"pageId":1,"type":"reload"}}
{"op":"checkpoint","phase":"reloaded"}
```

이어서 관측한 기록 링크 클릭 → `history` → 관측한 작업 행 클릭 → `revisited`.
Network와 Console을 조회하고 `finish`한다. 기본 login 모드는 기존 명령을 사용한다.

실행마다 임시 프로필·격리 DB를 새로 만든다. 입력 fixture/사용자 상태/기대값을
준비하는 것과 실행 중 DOM·응답을 조작하여 통과시키는 것을 구분한다.
이미지 모드는80개 명령/10분 대화형 제한을 적용하고, 생성·향상 클릭 시도는 각1회로
제한한다. 클릭 timeout은 요청 미발생을 뜻하지 않으므로 자동 재클릭하지 않는다.

## 코드 검증과 운영 한계

- `npm test --prefix qa/devtools`:14 PASS. 잘못된 payload, 누락된 decode/응답,
  다른 Job/이미지, 불충분한 reload/revisit 증거, 중복 POST, 순서·입력 제한,
  출력 정제와 누적 Network 요구 조건을 검사한다. 독립 E2E14건이 아닌 하네스 테스트다.
- DevTools/mock OAuth focused Python tests6 PASS, frontend lint/build PASS,
  `.env.example` Compose config와 `git diff --check` PASS.
- 최종 live local mock 실행 exit0, source/revision unchanged, cleanup0.
- 전체 backend/Chromium suite는 로컬 재실행하지 않았다. GitHub CI와 별도이며,
  현재 CI가 이 대화형 에이전트 시나리오를 자동 실행하는 것은 아니다.
- 기존 API/state machine/storage를 거친 제품 동작을 검사한다. 정책 변경, migration,
  Hook, global MCP 설정, Skill, merge automation은 추가하지 않았다.
- asset 파일 자체와 프롬프트/응답/사용자 식별자는 evidence에 저장하지 않는다.
  controls는 UID·role·purpose·disabled, probe는 boolean/숫자만 보존한다.
- PNG는 mock placeholder다. 이미지의 의미·미적 품질 또는 실제 Imagen 성능은 검증하지 않았다.
- 실제 Google/TLS/Vertex, 영상, 다운로드, 다른 사용자 소유권, 과금/예약, 실패 재시도,
  모든 history 필터·페이지 이동은 이번 사용자 시나리오에 포함되지 않는다.
- 같은 revision 반복 안정성/flake 비율과 강제 종료 복구는 별도 검증이 필요하다.
- rollback은 이번 test-only 시나리오 확장을 revert하는 것이다. 기존 사용자 데이터와
  제품 schema에는 변경이 없다. 다음 단계는 검증한 절차를 재사용 가능한 QA Skill로 정리하는 것이다.
