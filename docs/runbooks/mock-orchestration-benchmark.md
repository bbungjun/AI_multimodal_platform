# GKE Mock 오케스트레이션 벤치마크

이 runbook은 Redis/Celery 기준선과 이후 PostgreSQL worker 후보를 같은 workload로
비교한다. `AI_PROVIDER=mock` 오케스트레이션 지표만 측정하며 실제 Vertex 생성 성능이나
품질을 증명하지 않는다.

## Workload와 비용 경계

- warm-up 20 jobs
- steady 100 jobs
- burst 200 jobs x 5 rounds
- 총 1,120 T2I mock jobs
- 실제 Gemini, Imagen, Veo 호출 0건

mock provider도 현재 worker의 Imagen rate limiter를 통과한다. 기본 5/min 상태에서
실행하면 queue 구조가 아니라 의도적인 provider throttle을 측정하게 되므로, benchmark
동안 worker rate limit만 5,000/min으로 임시 override한다. API, dispatcher, worker
replica와 worker concurrency는 변경하지 않는다.

## 1. 로컬 도구와 개인 GCP guard

repository root에서 실행한다. GCP CLI config와 kubeconfig는 개인 프로필 전용 경로를
사용하되, 문서나 artifact에 credential 경로나 payload를 기록하지 않는다.

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

test -n "$CLOUDSDK_CONFIG"
test -n "$KUBECONFIG"

profile="infra/gcp/release-profile.json"
project_id="$(python3 -c 'import json; print(json.load(open("infra/gcp/release-profile.json"))["project_id"])')"
cluster_name="$(python3 -c 'import json; print(json.load(open("infra/gcp/release-profile.json"))["cluster_name"])')"
cluster_zone="$(python3 -c 'import json; print(json.load(open("infra/gcp/release-profile.json"))["cluster_zone"])')"
namespace="$(python3 -c 'import json; print(json.load(open("infra/gcp/release-profile.json"))["namespace"])')"

gcloud config set project "$project_id"
gcloud container clusters get-credentials "$cluster_name" \
  --zone "$cluster_zone" \
  --project "$project_id"

gcloud auth list --filter=status:ACTIVE --format='value(account)'
gcloud config get-value project
kubectl get deployment -n "$namespace"
```

출력 account/project가 release profile과 다르면 중단한다. Secret, `.env`, Terraform
state/tfvars는 열거나 출력하지 않는다.

## 2. 현재 상태와 복구 기준 기록

```bash
kubectl get deployment creativeops-api creativeops-dispatcher creativeops-worker \
  -n "$namespace" \
  -o custom-columns='NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image'

curl --fail --silent "http://34.50.26.152/api/health" | python3 -m json.tool
curl --fail --silent "http://34.50.26.152/api/ops/health" | python3 -m json.tool

worker_pod="$(kubectl get pod -n "$namespace" -l app=creativeops-worker -o jsonpath='{.items[0].metadata.name}')"
kubectl exec -n "$namespace" "$worker_pod" -- python -c \
  'import json,os; keys=["AI_PROVIDER","JOB_DISPATCH_MODE","RATE_LIMIT_IMAGEN_PER_MIN","CELERY_WORKER_CONCURRENCY","CELERY_DEFAULT_QUEUE"]; print(json.dumps({key:os.environ.get(key) for key in keys}))'
```

필수 상태:

- API health `vertex.status=mock_provider`
- ops dispatch `mode=celery`
- API 2, dispatcher 1, worker 1 replica ready
- worker concurrency 2
- active job과 outbox pending 0

## 3. 임시 rate-limit override

```bash
kubectl set env deployment/creativeops-worker \
  -n "$namespace" \
  RATE_LIMIT_IMAGEN_PER_MIN=5000

kubectl rollout status deployment/creativeops-worker \
  -n "$namespace" \
  --timeout=180s

worker_pod="$(kubectl get pod -n "$namespace" -l app=creativeops-worker -o jsonpath='{.items[0].metadata.name}')"
kubectl exec -n "$namespace" "$worker_pod" -- python -c \
  'import os; print(os.environ.get("RATE_LIMIT_IMAGEN_PER_MIN"))'
