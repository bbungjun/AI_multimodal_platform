# Issue #107 — Worker ownership and pipeline/race proof

- 상태: **In Progress — Todo6**, 2026-09-03. 준비 기록과 아래 실행 기록을 구분한다.
- [Issue107](https://github.com/bbungjun/AI_multimodal_platform/issues/107),
  branch `codex/issue-107-worker-ownership-invariants`.
- Base: A [PR106](https://github.com/bbungjun/AI_multimodal_platform/pull/106)의 실제 squash merge
  `d40a8f704df583c050a6a89c235c311a0d4aef77`; schema head0003 그대로.
- [상세 spec B1–B4](../initiatives/g4-2-owner-persistence-admission-spec.md),
  [전체 정책](../initiatives/auth-credits-master-console.md#ownership-invariants).

## 배경과 문제

A는 요청 접수 시 owner와 참조를 검사한다. 비동기 worker는 이후 다른 시점에 실행되며,
직접 handler 호출이나 polling 재개에서도 저장된 관계를 다시 확인해야 한다.
pipeline 연결은 parent/child/Asset/outbox를 함께 다루므로 같은 owner 보존과 반복 실행의
안전성을 실제 PostgreSQL에서 검증할 필요가 있다. 이는 아직 B의 구현 성과가 아니다.

## 관측과 원인 분석

- 직접 T2I/T2V/I2V와 polling 경로가 분리돼 있다. dispatch만 감싸는 설계로는 호출을 놓친다.
- 현재 pipeline child 조회에는 row lock/blocked 재검사가 없어 반복 link가 outbox를
  중복 생성할 수 있는 구조다. 이 준비 단계에서 실제 경합을 실행한 것은 아니다.
- T2I completion/link가 같은 try에 있고, handlers는 rollback 후 Job id를 읽는다.
  A에서 확인한 expired ORM 위험이 이 경계에도 있어 별도 회귀가 필요하다.
- handler/pipeline 기존 fake는 owner와 source parent 관계가 불완전하다. ownership을
  우회하지 말고 명시적 owner/관계를 제공하도록 test adapter를 갱신해야 한다.
- 원래10개 후보에 real proof까지 모두 넣으면 identity helper의 책임이 커진다.
  guarded execution helper1개를 추가한11개 allowlist로 실제 proof를 분리했다.

## 해결 설계와 판단 근거

codebase-design의 작은 Interface/Locality 원칙으로 기존 Ownership Module에
`validate_execution_references(session, job)`를 추가한다. actor/Session을 새로 만들지 않고
저장된 Job owner를 기준으로 남은 관계를 검증한다. 실패는 해당 Job에만 고정 safe code를
기록한다. Session 만료를 이미 접수된 Job의 취소로 해석하지 않는다.

pipeline은 child row lock 후 owner/state/blocked를 재검사하고 unblock과 outbox를 같은
transaction에 둔다. completed parent와 link 실패를 구분하고 실패 전파는 safe result로
외부 식별자 없이 표현한다. 범용 ACL, 새 queue, recovery service, migration은 추가하지 않는다.

실경합은 단순 thread 동시 실행이나 임의 sleep을 성공 근거로 삼지 않는다. 테스트 전용
source lock holder와 실제 DB waiter 관측 뒤 해제하는 절차를 고정했다. 한정된 protocol,
timeout/EOF 정리와 실패 canary를 포함한다. worker corruption 함수 proof와 실제 Celery
pipeline E2E, unit provider/storage spy의 증거도 서로 구분한다.

## 실행 준비 검증

- PR106 MERGED 및 main의 `d40a8f7` 확인, `git fetch origin` 후 local main fast-forward.
- 시작 시 unrelated tracked/staged 변경0; 기존 `.omo` 계획/evidence 보존.
- `AI_PROVIDER=mock`, backend에서 다음 기존10개 파일 **282 PASS /3.59s**:
  `python -m pytest tests/test_job_handlers.py tests/test_pipeline_link.py
  tests/test_generation_api.py tests/test_pipeline_api.py tests/test_ownership_persistence.py
  tests/test_verify_ownership_script.py tests/test_mock_auth_support.py tests/test_job_runner.py
  tests/test_outbox.py tests/test_outbox_dispatcher.py -q` (한 줄로 실행).
- spec/Goal exact11 중복0, 신규 파일2개, Todo1–8/F1–F4 구조 일치 검사 PASS.
- 최종 준비 재검증 **282 PASS /3.14s**, 상대 문서 링크77개/오류0,
  `git diff --check`/status/staged 경로 검사 PASS, 제품/config/test 변경0.
- frozen local/untracked plan:
  `.omo/plans/issue-107-g4-2b-worker-ownership-invariants-goal.md`.
  SHA256 `16f6cda60a7306b86bbd909c84241e25394117bb2953ae4445c70c550e271064`.
  다른 기기에서는 exact bytes를 별도로 전달해야 한다. hash는 파일 백업이 아니다.

## 결과와 영향

Issue/branch와 한 Todo씩 실행할 수 있는 계획을 준비했다. 현재 변경은 문서뿐이며
worker 보안 PASS, race 성공 횟수, Docker 정리 결과, B PR/merge 성과를 주장하지 않는다.
미래 종료 조건은 P11–P16 + 기존 A 회귀, 독립 전체2cycle/cleanup0, Linux 전체와
frontend 무변경 회귀, Ready PR의 최종 head verify/양쪽 Scan-SBOM 및 실제 squash merge다.

## Rollback·남은 위험·다음 단계

- 다음 단계는 frozen SHA를 포함한 명시적인 G4.2B Goal 실행 요청이다.
- schema/model/migration은 바꾸지 않는다. 향후 코드 rollback은 A 호환 head0003을
  유지하되 worker 보호가 사라짐을 명시하고 공개 배포 금지 상태를 유지한다. DB reset은 하지 않는다.
- 비정상 pipeline link의 자동 복구는 범위 밖이다. parent 완료/child 미연결 상태를
  숨기지 않고 안전한 실패 결과와 운영상 잔여 위험을 기록해야 한다.
- 임의 동시 DB 변경과 provider side effect를 원자적으로 묶지는 않는다. 검증 시점과
  provider 성공/DB 실패의 비원자성을 성과와 섞지 않는다.
- 11개 외 코드 경로나 migration, developer/preview reset이 필요하면 구현 전 재설계한다.
- G4.3 조회/list/delete/file/ops/cache와 긴급 폐기/live 검증은 별도다. 외부 provider,
  Google OAuth, managed Redis/cloud 비용을 발생시키지 않는다.

## 실행 기록

### Todo1 — preflight

명시적 Goal 요청 후 SHA/branch/base 일치 확인. 원격 main은 여전히 A merge d40a8f7이며
tracked/staged 사용자 변경0, 기존 .omo 보존. B0 **282 PASS /4.40s**, S **106 PASS /1.48s**.
Docker Desktop local named-pipe endpoint와 host override 부재를 확인했다. 기존 preview
container5개(4 running/1 exited), default/preview volumes는 읽기 전용 확인만 했다.
이 단계는 새 worker 기능이나 실제 격리 검증의 완료를 뜻하지 않는다.

### Todo2 — behavioral RED

직접/재개5종 × 남은 참조4종 × foreign/missing2종40개와 null owner5개,
SQL scope/optional-null/source 필수/attempt 재검사/실제 ORM expire 회귀를 고정했다.
pipeline foreign 관계, 반복 outbox, lock, commit 실패, 혼합 owner cascade 계약도 추가했다.
W/E 합계 **70 expected FAIL /22 PASS /2.79s**, collection 오류0. 실패는 누락된
검증 Interface와 기존 pipeline 계약 때문이며 기존 무변경 schema 회귀106개는 PASS다.
기존 factory에는 명시적 일반 User owner와 source parent 관계를 제공했다. bypass/skip은 없다.

### Todo3 — worker Interface

저장된 owner와 남아 있는 참조의 SQL scope/반환 row를 검사하고 직접 실행, 각 attempt,
poll/source-read 직전에 적용했다. mismatch는 고정 오류로 현재 Job만 실패시키며 cascade는
하지 않는다. nested provider 변환에서도 이 예외를 유지하고 재시도하지 않는다.
rollback 전에 id를 보존했다. expire 테스트의 fake refetch도 일반 attribute 대입 시
ORM load를 유발해 `set_committed_value`로 실제 재조회 완료 상태를 모사하도록 정정했다.
기존 missing-source 테스트는 승인된 조기 실패 계약(queued/generating 없이 mismatch)으로
기대값을 바꿨다. E/handler **84 PASS /2.48s**, S106 PASS. pipeline9 RED는 Todo4에 남았다.

### Todo4 — pipeline transaction

child lock과 fresh 상태 재검사, 같은 owner/정확한 parent-Asset 관계 검증, 이미 unblocked
child의 no-op을 적용했다. 실패 전파는 자신의 child만 변경하고 foreign/null은 safe result로
건너뛴다. commit 실패는 rollback 후 safe result이며 generation 완료와 link를 분리했다.
예상 밖 link 예외도 완료 parent를 재분류하지 않는 회귀를 추가했다.
W/E **98 PASS /2.20s**, S **106 PASS /1.30s**; Todo2 RED 전부 해소. 실제 lock 경합은 아직 미검증이다.

### Todo5 — guarded proof helper

고정 명령만 받는 test-only helper로 실제 FK를 유지한 foreign worker20종, 두 Session의
child lock overlap, HTTP race3종, admission 후 Session expiry, Celery 결과 bytes 검증을
구성했다. host label/DB name/head/fixture identity guard를 재사용한다. lock holder는
20초 self-timeout/EOF rollback, host는 bounded ACK와 process reap을 보장하고 실패 시
전체 owned project cleanup으로 이어진다. launcher kill을 DB 정리 증거로 간주하지 않는다.
H **144 PASS /0.87s**, W **98 PASS /2.09s**, S **106 PASS /1.14s**. canary 출력,
잘못된 대상·operation·records, head/identity, EOF·timeout·broken pipe 음성 테스트 포함.
이 시점의 검증은 단위/guard 검증이며 실제 2cycle 성공은 Todo6에서 별도 기록한다.

### Todo6 — first real failure and diagnosis

최초 R은122.67초에 HTTP race 단계에서 실패했고 cleanup=true, exact-label 잔여0이었다.
진단 재현101.55초에서도 create/create의 release ACK가 EOF로 끝났다. ready ACK는
정상이며 Windows text pipe가 CRLF를 전달한다는 별도 컨테이너 probe를 확인했다.
LF literal 비교가 release를 거부한 원인이므로 bounded JSON shape/boolean 검증으로
CRLF/LF를 모두 지원했다. HTTP waiter 관찰의5초도 label 검사와 개별 command까지
공유 deadline으로 묶었다. 20초 holder self-timeout과 기존 HTTP10초는 바꾸지 않았다.
추가 timeout 테스트에서 전역 monotonic 패치가 asyncio까지 침범한 실패도 발견해,
helper module에만 clock fake를 주입했다. 실패 run과 진단 run은 accepted cycle이 아니다.

### Todo6 — accepted independent cycles

불변 구현 `ff808b0051570c8a7feeb951effc7f6cb35e736a`에서 canonical R2를 재실행했다.
서로 다른 fresh Compose project의 결과는 각각 **274.97초 /272.36초**이며,
합계547.33초로 전체900초 예산 안이다. 각 cycle: auth12/admission111/smoke3,
execution20/pipeline4/race3/expiry1, passed=true/cleanup=true. 이는 fake-only가 아니라
실제 PostgreSQL lock 대기, 인증 HTTP 경합, Redis/Celery 처리, storage bytes 검증이다.
worker20은 유효 FK의 foreign 관계이며 불가능한 null/missing FK는 unit proof와 구분한다.
pipeline4는 DB link race+foreign link+foreign cascade+Celery E2E다. expiry1은 접수 후
A Session만 만료시켜 /me401과 기존 Job 완료/소유자 보존을 함께 확인했다.
검증 명령: `python scripts/verify_ownership.py --env-file .env.example --cycles 2`.
로컬 safe receipts: `.omo/evidence/issue-107/cycle1.json`, `cycle2.json`.
두 project의 container/volume/network는 별도 exact-label 조회에서도 모두0이었다.
기존 default/preview DB와 volume, preview 서비스는 보존했다. 전체 회귀/CI/merge는 다음 단계다.
