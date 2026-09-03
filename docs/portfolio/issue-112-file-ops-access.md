# Issue112 — G4.3B File/Range and Master Ops Access

- **Implemented; v2 complete local mock proof and full regression**,2026-09-03.
  Original combined failure is preserved; v2 Todo1–6 now complete. Delivery requires
  Ready PR, final-head CI and actual merge; final evidence is linked from Issue112.
- [Issue112](https://github.com/bbungjun/AI_multimodal_platform/issues/112), branch
  `codex/issue-112-file-ops-access`, parent [Issue109](https://github.com/bbungjun/AI_multimodal_platform/issues/109).
- Delivery: [Ready PR113](https://github.com/bbungjun/AI_multimodal_platform/pull/113).
  Final-head CI links, actual merge SHA and parent closure are recorded in Issue112
  after confirmation, not inferred from auto-merge being enabled.
- [Spec/B contract](../initiatives/g4-ownership-access-control-spec.md),
  [canonical initiative](../initiatives/auth-credits-master-console.md).
- Main base `cd654e5003e70d78cd7390cc24e98f322a3383fe`: [PR111](https://github.com/bbungjun/AI_multimodal_platform/pull/111)
  actual squash merge. Its final head5738c0d verify/both Scan-SBOM all SUCCESS.
- Local/untracked frozen Goal `.omo/plans/issue-112-g4-3b-file-ops-access-goal.md`;
  SHA-256 `005908f870551f84d952a11e18f7348e11811337ac1010adf422fdd2ae65a29f`.
  Transfer exact bytes between machines; .omo whole staging forbidden.

## 배경과 문제

### v2 실행 진행 (최초 실패 기록 보존)

사용자 frozen-v2 실행 요청으로 재개했다. Todo1 7e9efa1 기준검증, Todo2 52c1cc6
고정 phase/error 계측, Todo3 48562bc suite/aggregate 구현을 완료했다. 제품 코드는
변경하지 않고 기존 verification4개 경로만 수정했다(허용5개 이내, 누적16/migration0).

Todo4 재검증: H290 PASS/1.39s, F231 PASS/5.23s, M248 PASS/4.26s,
S94 PASS/기존2 skip/1.77s. 제품/기존 migration/frontend/CI/Compose diff0 확인.
실제 v2 Docker proof는 아직 실행 전이며 아래는 검증 배치와 코드 검토 결과다.

| Matrix | Retained verification | Evidence level before R-v2 |
|---|---|---|
| A1–A3/A23 | auth12, admission111, existing Origin/owner/session tests | unit verified; fresh runtime pending |
| A4–A9/A12–A13 | metadata L/D/P/X/R/C/S/Q, >=348 checks; ownership A golden/retry/duplicate | unit verified; fresh runtime pending |
| A10–A11 | worker20/pipeline4/HTTP races3/expiry1; observed delete/create and delete/retry races2 | call paths preserved; fresh runtime pending |
| A14–A20 | unchanged product F231; file-ops F/O/V and each actor E ten stages | unit verified; real bytes/logout/ops pending |
| A21–A22 | existing schema head0003 and guarded schema verifier2 | schema code unchanged; fresh runtime pending |
| A24 | guards/canaries/phase timing/aggregate fail-closed, exact cleanup labels | H290 verified; actual cleanup pending |

Coordinator review: ownership runs all three original A smokes then execution proof;
file-ops runs all original selected A/B smokes and both complete pipeline paths.
Actor E runs sequentially with deadline-clamped clients to avoid a failed actor
leaving a background executor during cleanup. No assertion or stage is removed.
All requires four distinct projects and one SHA; single-suite/one-cycle success
returns complete=false. Per-cycle clocks and per-suite/command limits are separate.
Earlier H failed on the obsolete combined-scenario assertion; its replacement
asserts both explicit suite contracts. No new skip/xfail or weakened product tests.

### v2 Todo5 actual isolated runtime

`python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 2`
passed exit0 at immutable `c05b815a29077b70d21da13cc8b592290455aebe`.
One aggregate: passed=true, complete=true, verified_cycles4,998.187s/1800s.

| Suite/cycle | Work seconds | Cleanup seconds | Total seconds | Actual proof |
|---|---:|---:|---:|---|
| ownership1 | 327.329 | 6.031 | 333.360 | auth12/admission111/smokes3/worker20/pipeline4/race3/expiry1/access8·348/delete-race2 |
| ownership2 | 322.500 | 6.359 | 328.859 | same complete proof |
| file-ops1 | 161.078 | 6.422 | 167.500 | auth12/FOVE4/checks310/A and B each10 stages |
| file-ops2 | 161.360 | 6.218 | 167.578 | same complete proof |

All four projects were distinct, schema0003/mock, same SHA, passed/cleanup true,
failure codes none. Independent exact project-label container/volume/network0 after
each run; preview4 and existing developer volumes preserved. An initial independent
inventory command used unsupported volume `-a`; corrected to volume/network `-q`
and verified0. This diagnostic CLI error did not mutate resources or affect runtime.
F231/3.26s and H290/1.15s fresh post-runtime PASS. Full regression remains Todo6.

Largest measured phase: ownership Celery completion143.188/142.563s. File suite
actor A69.813/69.609s and B63.218/63.016s. Every work cycle stayed below360s and
cleanup below90s; original failed combined417.17s remains failure, not overwritten.
The redesign increases total work to four projects; these times are not an apples-
to-apples speedup claim against the original all-in-one workload. It proves bounded
repeatability with all coverage retained. Runtime receipts are local under
`.omo/evidence/issue-112/v2-*-cycle*.json` and `v2-aggregate.json`.

### v2 Todo6 full regression

At51ee0c2 (documentation-only since c05b815; executable code tree unchanged):

- Two unchanged `verify_schema_migrations.py --env-file .env.example --include-reset`:
  PASS76.100/77.000s. New projects d2a304395530/03beea0a3603, schema0003, round trips,
  identity/ownership constraints, nonempty refusals8, lock refusal, stale revision
  refusal/recovery and guarded reset; exact-label cleanup independently0 each.
- `verify_auth_sessions.py --env-file .env.example`: PASS27.373s, PostgreSQL/Redis
  outage/recovery, cleanup0. Admission12 -> active5; touch20 -> effective1; signup8;
  authentication50/p95 7.158ms; flow consume12 -> consumed1, replay refusal12, expired1.
- Fixed B0/F/M/H/S:631/231/248/290/94 PASS, respectively4.76/3.53/3.56/1.00/1.51s;
  S has only2 existing guarded-runtime skips.
- Authoritative tracked-only Linux archive:1128 PASS/3 existing guarded skips/4.38s;
  environment setup plus tests35.487s. Exact container cleanup0. Linux passed the
  real symlink test and the release-script syntax test. No private env/workspace mount.
- Windows full:1127 PASS/3 existing skips/7.59s, sole known Bash-path/native127
  failure in `test_supply_chain_release.py::test_release_script_guards_plan_scope_and_uses_terraform_rollback`.
  Fresh untouched cd654e5 archive in a new OS temporary directory reproduced that
  exact1 failure/native127 in0.39s. No test modification/skip/xfail to hide it.
- Unchanged frontend: `npm run lint`, `npm run build` PASS; `npm run test:auth`
  48 PASS/0.776s; `npm run test:auth:browser`34 PASS/18.3s, local mocked browser only.
- Final H290/1.10s and F231/3.32s PASS; D cumulative16/resume4/migration0 and Compose
  example PASS. Developer/preview unchanged, no live OAuth/provider/cloud operations.

Schema/auth receipts remain in their existing local evidence folders; summarized
results above are safe durable portfolio evidence. Deprecation warnings from test
dependencies are recorded as non-blocking; no dependency update was added to scope.

### 최초 combined 실행과 실패 (v2 이전 이력)

사용자의 frozen-SHA 요청으로 실행했다. SHA 일치, main cd654e5 유지, 브랜치와 사용자
변경 보존을 확인했다. 코드 변경은 정확한16개, migration0이다.

| Checkpoint | Result |
|---|---|
| Todo1 b10136a | B0 431 PASS/4.04s; S94 PASS/기존2 skip/1.62s |
| Todo2 01b1239 | file_asset/require_master; I25 PASS, M248/S94 회귀 PASS |
| Todo3 e9f38ec | files/ops routes; F175/M248/S94 PASS |
| Todo4 e4291d1 | no-store/raw-path/stream errors; F231/M248/H201 PASS |
| Todo5 ebfd530 | guarded F/O/V/E; H230/F231/M248/S94 PASS, py_compile PASS |
| Todo6 actual attempt1 | FAIL,417.17s including cleanup; successful cycles0/2 |

Actual revision `ebfd53068a643e00d7988130c14d6df41cbf51e3`, command
`python scripts/verify_ownership.py --env-file .env.example --cycles 2`, exit1.
Project `ownership-verify-fd3cd2d336a4`, head0003, provider mock. Final receipt:
phase=scenarios, auth_checks12, scenarios0, passed=false, cleanup=true.
F/O and V progress markers and metadata L/D/P/R/X/S/C/Q were observed; both actor
flows returned before worker/pipeline/http_races/expiry/celery_completion markers.
These are partial observations, NOT a final successful F/O/V/E/old-proof receipt.

Docker lifecycle events show cleanup stop signals at11:03:31 UTC and final container
removal at11:04:25 UTC (about54s). Combined with417.17s total, work reached the360s
deadline; deadline exhaustion is the timing-supported diagnosis. Existing receipt
intentionally suppresses exceptions, so the precise internal failure code is not
available and must not be invented. The last observed stage was Celery completion.
No raw container/application logs, secret or generation contents were recorded.

### 장애 분석과 중단 판단

기존 A 약338초에 파일/ops/폐기와 두 actor의 추가 workload를 한 cycle로 합친 예산이
충분하지 않았다. 개별 provider나 DB 장애로 확정할 근거는 없으며, phase별 소요시간과
고정 오류 코드를 보강해야 구체 병목을 구분할 수 있다. timeout/rate limit/worker 수를
늘리지 않았다. frozen Goal의 시간 한도 중단 조건을 적용해 두 번째 cycle 및 후속
schema2/auth1/full regression/PR를 실행하지 않았다.

초기 unit 실패도 보존한다: 세 digit-named storage tests의 fixture 누락, 기존 file404
detail과 AuthError bounded-code 기대값 불일치를 수정했다. H의 기존 `/metrics` 거절
테스트는 새 exact GET 계약에 맞춰 slash/비GET/query/payload 거절과 positive GET으로
보강했다. 테스트 삭제·skip·제품 인증 우회는 하지 않았다.

### 복구·보존과 승인된 재설계 (아직 구현/실행 전)

- 검증 runner cleanup true 외에 exact-label container/volume/network 목록 모두0을
  독립 확인했다. 기존 preview4와 개발용 volume은 보존했으며 수동 reset/prune하지 않았다.
- 구현 commit은 작업 브랜치에 보존한다. F1 경로 검토는 통과하나 F2–F4 종료 근거는
  부족하다. Ready PR/merge 및 parent109 종료는 하지 않는다.
- 사용자 승인: 검증만 두 suite로 분리한다. legacy ownership suite는 기존 auth/admission/
  metadata8/348/delete-race2/worker/pipeline/race/expiry를 두 독립 cycle에서 보존하고,
  file-ops suite는 F/O/V/E와 A/B 흐름을 별도 두 독립 cycle에서 검증한다.
- 각 cycle360s/cleanup90s와 각2cycle command900s를 유지한다. 최초 frozen 계획의
  "한 cycle에 모든 그룹" 수용 조건을 변경하도록 승인했다. 총4회 aggregate1800s이며
  단일 cycle의 시간 제한은 늘리지 않는다. 새 v2 계획과 SHA로만 재개한다.
  누락된 보안 matrix를 없애거나 전체 결과를 fake로 대체하는 제안은 아니다.
- 재실행 전에 고정된 phase duration/failure-code만 출력하는 안전한 계측을 설계한다.
  현재 frozen 계획은 수정하지 않았다. suite 분리/계측도 아직 구현하지 않았다.

새 계획 `.omo/plans/issue-112-g4-3b-file-ops-access-v2-goal.md`는 명시적 `--suite all`에서
ownership2 다음 file-ops2, 모두 다른 새 project와 동일 code SHA를 요구한다. 단일 suite
성공은 aggregate 완료로 간주하지 않는다. schema2/auth1/Linux/frontend/최종 CI/실제
merge/parent109 종료 조건은 유지한다. 새 변경은 기존 verification5개 경로로 제한한다.
원래 Todo1–5를 다시 구현하지 않고 재개용 Todo1–8로 남은 검증/전달 작업을 진행한다.

판단 근거: codebase-design의 작은 Interface 원칙에 따라 suite selector와 엄격한
aggregate를 기존 verifier Module에 둔다. 제품 권한 코드를 다시 설계하거나 임의
scenario/URL 실행 옵션을 노출하지 않는다. Trade-off는 격리 환경이2개에서4개로 늘어
전체 검증 비용이 증가하는 점이다. 네 번 모두 같은 코드에서 통과해야 coverage를 보존한다.
준비 중 Docker/DB 작업과 PR/merge는 수행하지 않았다. 효과와 실제 소요시간 개선은
v2 실행 전이므로 아직 측정/주장하지 않는다.
기존 수동 smoke workflow가20분으로 제한된 것을 확인해 기본 selector는 ownership으로
유지한다. all의 최대30분과 충돌하지 않으며 CI 설정은 변경하지 않는다. 기본 명령의
성공은 legacy suite만 증명하므로 complete=false이고, B 종료는 명시적 all이 필수다.

v2 frozen SHA-256:
`55f4fcf9c737b764f6747d781344ebcfd5d6bd3ce4f6a2ea1da001f63a91d909`.
준비 검증: F231 PASS/3.97s, H230 PASS/1.00s, Compose example/diff check PASS,
누적16경로와 계획 일치, 이번 코드 변경0/migration diff0. 이는 재설계 문서의 준비
근거이며 새 selector/계측/4cycle 구현을 검증한 결과가 아니다.

아래는 준비 시점 기록이다. "구현 미시작" 문구는 당시 상태이며 위 실행 결과가 최신이다.

A는 목록/상세/삭제를 보호했지만 파일 route는 아직 DB 조회 없이 storage를 열고,
운영 endpoint는 익명에게 전역 작업/지표를 반환한다. 로그인 화면과 metadata 소유권만으로
파일 URL을 아는 타 사용자를 막을 수 없다. B가 닫히기 전 공개 multi-user 노출은 No-Go다.

## 관측과 원인 분석

- files.get_file에서 resolve/stat이 첫 단계이고 Range는 그 뒤다. 등록하지 않은 파일을
  HTTP200으로 기대하는 기존 storage 테스트도 있으므로 explicit actor/Asset fixture로 바꿔야 한다.
- ops.health/runtime metrics 및 Prometheus route에는 require_master가 없다.
- OwnershipAccess에는 A의 read/use 구분은 있으나 정확한 local_path lookup은 없다.
- 기존 storage 경로 parser는 경로를 해석/정규화하므로 HTTP raw-path alias와 DB Job/path
  혼선은 storage 이전에 검사해야 한다. in-root symlink alias도 별도로 확인해야 한다.
- ScopedClient는 /metrics 및 HEAD/percent 공격 URL을 거절한다. 전역 URL guard를 느슨하게
  하는 대신 exact GET metrics와 고정 enum probe를 설계했다.
- A 실제 cycle337.73/338.12s에 비해 작업360s 한도의 여유가 작다. 기존 증거를 삭제하거나
  timeout을 늘리지 않고 stage 재사용/독립 actor 최대2개 병행을 설계한다. 초과 시 재설계한다.

## 해결 방법과 판단 근거

codebase-design 원칙에 따라 기존 Ownership Module의 작은 file_asset Interface를
확장한다. DB에 권한 근거를 모으고 HTTP Adapter는 인증→DB→storage→Range 순서를 지킨다.
Master read 예외가 delete/retry/use로 번지지 않게 한다. 운영 route는 require_user를
재사용하는 require_master로 제한하며 collector 이전에 거절한다.

정확한 기존16개 코드 경로, migration0을 고정했다. storage helper/worker/metadata route,
frontend/cloud를 건드리지 않는다. 별도 ACL/RLS/새 파일 저장소/인증 off toggle은 만들지 않는다.
무인 scrape 중단은 의도된 접근 정책 영향이며 서비스 인증은 별도 작업이다.
Rollback은 노출 중단 후 검토된 revert다. 되돌리면 파일/metrics가 다시 익명이 되므로
공개 서비스를 그대로 유지하는 rollback을 안전하다고 하지 않는다.

## 검증

준비 단계에서 실행한 기존 코드 baseline (backend):

```powershell
$env:AI_PROVIDER = 'mock'
python -m pytest tests/test_ownership_access.py tests/test_ownership_integration.py tests/test_storage.py tests/test_ops_api.py tests/test_ops_runtime.py tests/test_ownership_persistence.py tests/test_ownership_execution.py tests/test_verify_ownership_script.py tests/test_mock_auth_support.py tests/test_smoke_mock_golden_path_script.py tests/test_smoke_mock_retry_script.py tests/test_smoke_mock_i2v_duplicate_script.py tests/test_mock_smoke_workflow.py -q
```

431 PASS/4.45s; post-document recheck431 PASS/4.99s, exit0. Compose example config
PASS and diff hygiene PASS. This is not proof of unimplemented B protection.
Plan/spec exact16 existing-path parity,24 existing test targets and96 relative
document links passed. Todo1–8/F1–F4 and final-head delivery conditions are fixed.
Read-only PR/main/protection checks confirmed actual predecessor merge and strict3 checks.
Git main fast-forwarded, existing untracked .omo preserved; no Docker runtime/DB mutation.

실행 계획의 검증은 F(files)/O(ops)/V(revocation)/E(two-actor E2E) 네 그룹, 기존8개 metadata
그룹/348검사와 삭제경합2종, 이전 admission/worker/pipeline/race/expiry 증거를 보존한다.
두 실제 ownership cycle와 별도 schema2/auth1, Linux 전체와 기존 frontend를 실행한다.
명령/중단 조건/Todo1–8/F1–F4는 frozen Goal에 고정하며 현재 통과 결과로 표시하지 않는다.

## 결과와 영향

### v2 final review before delivery

Sequential executor self-reviews (not independent-agent approvals): F1 APPROVE
exact16/resume4/migration0, excluded code and both frozen SHA unchanged; F2 APPROVE
A1–A24 mapped to unit/actual HTTP-DB/schema proof with all old and FOVE checks retained;
F3 APPROVE aggregate4/schema2/auth1/Linux/frontend and independent cleanup0, sole
freshly reproduced Windows exception. Final F231/M248/H290 PASS3.20/3.32/1.03s and
114 relative documentation links PASS. F4 documentation review is ready, but F4
delivery is not APPROVE until final-head verify/both Scan-SBOM SUCCESS, actual squash
MERGED and justified parent109 closure. Final evidence is posted to Issue112.

현재 결과는 Session/owner 확인을 실제 파일·Range·운영 정보까지 연결한 구현과 재현 가능한
mock 검증이다. 사용자 A/B와 Master의 읽기 범위, 타인·고아·참조 혼선 거절, 로그아웃 후
새 Range401, private/no-store를 실제 HTTP/DB와 unit 경계 테스트로 확인했다.
codebase-design의 작은 Interface 원칙으로 제품은 기존 Ownership Module에 유지하고,
검증은 두 suite와 엄격한 aggregate로 정리했다. 추가 migration과 provider 비용은 없다.
Windows 고유 실패와 첫 runtime No-Go를 숨기지 않고 원인·복구·재검증 근거를 남겼다.
Live OAuth, cloud rollout, machine-scraper 운영 성공을 주장하지 않는다.

## 남은 위험과 다음 단계

- Ready PR/최종 head 필수3 CI/실제 squash merge와 parent109 종료는 Issue112 delivery
  링크에서 확인한다. 자동 병합 설정만으로 완료를 인정하지 않는다.
- 다음 Goal 입력은 User.id/require_user, 신규 Job owner와 owner-only mutation, Master
  read exception이다. Credit/Plan/Usage/Audit와 Master mutation은 아직 구현하지 않았다.
- schema reset은 새 verifier-owned DB에서만. 개발/preview DB와 사용자 변경은 보존.
- G4 완료 후에도 #99 긴급 폐기, 실제 OAuth/browser/proxy, cloud deployment 및 machine
  scraper 인증은 미완료다. 무료 local Redis를 사용하며 유료 서비스는 실행하지 않는다.
- 파일 삭제와 DB commit의 비원자성, 이미 전송된 bytes 회수, 신뢰된 DBA/파일시스템의
  동시 변조까지 해결한 것으로 표시하지 않는다.