```

마지막 출력이 `5000`이 아니면 benchmark를 실행하지 않는다.

## 4. Dry-run

```bash
python3 scripts/benchmark_mock_orchestration.py \
  --base-url "http://34.50.26.152" \
  --gke-profile "$profile" \
  --expected-dispatch celery \
  --minimum-imagen-rate-limit 5000
```

dry-run은 GCP account/project, release profile의 public base URL과 Celery mode,
현재 kubectl context의 exact GKE cluster, deployment, mock provider, rate-limit,
resource metrics, Redis queue를 확인한다. 하나라도 다르면 public workload를 보내기
전에 중단한다. job은 만들지 않는다.

## 5. 기준선 실행

```bash
run_id="redis-celery-$(date -u +%Y%m%dT%H%M%SZ)"
output="benchmarks/orchestration/runs/${run_id}.json"

python3 scripts/benchmark_mock_orchestration.py \
  --base-url "http://34.50.26.152" \
  --gke-profile "$profile" \
  --expected-dispatch celery \
  --minimum-imagen-rate-limit 5000 \
  --run-id "$run_id" \
  --output "$output" \
  --execute
```

실행 중 각 phase의 submit/completed 수가 출력된다. raw report는 Git에서 제외되며
job별 prompt, credential, broker URL을 포함하지 않는다. 성공 후 public DELETE API로
1,120개 job과 asset을 정리한다. 현재 outbox event에는 job FK가 없으므로 published event
row는 남으며, `ops_before`와 `ops_after` 증가량을 결과에 기록한다.

POST 응답이 timeout/disconnect되면 서버 commit 여부를 알 수 없으므로
`ambiguous_submissions`로 기록한다. 종료 경로는 성공, 실패, 사용자 interrupt와
관계없이 prompt의 exact run-id prefix로 job을 다시 조회한다. terminal job만 삭제하고
active/pending job은 `reconciliation.unresolved_active`에 남겨 operator가 복구한 뒤
정리하게 한다. cleanup 후에는 run-id를 다시 조회해 실제 잔여 job이 0인지 검증한다.
resource sampler 오류나 종료되지 않은 sampler thread도 benchmark 실패로 처리한다.

## 6. 반드시 원복

성공, 실패, 사용자 interrupt와 관계없이 임시 override를 제거한다.

```bash
kubectl set env deployment/creativeops-worker \
  -n "$namespace" \
  RATE_LIMIT_IMAGEN_PER_MIN-

kubectl rollout status deployment/creativeops-worker \
  -n "$namespace" \
  --timeout=180s

worker_pod="$(kubectl get pod -n "$namespace" -l app=creativeops-worker -o jsonpath='{.items[0].metadata.name}')"
kubectl exec -n "$namespace" "$worker_pod" -- python -c \
  'import os; print(os.environ.get("RATE_LIMIT_IMAGEN_PER_MIN"))'

curl --fail --silent "http://34.50.26.152/api/health" | python3 -m json.tool
curl --fail --silent "http://34.50.26.152/api/ops/health" | python3 -m json.tool
kubectl get deployment creativeops-api creativeops-dispatcher creativeops-worker \
  -n "$namespace"
```

rate limit은 ConfigMap 값인 `5`, health는 `mock_provider`, 모든 deployment는 desired=ready,
active job과 outbox pending은 0이어야 한다.

## 7. 결과 검토

```bash
python3 - "$output" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({
    "run_id": report["run_id"],
    "scope": report["evidence_scope"],
    "workload": report["workload"],
    "summary": report["summary"],
    "resource_summary": report["resource_summary"],
    "cleanup": report["cleanup"],
}, ensure_ascii=False, indent=2))
PY
```

다음이면 결과를 채택하지 않는다.

- completed가 집계 대상 1,100보다 작음
- failure, duplicate execution, cleanup failure가 하나라도 있음
- resource sample error가 있음
- ambiguous submission 또는 unresolved active job이 있음
- release profile의 base URL/Celery mode와 실행 인자가 다름
- 현재 kubectl context가 release profile의 GKE cluster와 다름
- mock provider 또는 celery dispatch guard가 report와 다름
- rate-limit wait가 발생했거나 임시 설정이 원복되지 않음
- 실제 Vertex 호출이나 비용이 발생함
