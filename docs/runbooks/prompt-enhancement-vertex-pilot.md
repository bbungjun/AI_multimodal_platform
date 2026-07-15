# Prompt Enhancement Vertex 20-case 파일럿 Runbook

이 runbook은 Issue #66의 실제 Gemini prompt enhancement와 Imagen paired generation을
`$20` workload-local 상한 안에서 실행하고, VQAScore·ImageReward·TIFA 결과와 사전 등록
판정을 생성하는 절차다. Mock 결과를 확인한 뒤 사용자가 실행을 별도로 승인하기 전에는
Vertex 요청을 보내지 않는다.

## 고정 계약

파일럿 입력은 다음 SHA-256으로 고정한다.

| 입력 | 버전/개수 | SHA-256 |
| --- | --- | --- |
| `benchmark.v2.jsonl` | 20 case | `259e25f7418a1a44f92de625ce7cb9fa150512a7cde21cf44a1a889d7934bd92` |
| `tifa_questions.v2.jsonl` | 80 QA | `460cd20d02b75ba737a685b770922f366d75ff4590fb92c37dd67391f2fe14d0` |
| `canonical_prompt_reviews.v2.json` | 한국어 10 case | `c42aa2ce408fa100f52c6cb3132faa2b7175b3f4c2d943ed2c7e9b08040fdc94` |
| `scorer_profile.v2.json` | 세 real scorer | `85415dd3394000b093bcc215c2a82a58ec1f536804a74cd92cfc13c25d692093` |
| `pilot_policy.v1.json` | 비용·요청·판정·HTTP deadline 정책 | `eb3b40195e28af97f2394bde09b62e63654b58c307d0a3a9bc9f5ab1ae76972d` |

Benchmark는 영어 10개와 한국어 10개다. `short_subject`, `detailed_subject`,
`multi_object`, `count_spatial`, `style_lighting` category별 4개이며 각 언어/category
교차 구간에 2개씩 들어 있다. 모든 case는 Imagen Fast, `balanced`, 1:1, arm별 2장으로
고정한다.

## 비용과 요청 상한

