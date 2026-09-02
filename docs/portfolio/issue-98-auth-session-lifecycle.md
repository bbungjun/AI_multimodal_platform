# Issue #98 — Backend OAuth와 Session lifecycle

## 상태와 범위

- 날짜: 2026-09-03. 구현: `Implemented`, 검증: `Mock Verified`.
- [Issue #98](https://github.com/bbungjun/AI_multimodal_platform/issues/98),
  [확정 spec](../initiatives/g3-auth-session-lifecycle-spec.md).
- 코드/테스트 checkpoint: `ec42d61`; 기반 `main`: `58f405b`.
- non-document 17개, migration 0개. Google OAuth, browser UX, cloud, AI provider
  실제 호출은 하지 않았다. CI와 PR delivery는 아래에 별도 기록한다.

## 배경과 문제

G2는 User와 Session을 저장할 수 있었지만, 요청에서 사용자를 식별하거나 안전하게
세션을 발급·만료·폐기하는 동작은 없었다. 이후 개인 작업 소유권과 사용량을 넣으려면
각 API에 OAuth 구현을 복제하지 않고 신뢰할 수 있는 사용자 경계를 제공해야 했다.
목표는 로그인 버튼 하나가 아니라 인증 실패, 재시도, 동시 로그인과 운영 장애에도
정책이 유지되는 backend 모듈이다. 기존 생성 흐름은 이 단계에서 변경하지 않는다.

## 관측과 원인 분석

1. 초기 collection-safe 계약 테스트 32개가 미구현 기능 때문에 실패했다. import
   실패를 완료 증거로 사용하지 않고 순차 구현으로 계약을 닫았다.
2. 첫 격리 검증에서 Postgres 테스트는 통과했지만 Redis 재시작 후 복구 검증이
   실패했다. Docker가 동적 host port를 바꾸는데 최초 주소를 재사용한 것이 원인이다.
   재시작 후 포트를 다시 조회하도록 고쳤고 회귀 검사를 추가했다. 실패한 진단 실행은
   성공 횟수에 넣지 않았으며 임시 리소스는 모두 정리했다.
3. 보안 검토에서 비정상 숫자 timestamp와 깊게 중첩된 JSON, cleanup 실패에 가려지는
   최초 검증 오류를 재현하는 6개 red test를 추가했다. 유한 timestamp만 허용하고
   파싱 오류를 안전한 실패로 바꾸며 최초 실패와 cleanup 실패를 함께 보존했다.
4. 전체 Windows 테스트의 유일한 실패는 G1/G2부터 기록된
   `test_release_script_guards_plan_scope_and_uses_terraform_rollback`의 Bash
   경로 변환 문제다. 인증 회귀가 아니며 테스트를 삭제·skip하거나 성공으로 표현하지
   않았다. Linux required CI에서 전체 suite를 다시 확인한다.
5. TTL만으로 Redis 스냅샷/AOF의 민감정보 잔존을 막을 수 없으므로 Compose에서 두 저장
   방식을 명시적으로 껐다. red/green 계약 테스트와 실제 Redis 설정 조회를 추가했다.
   같은 Redis의 broker도 비영속이 되는 trade-off를 문서화하고 golden path를 재실행했다.

## 해결 방법과 판단 근거

- `AuthService`의 start/complete/authenticate/logout 네 연산에 정책을 모았다.
  Google adapter와 flow store는 내부 seam이다. 운영 설정으로 fake login을 켤 수 없다.
- Authorization Code + PKCE S256, state/nonce 검증, 실제 서명 검증 경계를 구현했다.
  자동 테스트는 ephemeral 서명 키와 MockTransport만 사용한다. 요구 scope는
  `openid email profile`, online access뿐이다.
- transient Redis flow는 digest key, state digest, nonce, verifier, 안전한 return path와
  생성시각만 보관한다. TTL 600초와 GETDEL로 실패한 callback도 재사용하지 못한다.
  provider token과 raw Session secret은 SQL·로그·증거에 남기지 않는다.
- Google subject로만 upsert하고 profile만 갱신한다. 같은 이메일로 계정을 합치지
  않으며 role/status/signup/suspension 값은 provider가 변경할 수 없다.
- User row lock으로 세션 발급·확인·로그아웃을 직렬화한다. 5개 활성 세션에서 로그인하면
  `(created_at, id)` 기준 가장 오래된 세션을 폐기하고 새 세션을 같은 transaction에 넣는다.
  주입한 SQL 실패로 profile 갱신과 eviction이 함께 rollback되는 것도 확인했다.
- Session은 256-bit random secret의 SHA-256 digest만 저장한다. 절대 7일·비활동 12시간
  만료를 매 요청 평가하고, 5분 이상 지난 활동시각만 조건부로 갱신한다.
- cookie는 host-only, HttpOnly, Lax, Secure 기본값이다. 삭제에도 같은 속성을 쓴다.
  unsafe method에는 exact Origin을 요구한다. callback query는 Uvicorn/httpx에서 지우고
  no-store/no-referrer 응답으로 깨끗한 로컬 경로에 redirect한다.

JWT 대신 서버 상태를 선택한 이유는 즉시 폐기, 정지 상태, 세션 수와 비활동 만료를
한 곳에서 결정하기 위해서다. Redis를 쓰면 login 가용성이 의존성 하나에 더 묶인다.
동일 User의 요청은 touch가 없어도 직렬화하므로 대규모 트래픽 전 측정이 필요하다.
5분 touch는 DB 쓰기를 줄이지만 실제 마지막 활동과 최대 5분 미만 차이가 난다.

## 검증과 수치

재현 명령은 repo root 기준이며 backend 명령만 해당 디렉터리에서 실행한다.

```powershell
$env:AI_PROVIDER = "mock"
python scripts/verify_auth_sessions.py --env-file .env.example
python scripts/verify_auth_sessions.py --env-file .env.example
python scripts/verify_local.py --skip-backend
docker compose --env-file .env.example config --quiet
git diff --check
```

| 항목 | 첫 번째 최종 실행 | 두 번째 최종 실행 |
|---|---:|---:|
| 프로젝트 | `auth-verify-d44013ba240b` | `auth-verify-d462709efd3b` |
| code/test checkpoint | `ec42d61` | `ec42d61` |
| schema | `0002_user_session_persistence` | 동일 |
| 동시 로그인 / 남은 활성 Session | 12 / 5 | 12 / 5 |
| 동시 활동 요청 / 실제 갱신 | 20 / 1 | 20 / 1 |
| 동시 첫 가입 / 생성 User | 8 / 1 | 8 / 1 |
| flow 동시 consume / 성공 | 12 / 1 | 12 / 1 |
| replay 거절 (경쟁 탈락 11 + 재시도 1) | 12 | 12 |
| 주입 시각 600초의 flow 만료 거절 | 1 | 1 |
| latency 측정 성공 요청 | 50 | 50 |
| 인증 p95 (ms) | 8.014 | 11.033 |
| Redis 장애·복구 / cleanup | PASS / PASS | PASS / PASS |

Redis TTL은 실제 저장소에서 590–600초를 확인하고, 정확한 만료 경계는 주입한 시각으로
검증했다. 기본 latency 표본은 성공 50·실패 0이며, 별도 negative 시나리오에서 unknown,
evicted, logged-out, inactive, absolute-expired, suspended Session의 같은 공개 오류를
확인했다. 0.1초 provider timeout 설정에서는 느린 fake 응답을 총 deadline으로 중단하고
1초 미만에 안전한 오류로 반환했다. 이 수치는 로컬 관측값이지 운영 SLO나 개선율이 아니다.

- Focused: `python -m pytest tests/test_auth_service.py tests/test_auth_api.py
  tests/test_google_identity_adapter.py tests/test_oauth_flow_store.py
  tests/test_verify_auth_sessions_script.py -q` — 60 passed, guarded integration
  3 skipped. 위 격리 verifier에서는 그 3개도 실제 Postgres/Redis로 실행한다.
- 전체 Windows backend: `python -m pytest -q` — 456 passed, guarded 3 skipped,
  기존 Bash 경로 문제 1 failed, Starlette TestClient deprecation warning 1개.
- frontend `npm run lint`, `npm run build`, Compose config,
  `verify_local.py --skip-backend`, diff hygiene: PASS. frontend 변경은 없다.
- generation golden path: `auth-verify-golden0298`, `ec42d61`에서 PASS.
  Redis persistence 비활성화를 포함한 최종 구현이다. backend를 loopback의 별도
  포트로 노출한 local Compose override를 사용했다. 실행은
  `python scripts/smoke_mock_golden_path.py --compose --env-file .env.example
  --base-url http://127.0.0.1:18098 --timeout-sec 120`.
  health → prompt enhancement → generation → metadata → PNG bytes/range → 삭제를
  통과했다. OAuth 설정은 비어 있었다. exact project에만 `down --volumes`를 실행했다.
- 두 최종 receipt는 `.omo/evidence/auth/<project>.json`, 순차 Todo/F 검토는
  `.omo/evidence/issue-98/`에 로컬 보존한다. `.omo`는 커밋하지 않는다. 위 표와 재현
  명령이 공유 가능한 bounded evidence이며 raw 로그·이메일·credential은 포함하지 않는다.

## 결과와 직무 관점

이제 후속 모듈은 인증된 User를 하나의 dependency로 받을 수 있고, 로그인 과정은
서비스/저장소/HTTP 경계를 통해 검증된다. 다만 현재 이미지 생성 API가 인증·소유권으로
보호된다는 뜻은 아니다. 그 부분은 G4다.

- AI Full Stack: backend와 이후 browser가 공유할 HTTP·cookie 계약을 완결했다.
- FDE: 외부 identity를 교체 가능한 경계에 격리하고 실제 저장소 장애·복구까지 검증했다.
- AX Consultant: 보안 정책을 수용 기준과 숫자로 연결하고 live 도입의 차단 조건을 남겼다.
- AI Platform Engineer: concurrency invariant, write amplification, disposable runtime,
  redacted evidence와 strict CI delivery를 운영 경계로 다뤘다.

## Rollback, 남은 위험과 다음 단계

G3는 migration이 없으므로 코드 revert에 schema rollback은 필요 없다. Google 설정을
비우면 신규 login만 차단되며 기존 Session은 여전히 유효하다. Redis/Google 장애 후에는
새 로그인부터 다시 시작한다. 소비·만료된 flow를 복원하지 않는다.

긴급 Session 일괄 폐기는 [#99](https://github.com/bbungjun/AI_multimodal_platform/issues/99)의
별도 승인 대상이며 구현하지 않았다. 이 기능과 reverse-proxy/LB query redaction,
실제 Google browser 검증 전에는 live 운영 준비 완료를 주장하지 않는다. Compose Redis의
RDB/AOF 비활성화는 실제 확인했지만 외부 배포의 persistence/backup·접근 통제 검토는 남아 있다.
같은 Redis의 broker도 비영속이므로 재시작 후 작업 복구를 자동 보장하지 않는다.
login rate limiting, certificate caching, Session retention 정리와 대규모 동일 User 부하는
추가 운영 검토 대상이다.

G3.1은 `/me`, logout, redirect와 cookie 계약만 인수한다. G4는 `require_user`와
`AuthenticatedUser`를 인수한다. frontend UX, ownership, Plan/Credit/Usage, Master mutation,
cloud 배포와 실제 Google·AI provider 호출은 이 작업에 포함되지 않았다.

## Delivery

작은 순차 commit으로 Todo 1–8을 수행했다. F1–F4 검토와 Draft PR의 strict required
checks (`verify`, backend/frontend Scan and SBOM)를 확인한 뒤 ready 및 squash
auto-merge로 전달한다. CI/merge 결과는 완료 시 PR 링크와 함께 기록한다.
