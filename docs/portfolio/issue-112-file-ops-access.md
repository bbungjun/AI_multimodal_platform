# Issue112 — G4.3B File/Range and Master Ops Access

- **Planned / execution-ready**,2026-09-03. No implementation or B runtime proof yet.
- [Issue112](https://github.com/bbungjun/AI_multimodal_platform/issues/112), branch
  `codex/issue-112-file-ops-access`, parent [Issue109](https://github.com/bbungjun/AI_multimodal_platform/issues/109).
- [Spec/B contract](../initiatives/g4-ownership-access-control-spec.md),
  [canonical initiative](../initiatives/auth-credits-master-console.md).
- Main base `cd654e5003e70d78cd7390cc24e98f322a3383fe`: [PR111](https://github.com/bbungjun/AI_multimodal_platform/pull/111)
  actual squash merge. Its final head5738c0d verify/both Scan-SBOM all SUCCESS.
- Local/untracked frozen Goal `.omo/plans/issue-112-g4-3b-file-ops-access-goal.md`;
  SHA-256 `005908f870551f84d952a11e18f7348e11811337ac1010adf422fdd2ae65a29f`.
  Transfer exact bytes between machines; .omo whole staging forbidden.

## 배경과 문제

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

현재 결과는 실행 가능한 범위/경로/테스트/종료 기준을 정리한 준비 문서와 Issue/branch다.
제품 동작 변화0, migration0, runtime 비용0. F1–F4 구현 승인은 아직 없다.
예정된 성과는 “UUID/파일 URL을 알아도 요청마다 권한을 확인하고, 사용자와 Master의
읽기 범위를 실제 파일 bytes/Range/운영 정보까지 검증한다”이다. 아직 구현 성과가 아니다.

## 남은 위험과 다음 단계

- frozen SHA를 포함한 별도 Goal 요청 후 구현. Ready PR/필수3 CI/실제 squash merge까지 수행.
- schema reset은 새 verifier-owned DB에서만. 개발/preview DB와 사용자 변경은 보존.
- G4 완료 후에도 #99 긴급 폐기, 실제 OAuth/browser/proxy, cloud deployment 및 machine
  scraper 인증은 미완료다. 무료 local Redis를 사용하며 유료 서비스는 실행하지 않는다.
- 파일 삭제와 DB commit의 비원자성, 이미 전송된 bytes 회수, 신뢰된 DBA/파일시스템의
  동시 변조까지 해결한 것으로 표시하지 않는다.
