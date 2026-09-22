# Mock 이미지 10,000 동시 요청 부하테스트

이 runbook은 Issue #195의 local mock capacity 측정용이다. `AI_PROVIDER=mock`을
내부 Docker network에서 강제하므로 Vertex·Google 생성 API를 호출하지 않는다.
각 실행은 랜덤 프로젝트/DB/Redis/asset volume을 소유하며 종료 시 이 프로젝트만
정리한다. 기존 Compose, `.env`, credential, GCP workload는 건드리지 않는다.

## 전제와 비용

- Docker Engine 실행, 20 CPU/16 GiB 수준의 시험 머신과 15 GiB 이상의 여유 디스크.
- Python 3.11+, Compose v2 `!override` 지원.
- 기본 `capacity` 구성은 단일 머신 기준 8 API process, worker16 slot, mock Imagen
  60,000/min, process별 DB pool 5/1/1이다. 숫자는 Vertex/GKE 권장 설정이 아니다.
- 10,000개 이미지와 PostgreSQL ledger가 생성되어 Docker volume에 수 GiB를 쓸 수 있다.
  성공과 실패 모두 소유 volume을 정리한다. unrelated volume은 보존한다.

## 절차

```powershell
git status --short --branch
git diff --cached --name-only
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.capacity.yml config --quiet
python scripts/image_load.py --count 100 --profile capacity --drain-seconds 120
python scripts/image_load.py --count 10000 --profile capacity --drain-seconds 1800
```

`--count` 범위는1~10,000, timeout과 drain은 유한 범위만 받는다. 테스트는 fresh
DB에 1만 명의 OAuth 형태 테스트 사용자와 hash된 Session을 만들고 `POST
/api/generations`를 barrier에서 해제한다. 실제 무작위 session 원문은 파일에 남기지
않는다. 이후 Postgres의 terminal 상태와 outbox, credit, asset을 검사한다.

각 run의 `output/image-load/<profile>-<timestamp>/receipt.json`과
`progress.jsonl`은 로컬 정제 evidence다. receipt의 `complete`는 runner가 끝났다는
뜻이고 `passed`가 제품 검증 판정이다. `statuses`, `errors`, `accepted`,
`peak_inflight`, `send_spread_seconds`, HTTP p95/p99, 완료 p95/p99, outbox 상태,
held credit, 디스크 파일 수 및 sample HTTP PNG를 함께 판단한다. 실패 시 첫 구체적
상태와 `diagnostics.pool_timeouts`를 보고서에 남긴다.

별도 `baseline` profile은 commit 당시 기본 5/min Imagen 제한과 단일 API/worker2
상태를 비교하기 위한 것이다. 대량으로 실행하면 오래 대기한 작업이 생길 수 있다.

## 중단·복구

작업이 중단되면 해당 run의 project id는 receipt가 아닌 Docker resource label에서
확인한다. 이 스크립트는 정상 종료 시 자신이 생성한 것만 정리한다. 강제 중단으로
소유 project가 남았다면 이름과 `creativeops.verifier` label을 직접 확인한 뒤 해당
project의 Compose 파일을 사용해 `down --volumes`한다. 다른 project나 전체 Docker
환경을 대상으로 정리 명령을 실행하지 않는다.

## 해석 경계

10,000개 HTTP를 모두 접수·완료했다고 해도 실제 Imagen quota, GPU 처리량,
GKE HPA, cloud DB/Redis, public ingress, 브라우저에서의 2초 polling을 증명하지 않는다.
다중 worker의 in-memory limiter는 글로벌 provider quota를 보장하지 않으며 실제
Vertex 부하 검증에는 별도 공유 limiter와 비용/할당량 승인이 필요하다.