2026-07-13의 고정 단가는 Imagen 4 Fast `$0.02/image`, Gemini 2.5 Flash Standard input
`$0.30/1M token`, output `$2.50/1M token`이다. 실행 전에 공식
[Vertex AI 가격표](https://cloud.google.com/vertex-ai/generative-ai/pricing)가 바뀌지 않았는지
다시 확인한다.

| 항목 | 정상 실행 | 보수적 retry envelope |
| --- | ---: | ---: |
| Imagen | 80장 × $0.02 = $1.600000 | 최대 3회 provider attempt = $4.800000 |
| Gemini | 20회 × 최대 $0.0064 = $0.128000 | case당 최대 3 call group × 3 attempt = $1.152000 |
| 합계 | $1.728000 | $5.952000 |
| 승인 상한 | $20.000000 | 잔여 headroom $14.048000 |

실행기는 prompt enhancement HTTP 요청 20회, generation HTTP 요청 40회, 이미지 80장,
provider retry 3회를 넘기기 전에 중단한다. 요청을 보내기 전에 ledger에 reserve하여 process
중단 뒤 같은 단계를 무심코 재요청하지 않는다.

파일럿 policy의 `limits.http_timeout_sec`는 `60.0`초다. 이는 backend가 provider retry와
응답 검증을 완료할 시간을 확보하기 위한 evaluation client deadline이며, preflight hash에
포함된다. timeout이 발생하면 ledger에는 `failure_type=HttpRequestTimeoutError`,
`failure_reason=client_timeout`, `timeout_sec`만 남고 prompt나 raw exception text는 저장하지
않는다.

`$20` 가드는 이 파일럿이 요청하는 workload의 보수적 추정치다. Google Cloud Billing
account의 결제 hard stop이 아니며 같은 project의 다른 사용량, 세금, 환율, credit, 지연
반영 비용은 포함하지 않는다. Cloud Billing budget/alert도 일반적으로 알림 수단이지 즉시
차단 장치로 가정하지 않는다.

## 사전 등록 판정

Vertex 결과를 보기 전에 다음 규칙을 고정한다. case별 `Enhanced - Raw` delta를 만들고
seed `6600`, 10,000회 paired bootstrap 95% CI를 계산한다. Tie threshold는 VQAScore
`0.001`, ImageReward `0.01`, TIFA `0.0`이다.

- `proceed_to_full_benchmark_review`: 20 case가 실패·누락 없이 완료되고, VQAScore와
  ImageReward 평균 delta가 모두 양수이며, 둘 중 하나의 CI 하한이 `> 0`, 두 지표 모두 CI
  상한이 `>= 0`, TIFA CI 하한이 `>= -0.05`다.
- `stop`: 두 primary metric의 CI 상한이 모두 `< 0`이거나 TIFA CI 상한이 `< -0.05`다.
- 나머지는 `revise_or_expand`다.
- 언어/category slice는 표본 수가 작으므로 탐색 결과로만 해석한다.

## 1. 비용 없는 preflight

Repository root에서 실행한다. Provider를 호출하지 않는다.

```powershell
.\scripts\run_prompt_eval_vertex_pilot.ps1 -Mode Preflight
Get-FileHash `
  evals/prompt_enhancement/runs/issue66-preflight/preflight.json `
  -Algorithm SHA256
```

Preflight는 policy/input hash뿐 아니라 현재 Git commit, tree, dirty 상태도 포함한다. 출력이
`READY`인 clean revision의 plan SHA-256만 승인할 수 있다. `CANDIDATE ONLY — DIRTY
WORKTREE` 출력은 개발 검증용이며 실제 실행 승인에 사용할 수 없다. 정책, 입력, 코드 또는
commit이 변경되면 hash도 바뀌므로 이전 승인을 재사용하지 않는다.

## 2. 20-case mock dry-run

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
$envFile = (Resolve-Path ..\..\.env.example).Path
python run_mock_e2e.py `
  --compose `
  --env-file $envFile `
  --benchmark benchmark.v2.jsonl `
  --run-id issue66-mock-dry-run `
  --poll-timeout-sec 120 `
  --health-timeout-sec 120
```

2026-07-13 개발 dry-run은 20 pair, 40 job cleanup, 80 PNG, synthetic score 240개,
case-statistic 60개를 만들었고 누락·실패 없이 완료됐다. 같은 run 재실행의 무중복성과 별도
failure run의 `mock_provider_failure`/cleanup도 통과했다. 이 수치는 orchestration 증거이며
이미지 품질 근거가 아니다.

유료 실행에 사용할 mock evidence는 병합 후 clean revision에서 새 run id로 다시 생성해야
한다. Runner는 mock manifest의 Git SHA와 `dirty_worktree=false`가 실제 실행 revision과 정확히
일치하지 않으면 거부한다.

## 3. 실제 실행 승인 gate

운영자는 사용자에게 다음을 보여주고 실제 실행 승인을 별도로 받아야 한다.

- 고정 plan SHA-256
- 정상 예상 `$1.728000`, retry envelope `$5.952000`, 상한 `$20`
- 20 enhancement HTTP 요청, 40 generation HTTP 요청, 80 image
- mock dry-run 통과 결과
- `$20` 가드의 billing-account 한계

예산 승인만으로는 실제 실행 승인이 아니다. 승인 전에는
`VERTEX_PILOT_EXECUTION_APPROVED=yes`를 설정하지 않는다.

## 4. 실제 Vertex paired generation

개인 GCP context를 선택하고 retry cap을 **stack 시작 전** process 환경에 고정한다. 그 다음
`docs/runbooks/vertex-live-qa.md`에 따라 Vertex stack을 시작한다. `/api/health`는 provider
`ready`와 `provider_retry_max_attempts=3`을 함께 반환해야 한다. Compose의 backend와 worker는
같은 `PROVIDER_RETRY_MAX_ATTEMPTS` 값을 사용한다.

```powershell
. .\scripts\use_personal_gcp.ps1

$planSha = "<clean merged revision에서 생성한 preflight SHA-256>"
$env:AI_PROVIDER = "vertex"
$env:PROVIDER_RETRY_MAX_ATTEMPTS = "3"
$env:VERTEX_PILOT_EXECUTION_APPROVED = "yes"
$env:VERTEX_PILOT_APPROVED_PLAN_SHA256 = $planSha

docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
$health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
if (-not $health.ready -or $health.provider_retry_max_attempts -ne 3) {
  throw "Vertex readiness or provider retry cap does not match the approved pilot."
}

.\scripts\run_prompt_eval_vertex_pilot.ps1 `
  -Mode Execute `
  -ApprovedPlanSha256 $planSha `
  -RunId "issue66-vertex-YYYYMMDD-001"
```

`pilot_usage.json`은 prompt나 credential을 저장하지 않는다. 단계 id, 모델, 요청/완료 상태,
latency, token count, provider attempt, public failure code만 기록한다. 실행 중 실패하면 같은
run id의 ledger와 manifest를 먼저 확인한다. 자동으로 새 run을 만들어 비용을 중복 발생시키지
않는다.

## 5. Real scorer와 최종 보고서

Generation이 `lifecycle=scoring`에 도달한 뒤 다음을 실행한다. Scorer 컨테이너는 network를
차단하고 기존 exact-revision model cache만 사용한다.

```powershell
.\scripts\finalize_prompt_eval_vertex_pilot.ps1 `
  -RunId "issue66-vertex-YYYYMMDD-001" `
  -ApprovedPlanSha256 $planSha
```

생성되는 핵심 artifact:

- `scores.jsonl`: 80 image × 세 real scorer = 240 score
- `case_statistics.jsonl`, `summary.json`, `report.md`: case paired 통계와 slice
- `pilot_usage.json`, `pilot_usage_summary.json`: 요청·latency·retry·비용 근거
- `pilot_decision.json`, `pilot_result.md`: 사전 등록 규칙으로 계산한 최종 권고

최종화는 20/40/80 exact count, 실패 요청 0, retry hard cap, 모든 artifact hash를 다시 검증한다.
결과를 본 뒤 TIFA 허용폭, tie threshold 또는 판정 규칙을 변경하지 않는다.

`recorded_response_estimate_usd`는 API가 반환한 최종 Gemini response token과 charged Imagen
결과만 사용하므로 repair/retry 중간 response가 있으면 실제 비용보다 작을 수 있다. 비용 판정은
항상 모든 허용 call group/retry를 포함한 `conservative_committed_envelope_usd`를 우선한다.

## 중단 조건

- personal account/project guard 또는 Vertex readiness 실패
- preflight hash와 승인 hash 불일치
- tracked worktree가 dirty 상태
- mock artifact 누락/hash 불일치
- 요청·이미지·retry·비용 상한 초과 예상
- ledger의 reserved 단계를 안전하게 reconcile할 수 없음
- scorer model revision/cache/resource 검증 실패

이 경우 실제 호출이나 full benchmark로 우회하지 않는다. 원인과 이미 발생한 public usage
count를 기록한 뒤 재개 여부를 다시 승인받는다.
