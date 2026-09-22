# 이미지 생성 10,000 동시 요청: 문제·원인·개선 보고서

- Issue: [#195](https://github.com/bbungjun/AI_multimodal_platform/issues/195)
- 기준 코드: main `45a7826`, 측정 harness revision `1d2d5cf`
- 상태: 로컬 mock 10,000 동시 요청 접수·생성 완료 검증 (`Mock Verified`)
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

## 개선 구현과 판단 근거

- `RequestAdmission`은 인증/DB 앞에서 process별 active4, waiting2500을 유한하게
  관리한다. 한도 초과 또는160초 대기 초과는503/Retry-After로 명확히 반환한다.
  health와 metrics는 차단하지 않는다. 기본 운영 값 active12/wait256/30초는
  기본 DB pool5+overflow10에서 여유 연결을 남긴다.
- DB pool size/overflow/timeout을 명시적으로 설정할 수 있게 했다. capacity profile은
  API8 process×5=40, worker16 process×1=16, dispatcher1, observer1로 약58개를
  예산화했다. Postgres100 연결 중 internal/autovacuum/관리 여유를 남긴다.
- mock-only capacity profile은 API8 process, worker concurrency16,
  Imagen limiter60000/min과 dispatcher batch200/poll0.1s를 사용한다. 이 limiter는
  process-local이므로 실제 Vertex 글로벌 quota 보장으로 재사용할 수 없다.
- API ingress와 queue/asset/credit 흐름은 유지한다. credential, production Vertex,
  GKE, 기존 Compose 기본값은 변경하지 않았다. rollback은 capacity override를
  사용하지 않고 API admission 설정을 이전 값으로 되돌리는 것이다.

## 검증과 남은 일

소량10건의 product 경로는 완료10, PNG10, held0으로 확인했다. 초기 harness는
internal Docker network에서 host port binding을 기대해 실행을 거부했고, readiness를
컨테이너 내부로 옮겼다. PostgreSQL numeric 집계값의 JSON 직렬화 오류도 수정했다.
이 두 실행은 제품 부하 실패로 계산하지 않았다.

수정 후100건 pilot은 100/100 접수, 100/100 완료, asset100, usage100, held0,
PNG HTTP 표본20/20이었다. 접수 p95 0.883s, 완료 p95 2.939s, 로그 pool timeout0,
owned cleanup0이다. 이 결과는10,000건 합격 근거가 아니라 변경 검증이다.

`python -m pytest tests/test_request_admission.py -q` 3 PASS, `npm run build` PASS,
Compose 기본/override config PASS. Windows host full pytest는 QA impact policy에 새
module 경로를 넣기 전1건, 기존 WSL Bash 경로1건 실패했다. policy 수정 후 해당
selector+admission 31 PASS, 기존 Bash 경로 테스트를 제외한 재실행은1906 PASS,
3 guarded SKIP, 1 deselected다. 수정 전 실패를 지우거나 합격으로 표현하지 않는다.

다음은 같은10,000 요청/HTTP timeout180초로 재측정하되 생성 drain1800초를
별도 명시한다. 첫 접수 상태, 실제 PNG 파일 전수 검사, outbox/credit 정합성,
CPU/DB/worker 신호를 보고 결정한다. 아직10,000건 처리를 지원한다고 주장할 수 없다.

### 첫 10,000 capacity 재측정: 대기 슬롯 편중

[실패 receipt](../evidence/issue-195/capacity-10000-first.json),
[시간별 상태](../evidence/issue-195/capacity-10000-first-progress.jsonl).

첫 요청10,000개/실제 송신 분포0.215초, peak in-flight10,000에서201은5,447건,
503은4,553건이었다. 56.254초에 모든 HTTP 응답이 왔고 p95/p99는
47.272/53.853초다. 접수된5,447건은137.462초까지 모두 완료됐고,
asset5,447, 디스크 파일 유효5,447, usage5,447, held0, outbox published5,447,
sample HTTP PNG20/20이었다. client retry0, cleanup0이다.

DB 연결 최대 관측55, pool timeout0, DB connection exhaustion0, Celery task failure0이다.
API process8개의 CPU snapshot이 고르지 않았다. 진입 제어 `max_waiters=2500`이
process별 한도라 OS의 connection accept 편중 시 일부 process의 한도에 먼저 도달한다.
503의 상세 code는 첫 실행에서 수집하지 않았으므로 이 원인은 관측값과 코드에 근거한
**추론**이다. 다음 반복은 허용된 public `detail` code만 aggregate하여 확인한다.
10,000건까지 접수하려면 각 process가 최악의 불균등 분배에도 burst를 보관할 수 있도록
capacity profile의 waiter 한도를 process당10,000으로 상향한다. 기본 운영 값256은
유지한다. 160초 deadline과4GiB API memory limit은 그대로 둬 무한 대기를 막는다.
요청 지연·메모리·실제 완료 수를 같은 부하로 다시 확인한다.

### 최종 10,000 capacity 재측정

- 측정 revision: `81b9b6a` (추적 파일 변경 없음)
- 명령: `python scripts/image_load.py --count 10000 --profile capacity --drain-seconds 1800`
- 근거: [통과 receipt](../evidence/issue-195/capacity-10000-pass.json),
  [시간별 상태](../evidence/issue-195/capacity-10000-pass-progress.jsonl).
- 조건: 앞선 capacity 실패와 동일한10,000명, HTTP timeout180초, mock provider,
  Docker20 CPU/16.7GB, internal network, API8 process/worker16. 변경은 process별
  waiter2500→10000과 public 오류 detail 집계다. 생성 drain deadline은1800초로 동일하다.

| 지표 | 수정 전 baseline | 첫 capacity | 최종 capacity |
|---|---:|---:|---:|
|201 접수 |969|5,447|**10,000**|
|503/500 |8,208/823|4,553/0|**0/0**|
|실제 송신 분포 |0.217s|0.215s|0.226s|
|HTTP 응답 수집 완료 |67.837s|56.254s|129.523s|
|HTTP p95/p99 |60.057/65.141s|47.272/53.853s|119.449/126.538s|
|전체 이미지 완료 |30/969 접수분|5,447/5,447 접수분|**10,000/10,000**|
|수집 종료 시각 |189.039s|137.462s|241.656s|
|완료 시간 p95/p99 |측정한30건 기준129.667/129.672s|78.055/78.798s|109.647/110.980s|
|outbox published |969|5,447|**10,000**|
|asset/usage/유효 디스크 파일 |30/30/표본20|5,447/5,447/5,447|**10,000/10,000/10,000**|
|held/reserved credit 잔여 |939/46,950,000,000|0/0|**0/0**|
|DB 연결 최대 관측 |24|55|51|
|pool timeout / task failure |823/0|0/0|**0/0**|
|client retry / transport error |0/0|0/0|**0/0**|
|owned cleanup 잔여 |0|0|**0**|

최종 실행은 API에서10,000개 HTTP 응답이 모두201이며 public 오류 detail은 비어
있었다. 최초 진입 한도 때문에 실패한 첫 capacity 결과와 달리 Postgres의 job 및
outbox가 각각10,000건으로 수렴했고, 모두 completed/published다. 서로 다른 owner
10,000명과 image asset·usage record10,000건을 확인했다. storage helper로10,000개
디스크 파일의 PNG signature와 DB 크기를 확인하고, 사용자 세션을 통과하는 HTTP
file route 표본20건도 모두 성공했다. `complete=true`, `passed=true`이며
test project의 container/network/volume cleanup 잔여는0이다.

첫 실패의503 상세 code는 수집하지 않았으므로 정확한 내부 경로는 미확정이다.
프로세스별 waiter 한도를 올린 뒤 동일한 burst에서503이0으로 바뀌고 DB pool
timeout도0인 점은 요청 분배 편중에 따른 admission 한도가 주원인이라는 설명을
강하게 뒷받침한다. 불확실성을 지우고 확정 원인으로 쓰지 않는다.

## 결과의 운영상 의미와 남은 위험

이 revision과 이 머신/설정에서는 1만 건의 **동시 요청 접수와 비동기 이미지
완료**가 mock mode로 검증됐다. 이 수치로 Vertex live 처리량, GKE HPA, 외부 ingress,
브라우저 polling 1만 명, 장애 중 recovery, 다중 노드 성능을 주장하지 않는다.
특히 HTTP 접수 p95가119.449초이므로 일반적인 ingress/client timeout 앞에서는
사용자가 실패로 볼 수 있다. API가 durable admission과 credit reservation을
완료해야201을 반환하는 현 contract의 비용이다. 실제 운영의 목표 대기시간을
정하고 DB/credit admission throughput을 별도로 개선하거나 명시적인202 접수
contract를 설계해야 한다. 동시 접수 숫자만으로 interactive UX를 인수하지 않는다.

capacity profile의 mock Imagen60,000/min은 실제 Vertex quota와 무관하며 기존
in-memory limiter는 여러 worker의 글로벌 호출량을 통제하지 못한다. 실제 provider
확장 전에는 공유 quota control, 비용/할당량, 429 처리 검증이 필요하다. 10,000개
실제 PNG는 이 머신에서 CPU·스토리지·DB가 제공한 결과이지 GKE 배포 결과가 아니다.

rollback은 `docker-compose.capacity.yml`을 적용하지 않는 것이다. default
admission은 pool15개 중 active12개까지만 실행하고 waiter256/30초로 제한한다.
이 기본값 자체의 10,000건 수용력은 검증하지 않았으며 capacity 수치는 해당
override가 적용된 환경에만 붙인다.
