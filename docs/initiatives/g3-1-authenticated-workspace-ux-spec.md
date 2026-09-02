# G3.1 — 기존 UI를 유지하는 로그인·Session UX 설계

## 1. 상태와 목적

- 상태: **Accepted — 2026-09-03 사용자 승인**. 구현·브라우저 검증은 시작하지 않았다.
- Tracker: [Issue #101](https://github.com/bbungjun/AI_multimodal_platform/issues/101).
- Branch: `codex/issue-101-authenticated-workspace-ux`, synced `main` `edd7208` 기반.
- 설계 기준: G3가 병합된 `main` revision `edd7208`, [PR #100](https://github.com/bbungjun/AI_multimodal_platform/pull/100).
- 전체 합의: [인증·크레딧 initiative](auth-credits-master-console.md).
- 선행 interface: [G3 spec의 HTTP / Cookie Contract](g3-auth-session-lifecycle-spec.md#http-contract).
- 사용자 확정 방향: 기존 UI/UX, CSS, 배치와 공통 UI를 유지한다. 리디자인하지 않는다.
- 아래 동작·검증·경로 예산과 여섯 승인 항목은 확정되었다. Goal 실행은 별도 명시 요청으로 시작한다.
- 설계 단계 확인: 기존 frontend lint/build PASS, 문서 링크·diff hygiene·신규 spec 안전 검사
  PASS. 이것은 baseline/문서 검증이며 새 로그인 UX의 테스트 결과가 아니다.

목표는 이미 구현된 backend 인증을 기존 작업공간에 연결하는 하나의 delivery slice다.
Google 인증 자체를 다시 만들거나 개인 작업 소유권까지 구현하지 않는다. 기본 로그인,
세션 확인, 계정 표시, 로그아웃, 만료·통신 오류를 동일한 시각 언어로 제공한다.

## 2. 현재 코드에서 확인한 문제

| 관측 | 설계에 미치는 영향 |
|---|---|
| `App.tsx`의 모든 작업 route가 즉시 mount된다. | 초기 인증 확인 전에는 작업 page/query를 mount하지 않는 gate가 필요하다. |
| 사이드바 사용자 이름/이니셜이 고정 값이다. | 현재 위치를 그대로 사용하면서 `/me`의 사용자 표시로 교체한다. |
| 920px 이하에서 `.creative-sidebar__footer`가 숨겨진다. | 작은 화면에서는 상단 action 영역에 같은 계정 기능을 노출해야 한다. |
| CSS 앞부분과 뒤의 `.creative-*` override가 다른 톤을 정의한다. | 첫 `:root`만 보고 색을 새로 고르지 않고 실제 적용되는 보라색·어두운 shell 스타일을 따른다. |
| QueryClient가 한 개이고 사용자 수명과 무관하다. | 로그아웃/계정 변경 후 이전 응답·캐시가 새 계정 화면에 나타나지 않게 해야 한다. |
| `/me`는 정상 확인 때 backend 활동시각을 갱신할 수 있다. | 타이머 폴링이나 health polling을 로그인 유지 장치로 사용하지 않는다. |
| Google start 오류는 503 JSON, callback 오류는 root redirect다. | 브라우저 이동 실패를 기존 앱의 오류 화면에 연결할 최소 호환 확장이 필요하다. |
| frontend 검증은 typecheck/build뿐이고 browser test runner가 없다. | 인증 상태·메뉴·이동·race를 검증할 test-only browser 도구를 추가한다. |

## 3. 포함 / 제외 범위

포함:

- `/login` 화면과 초기 인증 확인 화면, 작업공간 진입 gate.
- `/me` 연동, 기존 사용자 카드 교체, 모바일 계정 버튼, 로그아웃.
- 로그인 취소/오류, 만료, 통신 장애, 로그아웃 결과 불명 상태의 구분.
- 안전한 복귀 경로, 계정 전환 시 캐시 폐기, 늦은 응답 무효화, 탭 간 로그아웃 신호.
- G3 start의 **opt-in browser error redirect** 하나, 관련 backend regression test.
- 기존 스타일 재사용, 키보드·모바일 검증, 외부 호출 없는 자동 테스트와 포트폴리오 기록.

제외:

- OAuth 검증/Session 정책/DB/migration 변경, 새 identity provider나 product fake login.
- Job/Prompt Enhancement/Asset의 backend 인증·소유권 정책(G4).
- Plan/Credit/Usage, Master 메뉴·승격·정지·Audit, 긴급 세션 일괄 폐기(#99).
- 생성 page의 form/model/submit 동작 변경, 초안 영속화, 자동 job 재제출/취소.
- 전역 리디자인, UI framework 추가, CSS 재정리, 무관한 고정 통계/브랜드 문구 정리.
- 실제 Google 로그인, 외부 프로필 이미지 요청, AI provider 호출, cloud/배포 변경.

**중요:** G3.1 gate는 브라우저 UX다. G4 전까지 기존 backend 작업 API와 파일은 사용자별로
보호되지 않는다. 로그인 화면을 만들었다는 이유로 공개 서비스의 접근 통제가 완성됐다고
표현하거나 배포하지 않는다. mock 모드도 로그인 우회 모드로 바꾸지 않는다.

## 4. 화면과 기존 CSS 재사용

| 위치 / 상태 | UI와 재사용 규칙 |
|---|---|
| 초기 확인 | 기존 shell 안에 작은 상태 panel과 `로그인 상태 확인 중` 문구. 작업 목록/폼과 임시 사용자 정보는 표시하지 않는다. |
| 비로그인 `/login` | 기존 workspace 영역에 폭 제한 panel. CreativeOps 이름, 짧은 설명, `Google로 계속하기` CTA 하나. 새 landing page/hero/가격표는 없다. |
| 로그인 성공 | 기존 생성/기록/작업 상세의 DOM 배치와 시각 스타일을 유지한다. |
| desktop 계정 | 기존 sidebar footer 사용자 카드 위치. 이름 또는 `사용자`, 로컬 이니셜 avatar, 계정 정보 펼치기와 로그아웃. |
| <=920px 계정 | 기존 topbar actions 안에 같은 기능의 작은 버튼. desktop/mobile 중 보이는 것만 tab 순서에 들어간다. |
| 계정 펼침 | 일반 disclosure + 버튼을 사용한다. 불완전한 ARIA menu 역할을 붙이지 않는다. Escape/외부 클릭으로 닫고 trigger로 focus를 돌린다. |
| 만료/폐기 | `로그인이 만료되었거나 종료되었습니다. 다시 로그인해 주세요.` 구체적 backend 원인을 추측하지 않는다. |
| 통신 장애 | `로그인 상태를 확인할 수 없습니다.` + `다시 확인`. 신규 로그인 필요 상태와 혼동하지 않는다. |
| logout 처리/불명 | 중복 버튼 비활성화. 성공 확인 전 `로그아웃되었습니다`라고 표시하지 않는다. |

- `components/ui.tsx`의 `Button`, `Panel`, `Badge`, 기존 icons/copy 패턴을 재사용한다.
- CSS는 `index.css` 끝에 `.creative-auth-*`, `.creative-account-*` 범위만 최소 추가한다.
  기존 `:root`, `.button`, `.panel`, generation selectors를 전역 재정의하지 않는다.
- 배경/문자/간격/테두리는 기존 값과 실제 `.creative-*` 스타일을 따른다. 새 스타일이 필요한
  로그인 CTA와 focus outline만 auth 범위에서 정의한다. Google 로고 asset은 새로 도입하지 않는다.
- 외부 profile image 대신 로컬 이니셜을 기본으로 사용한다. 이메일은 계정 정보 펼침 안에만
  표시하며 raw User ID, Session, provider 값, 임의 Plan badge는 보여주지 않는다.
- 1440×900, 920×900, 390×844, 320×720에서 가로 overflow/잘린 CTA/숨은 logout을 검사한다.
- 상태 문구는 `role=status`, 오류는 적절한 alert, 명시적 label과 focus-visible을 제공한다.
  강제 animation은 추가하지 않고 reduced-motion 설정을 존중한다.

## 5. 사용자 흐름과 상태

| 사건 | 상태 전이 / 동작 |
|---|---|
| 첫 방문/새로고침 | `checking` → `/me` 확인. 200이면 `authenticated`, 401이면 `anonymous`, 나머지 실패는 `unavailable`. |
| 보호된 UI route의 401 | 원래 목적지를 검증하여 `/login`으로 replace. 작업 page는 mount하지 않는다. |
| 로그인 CTA | 중복 이동 차단 후 같은 origin의 Google start로 **전체 페이지 이동**. fetch로 Google redirect를 따라가지 않는다. |
| callback 성공 후 앱 복귀 | URL이나 성공 문구를 신뢰하지 않고 `/me` 200으로 사용자와 작업공간 진입을 확정한다. |
| callback/start 실패 | allowlist의 `auth_error`만 한국어 문구로 매핑하고 주소에서 제거한다. 임의 error description은 렌더링하지 않는다. |
| 이미 로그인한 사용자의 `/login` | 재인증 버튼 없이 검증된 복귀 route 또는 `/generate`로 replace한다. |
| 기존 로그인 사용자의 401 | 즉시 이전 사용자/작업 화면·캐시를 폐기하고 재로그인 안내. 기존 요청을 자동 재실행하지 않는다. |
| `/me` 5xx/timeout/invalid profile | 성공으로 간주하지 않고 gate를 잠근다. 사용자에게 수동 재확인을 제공한다. |
| 작업 API의 403/5xx | 그 작업의 기존 오류 처리 유지. 모든 403/5xx를 로그아웃으로 바꾸지 않는다. |
| logout 시작 | `signing-out`, 작업 화면/캐시 제거, 중복 POST 차단. 서버 job을 취소하지 않는다. |
| logout 204 | `anonymous`, `/login` replace, 다른 탭에 비밀값 없는 invalidation 신호 전송. |
| logout 실패/timeout/403/503 | `logout-unconfirmed`; 화면은 잠근 채 재시도 또는 명시적 상태 확인. 브라우저가 cookie를 삭제했는지 추정하지 않는다. |

### 복귀 경로와 입력 보존

- 기본 복귀는 `/generate`. `/generate`, `/history`, `/ops`, UUID 기반 `/jobs/...`,
  `/pipelines/...`만 허용한다. `/login`, `/api/...`, 외부 URL, protocol-relative URL,
  제어문자/역슬래시/과도한 인코딩/512-byte 초과 값은 거절한다.
- `/generate`의 기존 `mode` enum과 UUID `source_asset_id`만 query allowlist에 넣는다.
  나머지 query/fragment는 버린다. return URL에 prompt나 오류 원문을 넣지 않는다.
- 실패 후 재시도 목적지를 유지할 필요가 있는 경우에만 sessionStorage에 검증된
  `{returnTo, createdAt}` 한 항목을 저장한다. TTL 10분, 성공/로그아웃 후 삭제한다.
  저장이 차단되면 memory/default path로 저하되며 로그인 자체는 실패하지 않는다.
- 사용자 profile, credential, Session, prompt, enhancement, asset 응답을 localStorage나
  sessionStorage에 저장하지 않는다. 로그인 성공 근거로 저장소 값을 사용하지 않는다.
- **확정 정책:** 만료·계정 전환·전체 OAuth 이동, 또는 인증 확인 실패로 작업 gate가 잠길 때
  미제출 form은 초기화된다. 정상 background 재확인은 기존 화면을 유지한다. 저장된 backend
  job은 삭제/취소되지 않는다. `입력 중인 내용은 자동 저장되지 않습니다`라고 안내한다.
  초안 보존이 필요하면 별도 작은 Goal로 설계한다. 현재 form 내부를 G3.1에 끌어오지 않는다.

### 활동 확인과 여러 탭

- 고정 간격 `/me` polling은 금지한다. public health polling이나 job polling도 auth
  활동 신호로 사용하지 않는다. inactive tab을 heartbeat로 영구 로그인시키지 않는다.
- 첫 진입은 항상 확인한다. 다시 보이기/focus와 실제 pointer/keyboard 활동은 직전 확인이
  5분 이상 지난 경우에만 revalidation을 유발한다. hidden 탭은 activity check를 만들지 않는다.
- 명시적 retry와 수신한 logout 신호는 throttle을 우회한다. 동시 focus/activity 요청은
  하나의 in-flight 확인으로 합친다. listener는 unmount 시 해제한다.
- 성공 확인 전 이미 눌린 backend 작업을 취소했다고 주장하지 않는다. G4의 서버 정책이
  최종 권한 판단이며, G3.1은 다음 401 또는 활동 확인 때 UI를 잠근다.
- BroadcastChannel 메시지는 `session-changed`뿐이다. 사용자/쿠키를 보내지 않는다.
  수신자는 잠금·cache 폐기 후 `/me`로 확인한다. 지원하지 않는 환경은 focus 재확인으로
  동작한다. 로그인 시 매번 broadcast하여 탭 간 무한 재확인 loop를 만들지 않는다.

## 6. Deep module과 interface

하나의 browser Session module이 인증 상태, 요청 race, 이동, 오류 매핑, cache 수명을
숨긴다. route와 account UI에 각각 별도 `/me` query나 redirect 규칙을 복제하지 않는다.

```typescript
type SessionView =
  | { kind: "checking" }
  | { kind: "anonymous"; reason?: "required" | "expired" | "signed-out" | "login-error" }
  | { kind: "authenticated"; user: SafeUser }
  | { kind: "unavailable" }
  | { kind: "signing-out" }
  | { kind: "logout-unconfirmed" };

// Accepted external interface; internal adapters remain private.
useSession(): {
  view: SessionView;
  beginLogin(): void;
  retry(): Promise<void>;
  logout(): Promise<void>;
};
```

- `SafeUser`는 G3의 id/role/status/email/display_name/picture를 검증한 값이다.
  UI에는 필요한 profile만 전달하며 `status=active`, `role=user|master`를 확인한다.
- internal seam은 HTTP/이동/clock adapter다. production fetch와 deterministic test adapter를
  모두 사용한다. fake adapter는 tests 밖이나 build 결과에 포함하지 않는다.
- controller는 프레임워크 독립 규칙을, React provider는 구독·event·QueryClient 수명을,
  view 파일은 login/gate/account 표시를 맡는다. 한 symbol짜리 pass-through 파일은 만들지 않는다.
- 요청마다 generation/epoch를 캡처한다. logout/identity 변경 후 도착한 `/me` 200이나
  오래된 작업 401은 현재 상태를 되돌리거나 새 사용자를 로그아웃시키지 못한다.
- QueryClient는 auth controller와 분리하고 사용자 admission epoch마다 새로 만든다.
  퇴역 client는 query 취소·clear, 작업 subtree unmount로 폐기한다. 늦은 응답이 퇴역
  client에 도착해도 새 client/UI에는 합쳐지지 않는다. mutation 자동 replay는 금지한다.
- 정상 revalidation에서 같은 사용자가 유지되면 client/page를 교체하지 않는다.
- HTTP seam은 `credentials: same-origin`, `/me` no-store, AbortController와 10초 timeout을
  명시한다. G3.1은 비어 있는 `VITE_API_BASE` 또는 동일 origin root만 지원한다.
  cross-origin/임의 prefix 설정은 명시적 configuration 오류이며 auth를 우회하지 않는다.

## 7. 승인된 최소 backend 호환 확장

현재 start의 오류 응답 503 JSON을 그대로 browser navigation에 쓰면 앱 밖의 JSON 화면이
나온다. 새 config endpoint나 두 번의 OAuth start 호출 대신 아래 opt-in 확장을 적용한다.

| 요청 | 성공 | 안전한 실패 |
|---|---|---|
| 기존 `GET /api/auth/google/start` | 기존 307 유지 | 기존 503 JSON 유지 |
| `GET /api/auth/google/start?...&ui=1` | 동일 307 | 설정된 frontend의 `/login?auth_error=<bounded-code>`로 303 |

- `ui=1`만 opt-in이다. request Origin/Host/임의 redirect 파라미터를 목적지로 사용하지 않는다.
- 실패 redirect도 no-store/no-referrer, flow cookie 정리, raw query/provider 값 미노출을
  보장한다. 기존 Google callback과 `/me`/logout 계약, OAuth·Session 정책은 바꾸지 않는다.
- Google start를 fetch preflight 후 다시 호출하지 않는다. 클릭당 flow 시작은 한 번이다.
- 기존 callback의 root `auth_error`도 bootstrap에서 **route 기본 이동 전에** 소비한다.
  알 수 없는 코드는 일반 오류로 표시하고 URL에서 제거한다. code/state를 frontend에서
  처리하거나 로그에 남기지 않는다.
- `/me` 성공은 OAuth 설정 부재 여부를 알려주지 않는다. 현재 사용 가능한 login을 표시하는
  새 config endpoint는 이번에 추가하지 않는다. 설정 부재는 클릭 후 안전한 UI 오류가 된다.

## 8. 변경 경로 예산

예상 non-document **17개**, 상한 **20개**, migration **0개**. 승인은 구현을 뜻하지 않는다.

| # | 경로 | 역할 |
|---:|---|---|
| 1 | `frontend/src/auth/session.ts` (new) | Session view/controller, return path·error·epoch 규칙, internal adapter interface |
| 2 | `frontend/src/auth/AuthProvider.tsx` (new) | React 연결, 활동/탭 구독, replaceable QueryClient 수명 |
| 3 | `frontend/src/auth/AuthViews.tsx` (new) | login/check/error gate와 desktop/mobile account 표시 |
| 4 | `frontend/src/api/client.ts` | G3 auth 요청 adapter와 명시적 credentials/오류 처리; 기존 payload 보존 |
| 5 | `frontend/src/App.tsx` | `/login`, 작업 page gate, 기존 shell의 계정 위치 연결 |
| 6 | `frontend/src/main.tsx` | router/provider 구성과 QueryClient 소유권 이전 |
| 7 | `frontend/src/index.css` | auth/account 범위의 스타일·반응형·focus 추가 |
| 8 | `frontend/src/ui/copy.ts` | 한국어 인증 문구 |
| 9 | `frontend/package.json` | test-only Playwright dependency와 명령 |
| 10 | `frontend/package-lock.json` | 위 dependency lock |
| 11 | `frontend/playwright.config.ts` (new) | 고정 local server, 외부 요청 차단, 증거 안전 설정 |
| 12 | `frontend/tests/auth-session.spec.ts` (new) | module interface·HTTP adapter·race 계약 테스트 |
| 13 | `frontend/tests/auth-ux.spec.ts` (new) | browser 상태/이동/응답성/계정 전환 검증 |
| 14 | `frontend/tests/auth-fixtures.ts` (new) | test-only HTTP/작업 fixture, 외부 네트워크 차단 |
| 15 | `backend/app/api/auth.py` | opt-in start 오류 redirect만 |
| 16 | `backend/tests/test_auth_api.py` | 기존 JSON 계약 및 opt-in redirect 회귀 검증 |
| 17 | `.github/workflows/ci.yml` | 기존 verify job에 고정 browser 테스트 단계 추가 |

문서는 이 spec, initiative, current-work, testing, local-mock runbook, Issue별 portfolio와
index를 갱신한다. 현재 계획 확정 단계에서는 앞의 세 문서만 바꾼다.

21번째 경로, generation page 내부 수정, schema/Session 의미 변경, 새 auth provider,
product bypass, cloud, 외부 OAuth/이미지 호출이 필요하면 구현 전에 중단하고 재설계한다.
경로 여유 3개는 같은 slice의 발견된 test/integration에만 이유를 기록하고 사용한다.

## 9. 검증 계약과 완료 기준

### 자동 검사

Playwright는 **test-only**로 도입하고 UI library는 추가하지 않는다. 기존 verify CI에
module tests와 Chromium browser tests를 실행한다. 선택 버전은 구현 preflight에서
기존 Node/TS 환경과 설치·실행으로 검증하여 lockfile에 고정한다.

브라우저 fixture는 실제 frontend를 띄우고 `/api/auth/*`와 필요한 작업 HTTP만 가로챈다.
테스트 외의 로그인 우회 endpoint/환경 변수는 만들지 않는다. 외부 origin 요청은 차단하며
Google 이동 대신 같은 origin의 테스트 응답으로 UI 이동만 확인한다. 이 결과는 실로그인
통합 증거가 아니다. G3의 real Postgres/Redis 검증과 구분해 기록한다.

| 영역 | 필수 검증 |
|---|---|
| bootstrap | checking 중 작업 요청 0건, 200/401/503/timeout/잘못된 profile, StrictMode 중복 방지 |
| login | CTA 한 번에 start 한 번, same-origin 이동, 성공 후 `/me` 검증, 안전한 deep link/기본 경로 |
| error | G3 모든 bounded error code, unknown code, root callback 처리 순서, URL scrub, 새로고침/뒤로 가기 loop 없음 |
| return path | 외부/인코딩/제어문자/길이 공격 거절, mode/source_asset_id allowlist, TTL/저장소 차단 fallback |
| expiry | 기존 인증 후 401 잠금, 403/5xx 작업 오류와 구분, 미제출 입력 손실 안내, 자동 submit 없음 |
| activity | 가짜 clock으로 5분 전/경계 검증, idle 12시간 동안 자동 `/me` 0건, hidden 탭 0건, focus burst 단일 요청 |
| logout | 204, 중복 클릭, 403/503/timeout 결과 불명, HttpOnly cookie를 JS로 조작하지 않음 |
| races | 늦은 `/me` 200 after logout 거절, A의 늦은 작업 응답/401이 B에 영향 없음, cache 재사용 없음 |
| tabs | 성공 logout 신호 후 sibling 잠금/재확인, 비밀값 없는 메시지, unsupported fallback, loop 없음 |
| style/accessibility | 지정 4개 viewport, 기존 생성 화면 배치 보존, 메뉴 Escape/외부 클릭/focus, 모바일 logout, keyboard-only flow |
| backend | 기존 start 503 JSON 그대로, ui=1 303과 고정 목적지, cookie/헤더/오류값 안전성, 기존 G3 suite |
| regression | frontend typecheck/build, 기존 backend suite, mock generation golden path, git hygiene |

### 확정 검증 명령

구현 Goal에서 다음 명령을 실제 생성하고 확인한다. 지금 실행 가능한 테스트가 생겼다는
뜻은 아니다. browser tests는 새로운 전용 port를 사용하고 기존 dev server를 재사용하지 않는다.

```powershell
cd frontend
npm ci
npm run lint
npm run build
npm run test:auth
npx playwright install chromium
npm run test:auth:browser
cd ../backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_auth_api.py tests/test_auth_service.py tests/test_google_identity_adapter.py tests/test_oauth_flow_store.py -q
python -m pytest
cd ..
docker compose --env-file .env.example config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

- test:auth는 browser 없는 module/interface tests, test:auth:browser는 Chromium UI tests로
  분리한다. 둘 다 CI required verify에 포함하며 테스트 미발견은 실패다.
- mock generation은 fresh explicit Compose project에서 기존 smoke script로 검증하고
  그 project만 정리한다. 기본 개발 volume이나 실제 Google 설정을 사용하지 않는다.
- 실제 OAuth/Session core를 변경하지 않으므로 G3의 Postgres/Redis 2회 검증을 복제하지
  않는다. 그런 변경이 필요해지면 별도 승인·재검증 대상으로 중단한다.
- 외부 profile/로그인 데이터가 없는 fixture만 사용한다. 스크린샷은 identity/email 영역을
  mask하고 prompt fixture도 가린다. HAR, storageState, cookie dump, trace/video는 기본 off.
  원본 request/response/URL query 대신 상태별 count와 pass/fail을 기록한다.
- 새 test artifacts는 기존 untracked `.omo/evidence/` 아래로 보내고 전부 stage하지 않는다.

### F1–F4와 종료 조건

1. **F1 범위:** 17 예상/20 상한, migration 0, product bypass·소유권·cloud 변경 없음.
2. **F2 보안/상태:** safe return, no credential storage, no idle heartbeat, race/cache/tab 정책,
   backend 호환 확장과 generic 오류, frontend gate의 한계가 모두 테스트로 증명됨.
3. **F3 UX/runtime:** module/browser tests·네 viewport·키보드 검증·기존 generation 회귀 통과,
   실제 비교 화면과 검사 항목을 검토함. AI output 품질/실 Google 검증이라고 표현하지 않음.
4. **F4 문서:** 문제→관측→판단→구현→검증→결과→남은 위험, before/after와 정확한 counts,
   새 artifact 안전성, 다음 G4 interface와 portfolio/current-work 정합성 확인.

모두 APPROVE이며 실제 실행 결과가 있을 때만 `Mock Verified`로 올린다. 승인된 Goal은
작은 commit마다 focused test/diff/status/staged path 검사를 수행하고 push/Draft PR까지
완료한다. Goal은 Draft PR의 필수 CI 통과까지 수행하고 Draft를 유지한다. 이번 승인은
ready/merge/auto-merge 권한을 포함하지 않는다. UI 자동화 성공은 #99/G4/실 OAuth 검증을
대체하지 않는다.

## 10. 확정 Goal 분할

| Todo | 산출물 / 종료 검사 |
|---|---|
| 1 | main/Issue/branch/spec hash preflight, baseline 화면·CSS 기록, test-only runner와 실패 계약 |
| 2 | Session module + 실제 HTTP/test adapter, safe return/error/clock/epoch 계약 green |
| 3 | start opt-in redirect와 기존 backend 계약 회귀 green |
| 4 | bootstrap/login/gate 연결, 인증 전 작업 mount 없음, 기존 shell 유지 |
| 5 | account/logout/mobile, cache epoch와 tab/activity 검증 |
| 6 | bounded browser matrix·네 viewport·keyboard/race 증거 |
| 7 | 전체 regression, 격리 mock golden path, CI 연동 검증 |
| 8 | 포트폴리오/상태/다음 interface, F1–F4, push와 Draft PR delivery |

각 Todo는 현재 파일과 해당 테스트만 읽는다. 큰 `index.css`는 auth 추가 영역과 기존
`.creative-*`/관련 breakpoint만 읽고 전역 rewrite하지 않는다. 이전 인터뷰 전체, G3 내부 SQL, credits 설계는
입력에 넣지 않는다. frozen 실행 계획은 별도 `.omo/plans/`에 보존한다.

## 11. 승인된 선택 / 위험과 rollback

2026-09-03에 승인된 핵심 선택:

1. 기존 shell/CSS 유지, desktop footer + mobile topbar의 동일 계정 기능.
2. 작업 UI는 로그인 후 진입. credential 없는 mock 개발에서는 login 화면이 기본이며,
   자동 UI 검증은 test-only HTTP fixture로 진행한다. product bypass는 없다.
3. 전체 OAuth 이동·만료·logout 때 미제출 입력 초기화, 안전한 URL만 복귀 정보로 보존.
4. backend start에 `ui=1` 오류 redirect만 추가; 기존 API caller의 JSON 계약 유지.
5. timer heartbeat 없음, 활동 기반 재확인·cache epoch·로그아웃 결과 불명 처리.
6. test-only Playwright와 required verify의 browser 단계, 17-path 예산/0 migration.

rollback은 G3.1 UI/CI 변경과 선택적 `ui=1` 확장을 코드로 되돌린다. G3 기본 endpoint와
Session schema는 그대로 남는다. UI rollback이 Session 폐기를 의미하지 않는다.
제품 전체의 재로그인·초안 복원, login abuse rate limit, 실브라우저 Google 검증과 proxy
설정은 이 설계의 구현 결과처럼 기록하지 않는다. 계획 확정은 구현 시작이나 live 검증이 아니다.
