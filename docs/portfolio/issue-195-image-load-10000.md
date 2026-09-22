# 이미지 생성 10,000 동시 요청: 문제·원인·개선 보고서

- Issue: [#195](https://github.com/bbungjun/AI_multimodal_platform/issues/195)
- 기준 코드: main `45a7826`, 측정 harness revision `1d2d5cf`
- 상태: 기준 측정 완료, 개선 및 재검증 진행 중
- 범위: local Docker, 실제 HTTP/auth/credit/Postgres/outbox/Redis/Celery/storage,
  `AI_PROVIDER=mock`. Vertex 처리량·Google OAuth·클라우드 성능의 증거가 아니다.

## 배경과 성공 기준

10,000명의 서로 다른 사용자가 이미지 한 장씩 동시에 요청했을 때 요청 접수와
비동기 완료가 모두 보장되는지 확인한다. 소수 사용자로 10,000회 반복하지 않는다.
동일 barrier에서 10,000 coroutine을 해제하고 실제 송신 분포와 peak in-flight를 기록한다.
테스트 전용 무작위 Session은 메모리에서만 유지하며 DB에는 hash만 저장한다.
생성·권한·크레딧 product 코드를 mock으로 바꾸지 않는다.

개선 후 목표는 첫 요청 10,000건 모두201, 완료10,000건, 각 사용자/job당 asset1개와
usage record1개, held reservation0, 잔여 reserved credit0, 실제 PNG 파일 검증이다.
재시도를 했다면 첫 요청 결과와 분리한다. 실행 시간이 길어져도 통과한 소량 테스트를
10,000건 결과로 대신하지 않는다. 대기시간과 전체 drain 시간은 측정값 그대로 보고한다.

## 환경과 재현

Docker Engine29.2.1, Docker 할당20 CPU, memory16,677,773,312 bytes.
같은 머신의 기존 unrelated 서비스는 유지했다. fresh project와 internal network를
사용하고 외부 egress를 차단했다. `.env` 및 credential은 읽거나 사용하지 않았다.

```powershell
python scripts/image_load.py --count 10000 --profile baseline --drain-seconds 120
```

기준 구성: API1 process, SQLAlchemy 기본 pool5+overflow10/timeout30s,
worker1×concurrency2, Imagen limiter5/min/process/model,
dispatcher batch50/poll1s, Postgres 기본 max_connections100.
HTTP timeout180s, 모든 HTTP 응답 이후 drain120s. 요청은 새 사용자 첫 생성이며
credit account/cycle 생성 비용도 포함한다. API는 Docker 내부에서 직접 호출하므로
공용 ingress/TLS/browser polling 부하는 포함하지 않는다.

## 수정 전 관측

[기준 receipt](../evidence/issue-195/baseline-10000.json),
[시간별 상태](../evidence/issue-195/baseline-10000-progress.jsonl).

| 지표 | 결과 |
|---|---:|
| 요청/peak in-flight/실제 송신 | 10,000 / 10,000 / 10,000 |
| coroutine 시작 분포 / 실제 송신 분포 | 1.779s / 0.217s |
|201 접수 |969 (9.69%)|
|503 /500 |8,208 /823|
|요청 p50/p95/p99 |49.843 /60.057 /65.141s|
|HTTP 응답 전체 수집 |67.837s|
|189.039s 후 완료 /pending /queued |30 /937 /2|
|outbox published |969|
|held reservations |939|
|DB 연결 최대 관측 |24 (시스템·관측 연결 포함)|
|로그 QueuePool timeout |823|
|PNG HTTP 표본 검사 |20/20|
|클라이언트 재시도 /transport error |0 /0|
|소유 리소스 cleanup 잔여 |0|

`complete=true`는 부하 측정이 끝났다는 의미다. 제품의 목표 달성 판정은
`passed=false`이며 미완료939건을 성공으로 계산하지 않는다. deadline 후 소유 test
환경을 정리했으며 이939건을 복구했다고 주장하지 않는다.

## 원인 분석

1. **API 진입에서 동시 DB 작업량을 제어하지 않는다.** 10,000개의 요청이 인증과
   admission에서 같은15개 연결 pool을 기다린다. admission의 pool timeout823건은
   unhandled500으로 노출됐다. 인증은 SQLAlchemyError를503으로 변환하므로8,208건의
   503은 동일 pool 경쟁과 일치한다(인증 예외의 상세 코드별 telemetry는 아직 없다).
   DB 서버의 `too many clients`는0이며, 무조건 DB max_connections를 올릴 문제가 아니다.
2. **단일 API process의 CPU 병목.** 진행 중 docker stats에서 API102.85% CPU,
   약940.8MiB를 관측했다. DB43.74%, 연결24로 DB 서버 전체 포화보다 API 처리와
   pool 대기가 먼저 발생했다. 이 단일 snapshot을 전체 기간 최대값으로 표현하지 않는다.
3. **생성 제한이 mock에도 적용된다.** worker2개 process가 각각5/min으로 제한되어
   첫10건 완료 후 대기하고 약60초 간격으로10건씩 증가했다. 실제로20→30건 증가와
   queued2가 관측됐다. outbox969건은 모두 publish되어 dispatch 유실 증거는 없다.

## 개선 방안과 판단 근거 (구현 전)

- API 요청을 인증/DB 진입 전에 제한된 수만 실행시키고, 유한한 대기 수와 deadline을
  둔다. 초과 시503/Retry-After로 명확히 거절한다. 인증·credit 검사를 생략하지 않는다.
- DB pool을 process별 설정으로 명시하고 API/worker/dispatcher 전체 연결 예산을
  계산한다. pool timeout만 크게 늘려 모든 요청이 DB를 붙잡게 하는 방식은 피한다.
- mock-only capacity profile에서 API process와 worker concurrency를 늘리고 Imagen
  제한을 높인다. Vertex 기본5/min과 cloud 구성은 바꾸지 않는다.
- 같은10,000 요청/timeout 조건으로 재검증하며, 생성 backlog의 drain deadline은
  별도 명시한다. 고정 PNG를 반환하거나 credit 경로를 우회해서 성능을 꾸미지 않는다.

## 검증과 남은 일

소량10건의 product 경로는 완료10, PNG10, held0으로 확인했다. 초기 harness는
internal Docker network에서 host port binding을 기대해 실행을 거부했고, readiness를
컨테이너 내부로 옮겼다. PostgreSQL numeric 집계값의 JSON 직렬화 오류도 수정했다.
이 두 실행은 제품 부하 실패로 계산하지 않았다.

다음은 admission/pool/config 개선, 단위 regression, 같은 burst 재측정, 전체 asset와
credit 정합성 증거, focused QA와 최종 runbook/PR 전달이다. 아직10,000건 처리를
지원한다고 주장할 수 없다.
