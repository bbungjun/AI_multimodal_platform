# Issue109 — Bounded ownership access design

- Status: **Planned — split proposed, approval pending** (2026-09-03).
- 후속 상태: 사용자가 분할을 승인했고 [Issue110 A 실행 준비](issue-110-metadata-ownership-access.md)를
  완료했다. 아래는 승인 전 관측 기록이며 당시15개 후보는 기존 unsupported-intent 테스트
  보존을 위해 A16개로 구체화되었다. G4.3 제품 구현은 아직 시작하지 않았다.
- [Issue109](https://github.com/bbungjun/AI_multimodal_platform/issues/109), branch
  `codex/issue-109-ownership-access-design`.
- Baseline: main `c84394a`, [G4.2B PR108](https://github.com/bbungjun/AI_multimodal_platform/pull/108)
  actually MERGED. [Policy/spec](../initiatives/g4-ownership-access-control-spec.md) and
  [initiative](../initiatives/auth-credits-master-console.md) remain the sources of truth.

## 배경과 문제

신규 콘텐츠 owner와 worker 참조 불변식은 구현했지만 목록·상세·삭제·파일·운영 endpoint의
접근 제어는 아직 완성되지 않았다. 로그인만 있다고 사용자 데이터가 격리되는 것은 아니다.
다음 실행은 sol/medium의 작은 context에서 완료할 수 있고 실제 HTTP 검증까지 포함해야 한다.

## 관측과 원인 분석

기존20개 경로 예상은 `scripts/mock_auth_support.py`와 그 테스트를 빠뜨렸다.
현재 safe client는 query string, JSON 배열, `/metrics`를 거절한다. 이 경계를 안전하게
확장하지 않으면 목록 pagination/scope와 Master 운영 권한을 실제 client로 검증할 수 없다.
또한 B proof는 A Session 만료 후 A Job을 B로 poll한다. 읽기 격리 후 이 요청은404가
정상이므로 허용된 Master read로 해당 관찰만 바꿔야 한다. 인증을 우회할 이유가 아니다.

삭제는 참조 detach와 파일 삭제를 함께 수행한다. 기존 create/retry의 Asset lock과
parent FK 순서를 고려하지 않은 Job-first lock은 역전 위험이 있다. 승인 후 A 계획에서
lock 순서를 고정하고 실제 PostgreSQL 경합으로 검증해야 한다.

## 해결 방향과 판단 근거

제안은 A15개(metadata/list/delete/cache/harness)와 B16개(file/Range/Master ops/final proof),
합집합22개로 나누는 것이다. 승인된 per-Goal20 제한은 유지한다. 테스트를 다른 파일에
억지로 합치거나 보안 검증을 생략하는 대안은 채택하지 않는다.

기존 Ownership Module의 Interface를 확장하여 read의 Master 예외와 owner-only mutation을
분리한다. route별 자체 ACL, 새 권한 framework, 새 DB migration은 추가하지 않는다.
A merge는 부분 완료이며 file/ops가 미보호이므로 공개 배포는 계속 금지한다.
현 단계는 문서만 변경하므로 runtime rollback은 필요 없다. 제품 변경의 rollback과
실제 file-delete/DB-commit 비원자성은 각 실행 계획에서 별도로 기록한다.

## 실제 검증

main fetch/fast-forward 및 PR108 실제 merge를 확인했다. 다음은 repository root에서 실행한
mock 기존 코드 baseline이다. 각 native 명령의 exit code를 확인한다.

```powershell
Push-Location backend
$env:AI_PROVIDER = 'mock'
python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py tests/test_asset_api.py tests/test_storage.py tests/test_ops_api.py tests/test_ops_runtime.py tests/test_ownership_persistence.py tests/test_ownership_execution.py tests/test_verify_ownership_script.py tests/test_mock_auth_support.py -q
$testExit = $LASTEXITCODE
Pop-Location
if ($testExit -ne 0) { throw 'focused baseline failed' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
git status --short --branch
if ($LASTEXITCODE -ne 0) { throw 'status check failed' }
git diff --cached --name-only
if ($LASTEXITCODE -ne 0) { throw 'staged check failed' }
```

결과: baseline `c84394a`에서 **385 PASS /4.71s**.
문서 수정 후 같은 명령 재실행도 **385 PASS /5.29s**. 후보 경로 자동 집계
(A15/B16/합집합22/공통9), 수정 문서의 상대 링크 target, `git diff --check`를 통과했다.
이는 **G4.3 코드/보안 테스트가 아직 미구현인 상태의 회귀 baseline**이다.
실제2cycle, 전체 backend/frontend 회귀, 보안 matrix, 최종-head CI는 향후 실행 gate이며
이 준비 단계에서 실행/통과했다고 주장하지 않는다.

## 결과와 영향

실행 전에 누락된2개 경로와 기존 proof의 cross-user 관찰을 발견했다. 승인 후 Goal이
코드만 완성하고 검증 도구 수정 때문에 범위를 넘는 상황을 예방하는 설계 근거를 남겼다.
현재 사용자 기능 변화는 없다. Docker, 개발/preview DB, migration, frontend, 실제
OAuth/provider/cloud를 변경하거나 실행하지 않았다. 기존 사용자 변경과 `.omo/`를 보존했다.

## 남은 위험과 다음 단계

- 사용자 분할 승인 → A child Issue/branch → exact allowlist/명령/Todo1–8/F1–F4/SHA 고정.
- 보호 응답 cache는 unhandled500/HEAD/Range도 포함해야 하며 streaming buffering 금지.
- B 실제 cycle 약275s에 추가 proof를 넣어 기존 work360s/cleanup90s 예산을 지켜야 한다.
  초과 시 재설계하며 임의 timeout 증가는 허용하지 않는다.
- Master-only `/metrics`는 기존 machine scraper와 호환되지 않는다. 별도 승인된 machine
  auth/live 배포 검증 전까지 cloud/scraper 변경이나 bypass를 추가하지 않는다.
- 파일 삭제와 DB commit의 비원자성, 이미 전송된 bytes의 회수 불가능성은 남는다.
- 전체 G4 완료는 B 최종 보안/실제2cycle/Ready PR/필수 CI/실제 squash merge 이후다.
  #99와 실제 OAuth/proxy/live gate는 별도이며 이 설계는 Live Verified가 아니다.
