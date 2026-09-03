# Issue #103 — 인증된 mock 검증 기반

- 상태: **Implemented / Mock Verified**. G4 전체 소유권 보호 또는 Live Verified가 아니다.
- [Issue #103](https://github.com/bbungjun/AI_multimodal_platform/issues/103)
- Branch: `codex/issue-103-authenticated-mock-harness`, base `100f5e7`.
- 검증된 harness revision: `471b76ee7f3e900ab112e39df297bd1797b34a47`.
- [Accepted spec](../initiatives/g4-ownership-access-control-spec.md), [G4 설계 판단](g4-ownership-design.md).
- Ready [PR #104](https://github.com/bbungjun/AI_multimodal_platform/pull/104)에서
  최종 head 필수 CI와 squash 병합 상태/결과 SHA를 확인한다.

## 배경과 문제

기존 생성·retry·I2V duplicate smoke는 익명 요청과 기본 Compose project에 의존했다.
소유권 보호를 추가하면 정상 사용자 요청을 재현하지 못하고, 여러 실제 Google 계정이나
유료 Redis 없이 인증 경계를 검증할 방법이 필요했다. Cookie를 단순히 추가하면
redirect/proxy/외부 asset URL과 raw error body를 통해 민감정보가 유출될 수도 있었다.

## 관측과 원인 분석

기존 golden client는 인증 헤더 없이 redirect를 따랐고, duplicate race는 별도 urlopen을
사용했다. retry는 SPA HTML200을 UX 검증으로 취급했다. Manual workflow는 실패 시
raw Compose 로그를 출력하고 기본 project에 down -v를 실행했다.

첫 실제 실행은 안전한 환경변수 allowlist가 Windows ProgramFiles까지 제거해 Compose
플러그인을 찾지 못한 탓에 start 단계에서 중단됐다. 아직 리소스는 없었고 cleanup은
성공했다. 시스템 경로만 허용해 해결했으며 credential/proxy 환경은 계속 차단했다.

전체 Windows pytest의 유일한 실패는 Bash에 Windows 절대경로가 전달되는 기존
`test_release_script_guards_plan_scope_and_uses_terraform_rollback`였다. `git archive 100f5e7`
사본에서 해당 테스트를 독립 재실행해 동일한 exit127을 확인했다. Cloud script를 고치거나
검증을 숨기지 않았다. 첫 Linux 테스트용 로컬 이미지에는 pytest가 없었으므로 깨끗한
python:3.11-slim 컨테이너에 backend[dev]를 설치하고 repo를 read-only로 마운트해 검증했다.

## 해결과 판단 근거

codebase-design의 작은 interface 원칙으로 복잡한 안전 로직을 test-only 경계에 모았다.

- `MemoryIdentity`: 유효/만료/폐기/정지/Synthetic fixture용 raw Session은 메모리에만 생성.
- `ScopedClient`: 정확한 loopback origin, Cookie와 trusted Origin, 무조건 redirect/proxy 차단,
  traversal/외부 URL/auth header override 거절. HTTP 상태와 body는 assertion용 메모리에만 유지.
- `OwnedRuntime`: 매번 새 project, local daemon 검증, 전체 실제 port binding 검사,
  이중 소유 라벨 확인, hash-only stdin seeding, bounded timeout과 finally cleanup.
- `verify_ownership.py`: 실제 G3 /me와 logout을 검증하고 세 기존 시나리오에 인증 client 주입.
  생성·Range·poll·delete 및 두 동시 요청도 숨은 익명 client를 만들지 않는다.

프로덕션 인증/소유권 코드는 변경하지 않았다. 정확히13개 non-document 경로와 migration0개다.
G1/G2 migrate를 새 DB에 적용하고 head/empty-table을 확인한다. Redis /data는 tmpfs라
익명 볼륨이 필요 없다. 요청/오류/cleanup 결과는 허용 필드 receipt만 남긴다.
기존 CLI의 --base-url/--compose/keep-job 옵션은 제거·거절하고 canonical runner로 위임한다.
Frontend static HTML 확인은 제외했지만 기존 auth/browser 테스트는 모두 유지했다.

대안인 실제 Google 계정 생성, product mock-login endpoint, 기본 개발 DB fixture 주입은
비용·인증 우회·데이터 손상 위험 때문에 선택하지 않았다. 수동 workflow는 같은 runner를
2회 실행하고 raw logs/default cleanup 없이 20분 timeout을 둔다.

## 검증

환경: local Docker Desktop Linux, Compose5.0.2, Python3.11, AI_PROVIDER=mock.
실제 Google/OAuth/provider/cloud 요청은0회다. 최종 커밋 상태에서 다음을 실행했다.

```powershell
python scripts/verify_ownership.py --env-file .env.example --cycles 2
```

| Project | 인증 검사 | 시나리오 | 시간 | Cleanup / 결과 |
|---|---:|---:|---:|---|
| ownership-verify-6a554904eeb2 | 12 | 3 | 32.81s | true / PASS |
| ownership-verify-1d16da8309e6 | 12 | 3 | 32.47s | true / PASS |

두 receipt의 code revision은 위 `471b76e`, schema revision은
`0002_user_session_persistence`다. 각 cycle은 A/B/Master /me200 및 id/role의 메모리 비교,
익명·idle/absolute 만료·revoked·suspended·Synthetic /me401, untrusted logout403,
trusted logout204 이후 /me401을 검증한다. Golden, 실패 retry lineage,
I2V one201/one409와 최종 완료/정리가 각각 통과했다. 세 종류 owned resource 잔존0개.

추가 회귀:

- `python -m pytest` focused6개 파일: **106 PASS**.
- Linux 전체 backend `python -m pytest -q -p no:cacheprovider`: **542 PASS / 기존 conditional SKIP3**.
- Windows 전체 backend: **541 PASS / SKIP3 / 기존 Bash 경로 FAIL1**, baseline 동일 실패.
- Frontend `npm run lint`, `npm run build`: PASS.
- Frontend `npm run test:auth`: **48 PASS**; `npm run test:auth:browser`: **34 PASS**.
- `docker compose --env-file .env.example config --quiet`, diff/check/status/staged-path audit: PASS.
- Migration0 / allowlist13; 사용자 변경과 기존 login preview project 보존.

Linux 재현은 provider 자격증명·DB URL을 전달하지 않는 일회성 컨테이너에서 수행한다.
repo-relative source를 read-only로 /repo에 마운트하고 /tmp/backend에 pyproject와 app만
복사해 `python -m pip install "/tmp/backend[dev]"` 후 /repo/backend에서 위 pytest를 실행한다.
기존3개 integration skip은 새 skip이 아니며, 본 작업의 실제 인증 proof는 위 독립
Docker cycle에서 실행했다. 원본 로그/식별자는 보존하지 않고 bounded receipt만 기록했다.

## 결과와 영향

로그인 UI에만 의존하지 않고 서버가 검증하는 여러 Session으로 생성 흐름을 재현할 수 있다.
여러 이메일이나 유료 관리형 Redis가 필요 없고, 개발 DB/preview를 건드리지 않는
재현 가능한 실행·정리 경계를 확보했다. 테스트는 baseline467에서542 PASS로 확장됐다.
이 수치는 테스트 수의 변화이며, 사용자 데이터 격리율이나 성능 향상 KPI가 아니다.

## 운영·롤백과 남은 위험

- 정상/처리 가능한 실패는 owned cleanup을 검증한다. 강제 kill·Docker 중단·cleanup 재중단은
  finally를 막을 수 있다. 정확한 receipt project/라벨/local context 검증 후
  [runbook 복구 절차](../runbooks/local-mock.md#failure-and-owned-project-recovery)를 따른다.
  기본 project, preview volume, broad Docker prune은 금지한다. Build cache/image는 남을 수 있다.
- Rollback은 검토된 harness/workflow/adapter revert다. DB schema downgrade나 기존 데이터 삭제는 없다.
- G4.1은 인증 검증 기반일 뿐 generation/file/ops ownership은 아직 강제하지 않는다.
  G4.2는 owner persistence/admission/reference invariant, G4.3는 read/file/ops 접근 제어다.
- G4.2는 client 주입 계약과 fixture를 재사용하고 migration 적용 시 두 expected-head 상수를 갱신한다.
- 실제 OAuth/browser/proxy 운영과 긴급 Session 폐기 #99, 클라우드/공개 배포는 별도 gate다.
  Frontend browser 검증은 mock 계약 테스트이지 실제 Google 로그인 검증이 아니다.
