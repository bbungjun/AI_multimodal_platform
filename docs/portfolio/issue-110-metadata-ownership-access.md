# Issue110 — G4.3A Metadata Ownership Access

- Status: **Mock Verified — Todo1–8/F1–F4 complete; [PR #111](https://github.com/bbungjun/AI_multimodal_platform/pull/111) actually squash MERGED cd654e5** (2026-09-03).
- Final head5738c0d: verify and both Scan/SBOM SUCCESS. [Delivery evidence](https://github.com/bbungjun/AI_multimodal_platform/issues/110#issuecomment-5524251068). Historical pending-delivery notes below describe earlier checkpoints, superseded by this result.
- [Issue110](https://github.com/bbungjun/AI_multimodal_platform/issues/110), branch
  `codex/issue-110-metadata-ownership-access`.
- Main base `c84394a8e2b16748d1b4b4c877f9f491624f7a1b` (G4.2B PR108 actual merge).
- [Accepted policy/split](../initiatives/g4-ownership-access-control-spec.md),
  [canonical initiative](../initiatives/auth-credits-master-console.md),
  [parent design #109](issue-109-ownership-access-design.md).
- Frozen local plan: `.omo/plans/issue-110-g4-3a-metadata-ownership-access-goal.md`.
  SHA-256 `e809a70b8ae7110e8585e357c1b769270d6c19b0251a0bfbc30883a25c426017`.
  Local/untracked: transfer exact bytes between machines; do not stage .omo wholesale.

## 배경과 문제

Latest actual runtime evidence at `acb44a909e2b955275a995c9db935b7df57eb180`:

| Independent local mock cycle | Duration | Per-cycle result |
|---|---:|---|
| 1 |337.73s|8 metadata groups /348 checks /2 observed deletion races, PASS |
| 2 |338.12s|8 metadata groups /348 checks /2 observed deletion races, PASS |

Canonical `python scripts/verify_ownership.py --env-file .env.example --cycles 2`
exit0. Both preserve auth12/admission111/smoke3/worker20/pipeline4/race3/expiry1.
Real PostgreSQL content-query measurement is5 SELECTs at page1/20/100. Both cleanup
receipts true and separate exact-label container/volume/network inventory0;4 existing
preview containers remain running. Combined675.85s, no deadline/quota relaxation.
Full regression at identical code tree: Linux tracked-only Python3.11 archive
**928 PASS/3 existing guarded skips/4.76s**; Windows **927 PASS/1 known FAIL/3 skips/10.96s**.
Untouched `c84394a` archive reproduced exactly
`test_supply_chain_release.py::test_release_script_guards_plan_scope_and_uses_terraform_rollback`
failure (0.39s, Bash native127 interpreting a Windows absolute path). This test passes
in Linux; no new skip/xfail or cloud script modification. Frontend lint/build PASS,
Session48 PASS/0.927s and Chromium34 PASS/24.9s. Final-head CI/merge remain pending.

Execution checkpoint:1588911 Ownership Interface,6f9a1a5 metadata routes,
671599e response cache,2042f8c guarded proof. O102/M248/H201/S94 tests pass with
existing guarded-auth skips only. First actual runtime stopped after L/D/P at109.75s:
the Master corruption-list probe incorrectly assumed all instead of default mine.
acb44a9 fixes only that probe's explicit scope; focused265 PASS. Cleanup succeeded;
at that checkpoint both complete cycles still needed rerunning. The two successful
reruns above supersede that intermediate result; delivery is tracked by PR #111.

The preparation notes below describe the earlier snapshot, not final verification.

G4.2B까지 owner persistence/worker 참조 검증은 끝났지만 목록·상세·삭제는 아직 서버의
사용자별 접근 제어를 완료하지 못했다. A는 metadata 읽기와 삭제, B는 파일/Range와
Master 운영 endpoint로 분리하여 각 Goal을 작은 실행 context에서 닫는다.

## 관측과 원인 분석

사용자는 #109 A/B 분할과 A 실행 준비를 승인했다. 준비 중 기존
`test_ownership_persistence.py::test_access_unknown_intent_fails_before_query`가
`read`를 미지원 intent로 검사하는 것을 발견했다. 새 read 지원과 충돌하므로 해당
테스트를 삭제하지 않고 정말 미지원인 값으로 바꾸도록 이 파일을 allowlist에 추가했다.
최초 A15 후보는 A16으로 확정되었고 B16 후보와 합집합23/공통9, per-Goal20 상한 유지다.
기존 파일의 다른 persistence/schema 테스트는 변경하지 않는다.

G4.2B의 A Session 만료 증거가 이후 B client로 A Job을 poll하는 부분도 확인했다.
읽기 보호를 도입하면404가 정상이므로 해당 관찰만 Master read로 바꾸도록 계획했다.
이 변경은 만료된 Session 갱신이나 인증 bypass가 아니다.

## 해결 방향과 판단 근거

기존 Ownership Module Interface에 SQL 목록 scope, read intent, 일괄 참조 검증을
추가한다. Master 읽기 예외를 owner-only mutate/use와 분리한다. 목록 SQL pagination과
최대5 content SELECT 기준, 동일404, 삭제 Asset→Job lock 순서/참조 검사, JSON no-store
실패 응답까지 명시했다. 실행 계획은 Todo1–8/F1–F4와 작은 commit 단위를 고정했다.

실제 HTTP/PostgreSQL 검증은8개 named access group과 delete/create·delete/retry 경합2종을
기존2cycle에 더한다. 실제 lock 대기를 관측하고 DB 최종 일관성을 확인한다. fake 테스트
결과와 실제 runtime 증거를 구별하며 기존 auth12/admission111/smoke3/worker20/pipeline4/
race3/expiry1 proof를 보존한다. 계획된 결과이며 아직 이 검증을 실행하지 않았다.

새 ACL/store/schema나 범용 복구 시스템은 제외했다. 파일 삭제 후 DB commit 실패의
비원자성은 남는 위험이며, A merge만으로 공개 multi-user 배포는 불가능하다.
이 준비는 문서만 변경하므로 runtime rollback이 없다. 구현 rollback은 private service
중단/상태 확인 후 기존 코드로 복귀하는 절차를 실행 기록에 남기며 보안 bypass는 만들지 않는다.

## 실제 준비 검증

- `git fetch origin main`, main fast-forward 확인 후 Issue110 branch 생성.
  #109 설계 commit `fd441f1`은 `a39d8cf`로 cherry-pick하여 보존했다.
- 기존 tracked/staged 변경0, untracked `.omo/`는 보존했다.
- mock focused baseline: **385 PASS /5.11s**. 아래 명령은 root 기준이다.

```powershell
$env:AI_PROVIDER = 'mock'
Push-Location backend
python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py tests/test_asset_api.py tests/test_storage.py tests/test_ops_api.py tests/test_ops_runtime.py tests/test_ownership_persistence.py tests/test_ownership_execution.py tests/test_verify_ownership_script.py tests/test_mock_auth_support.py -q
$g43PrepExit = $LASTEXITCODE
Pop-Location
if ($g43PrepExit) { throw 'Focused baseline failed' }
git diff --check
if ($LASTEXITCODE) { throw 'Diff failed' }
git status --short --branch
if ($LASTEXITCODE) { throw 'Status failed' }
git diff --cached --name-only
if ($LASTEXITCODE) { throw 'Staged check failed' }
```

- GitHub read-only protection query: strict=true, `verify`, `Scan and SBOM (backend)`,
  `Scan and SBOM (frontend)` 모두 필수임을 확인했다. 이 결과는 향후 PR CI 성공이 아니다.
- 최종 문서 수정 후 B0 재실행: **385 PASS /4.43s**. spec/Goal16개 경로 일치,
  신규 예정 테스트2개/기존 검증 명령의 경로 존재, Todo8/F4 개수, 문서/SHA 일치,
  상대 문서 링크 target, diff/status/staged 검사를 통과했다. 신규 O/OI/OM 테스트는
  실행 중 추가될 예정이며 준비 단계에는 없다. 기존 frontend scripts와 CLI도 확인했다.

## 결과와 영향

A16개 코드 경로/migration0, Todo1–8/F1–F4, mock-only 2cycle, 전체 회귀와 Ready PR의
최종-head CI/실제 squash merge까지 실행 계획을 준비했다. SHA 불일치, 목록 밖 코드,
추가 migration/정책/운영 환경 변경이 필요하면 구현 전에 멈추도록 했다.
준비 단계에서는 Goal/제품/Docker 작업을 하지 않았다. 이후 명시적 실행 요청으로 위
metadata 구현과 격리 mock 검증을 완료했다. 개발/preview DB와 실제 OAuth/provider/cloud는 변경하지 않았다.

## 남은 위험과 다음 단계

- A 로컬 구현·검증은 완료했으며 Ready PR의 최종-head 필수 CI와 실제 merge를 확인해야 한다.
- G4.3B는 A 실제 병합 후 파일/Range/Master ops/최종 전체 검증을 설계·실행한다.
- 기존 work360s/cleanup90s 예산 안에 추가 proof가 들어가야 한다. 초과하면 재설계한다.
- no-store의 unhandled500 처리, FK lock 순서와 concurrent delete는 실제 검증이 필요하다.
- #99 긴급 폐기, 실제 OAuth/proxy/live gate, machine metrics 인증은 별도다.
- 실제 MERGED 후 PR/Issue에 merge SHA를 기록하고 #109는 B 완료까지 열어 둔다.

## 구현 결과, 검증 명령과 운영 인계

조회는 SQL owner scope를 먼저 적용하고 UUID tie-break pagination을 사용한다.
Master도 기본 mine이며 all은 명시적 요청만 허용한다. known reference/Asset graph를
일괄 검증하고, 타인/없는 대상은 동일404다. Master의 read 예외가 delete/retry/use로
번지지 않는다. 안전한 삭제 lock 순서와 no-store500/스트리밍 보존을 함께 검증했다.
초기 Linux782에서928 PASS로146개가 늘었으며 기존 테스트는 삭제/skip하지 않았다.

실행 명령: backend에서 mock `python -m pytest -q` (Windows 결과는 위 예외 포함),
Linux는 HEAD tracked-only `git archive`를 생성해 `python:3.11-slim` 컨테이너에
read-only archive만 mount하고 `python -m pip install ".[dev]" && python -m pytest -q`를
수행했다. .env/credential/workspace mount0, 종료 후 해당 컨테이너0. 새 검증 명령은
[testing](../testing.md)의 G4.3A 절, runtime은
`python scripts/verify_ownership.py --env-file .env.example --cycles 2`다.
frontend `npm run lint`, `npm run build`, `npm run test:auth`, `npm run test:auth:browser`
모두 통과했다. `docker compose --env-file .env.example config --quiet`와 diff/staged/
allowlist/hash 검사도 통과. Native exit를 확인했으며 실패 run은 성공에 포함하지 않았다.

Rollback: 새 schema가 없으므로 downgrade하지 않는다. private 환경에서 backend 진입을
중지한 후 알려진 이전 이미지/code로 복귀하고 mock readiness와 기준 검증을 실행한다.
이전 코드에는 metadata 보호가 없으므로 외부 접근을 재개하면 안 된다. 이미 삭제된 파일은
DB rollback만으로 복원되지 않는다. provider/UI/cloud rollback을 수행한 것으로 주장하지 않는다.

운영 한계: 직접 DB 변조를 read snapshot과 원자적으로 막는 RLS는 아니다. 잘못 연결된
row가 있는 page는 전체404로 거절한다. 이미 전송된 bytes나 파일 삭제/DB commit의
비원자성을 해결하지 않았다. File/Range/ops 보호와 machine metrics 인증/실제 Google/
긴급 폐기 gate는 남아 있다. 이는 metadata Mock Verified이며 전체 G4/Live Verified가 아니다.
