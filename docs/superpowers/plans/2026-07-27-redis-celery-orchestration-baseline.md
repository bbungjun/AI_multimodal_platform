# Redis/Celery 오케스트레이션 기준선 구현 계획

> Issue [#83](https://github.com/bbungjun/AI_multimodal_platform/issues/83)의
> GKE mock 기준선을 재현 가능하게 측정한다.

## Task 1: 지표 계산과 안전 preflight를 테스트로 고정

**Files**

- Create: `backend/tests/test_benchmark_mock_orchestration_script.py`
- Create: `scripts/benchmark_mock_orchestration.py`

1. percentile, state history timestamp, duplicate 판정의 실패 테스트를 작성한다.
2. mock health, dispatch mode, rate-limit guard의 실패 테스트를 작성한다.
3. 테스트 실패를 확인한다.
4. 최소 구현으로 테스트를 통과시킨다.

## Task 2: HTTP workload runner 구현

**Files**

- Modify: `backend/tests/test_benchmark_mock_orchestration_script.py`
- Modify: `scripts/benchmark_mock_orchestration.py`

1. phase 계획과 1,120-job 기본 workload 테스트를 작성한다.
2. concurrent POST, paginated polling, timeout/failure 수집 테스트를 작성한다.
3. warm-up 제외 aggregate와 JSON schema 테스트를 작성한다.
4. public DELETE cleanup과 cleanup 실패 보고를 구현한다.

## Task 3: GKE evidence sampler와 operator guard 구현

**Files**

- Modify: `backend/tests/test_benchmark_mock_orchestration_script.py`
- Modify: `scripts/benchmark_mock_orchestration.py`
- Create: `docs/runbooks/mock-orchestration-benchmark.md`

1. release profile guard와 whitelisted runtime config 파싱 테스트를 작성한다.
2. Deployment metadata, `kubectl top`, Redis queue depth, ops backlog sampler를 구현한다.
3. dry-run, temporary rate-limit override, 복구, 검증 명령을 runbook에 기록한다.
4. credential과 broker URL이 artifact에 포함되지 않는지 테스트한다.

## Task 4: 로컬 검증

**Files**

- Modify: `.gitignore`
- Modify: `docs/current-work.md`

1. benchmark script unit test를 실행한다.
2. 전체 backend pytest를 실행한다.
3. local mock에서 소형 workload로 end-to-end preflight를 실행한다.
4. `git diff --check`, status, staged 파일을 확인한다.
5. 구현을 커밋하고 branch를 push한다.

## Task 5: 배포 Redis/Celery 기준선 측정

**Files**

- Create: `docs/evidence/issue-83-redis-celery-baseline.md`
- Modify: `docs/current-work.md`

1. personal GCP guard와 현재 mock/celery/replica 상태를 확인한다.
2. worker에만 Imagen rate limit 임시 override를 적용하고 rollout을 확인한다.
3. dry-run 뒤 20 + 100 + 200x5 workload를 실행한다.
4. raw artifact에서 비밀과 개인 경로가 없는지 검사한다.
5. aggregate, peak resource, queue/backlog, 실패/중복을 evidence 문서에 기록한다.
6. 임시 override를 제거하고 worker rollout, mock health, job cleanup을 확인한다.
7. fresh verification 후 결과 문서를 커밋하고 push한다.

