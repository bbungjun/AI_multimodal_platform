# Prompt Enhancement 실제 Offline Scorer Runbook

이 runbook은 고정된 로컬 fixture를 실제 VQAScore, ImageReward, TIFA adapter로 평가하고
Vertex 파일럿 전에 scorer provenance와 tie threshold를 고정하는 절차다. 이 흐름은 Gemini,
Imagen, Veo 또는 Vertex API를 호출하지 않는다.

## 증거 범위

이 smoke가 증명하는 것은 다음뿐이다.

- hash-locked 전용 Docker 환경에서 세 실제 scorer가 모두 로드되고 finite score를 반환한다.
- scorer code/package와 모델 snapshot revision이 manifest에 기록된다.
- TIFA 질문과 한국어 canonical prompt 검토 기록이 benchmark hash에 묶여 있다.
- 같은 fixture 반복 추론의 noise로 metric별 tie threshold를 계산한다.
- scorer cache와 실행 산출물은 Git ignored 경계에 남는다.

로컬 fixture 점수는 Raw/Enhanced 이미지 비교가 아니므로 prompt enhancement의 품질 향상을
증명하지 않는다. 세 점수를 합산한 종합 점수도 만들지 않는다.

## 고정된 경계

`evals/prompt_enhancement/offline/scorer_profile.v1.json`이 source of truth다.

- Base image: Python 3.11.13 slim-bookworm digest 고정
- Runtime: CPU PyTorch 2.5.1, Transformers 4.49.0과 모든 transitive wheel hash 고정
- VQAScore: `t2v-metrics==3.0` wheel hash와 CLIP-FlanT5-XL snapshot 고정
- ImageReward: `image-reward==1.5` wheel hash와 ImageReward-v1.0 snapshot 고정
- TIFA: upstream algorithm Git revision, BLIP-VQA-base와 all-mpnet-base-v2 snapshot 고정
- TIFA QA: `tifa_questions.v1.jsonl`의 SHA-256 고정
- 한국어 canonical review: `canonical_prompt_reviews.v1.json`의 SHA-256과 benchmark SHA-256 고정

Upstream `t2v-metrics`와 `image-reward` 패키지는 범용 optional dependency를 모두 가져오지
않는다. Hash가 고정된 wheel을 `--no-deps`로 설치하고 필요한 CLIP-FlanT5/ImageReward 모듈만
좁게 import한다. Production backend/worker dependency와 Compose image는 변경하지 않는다.

## 리소스와 실행 한계

Versioned Docker image는 CPU 전용이다. `--device cuda`는 CUDA-enabled PyTorch가 없으므로
명시적으로 실패한다. GPU runtime은 별도 CUDA base/lock과 실제 검증이 추가되기 전까지
지원한다고 간주하지 않는다.

CPU 실행 정책:

- Docker에서 최소 12GiB 가용 메모리 필요
- VQAScore는 upstream과 같은 bfloat16 load path 사용
- ImageReward와 TIFA는 float32 사용
- 세 모델을 동시에 올리지 않고 VQAScore → ImageReward → TIFA 순서로 로드·해제
- 메모리 guard를 우회하는 `--skip-resource-check`는 OOM 위험을 명시적으로 수용할 때만 사용

최초 cache 준비에는 공개 model snapshot 약 10GB와 충분한 디스크가 필요하다. 모델 사용
조건과 라이선스는 각 upstream repository/model card를 실행 전에 별도로 확인한다.

## 이미지 빌드

Repository root에서 실행한다.

```powershell
cd evals/prompt_enhancement
docker build -f offline/Dockerfile -t creativeops-offline-scorers:v1 .
```

빌드는 `requirements-runtime.lock.txt`와 `requirements-adapters.lock.txt`의 모든 hash를
검증한다. Docker build context는 별도 `.dockerignore`로 `runs/`, `.model-cache/`, test cache를
제외한다.

## 모델 cache 준비

이 단계만 Hugging Face 공개 endpoint 네트워크를 사용한다. Exact commit snapshot을 모두 받은
후에만 각 디렉터리에 `prepared.json` marker를 원자적으로 기록한다.

```powershell
cd evals/prompt_enhancement
New-Item -ItemType Directory -Force .model-cache | Out-Null
docker run --rm `
  -v "${PWD}/.model-cache:/model-cache" `
  creativeops-offline-scorers:v1 `
  python -m offline.run_smoke --prepare-models --prepare-only
```

중단되면 같은 명령을 재실행한다. 완료 marker가 맞는 snapshot은 재사용하고 미완료 snapshot만
다시 준비한다. `--prepare-models` 없이 cache가 비었거나 marker가 다르면 추론이나 임의
네트워크 fallback 없이 실패해야 한다.

## 세 scorer 통합 smoke와 threshold 보정

```powershell
cd evals/prompt_enhancement
New-Item -ItemType Directory -Force runs/issue65-all-scorers-smoke | Out-Null
docker run --rm `
  -v "${PWD}/.model-cache:/model-cache" `
  -v "${PWD}/runs/issue65-all-scorers-smoke:/runs" `
  creativeops-offline-scorers:v1 `
  python -m offline.run_smoke --device cpu --output-dir /runs
```

성공 메시지는 다음 경계를 명시한다.

```text
REAL OFFLINE SCORER SMOKE COMPLETE — ADAPTER EXECUTION EVIDENCE ONLY.
```

산출물:

```text
runs/issue65-all-scorers-smoke/
  manifest.json
  calibration.json
  smoke_scores.json
  report.md
  fixtures/en-short-subject-001.png
```

`manifest.json`은 `provider_calls=none`, `evidence_kind=real`,
`quality_claim_scope=adapter_execution_only`를 기록한다. 모든 산출물 hash가 일치해야 한다.

## Tie threshold 규칙

세 scorer는 같은 canonical prompt와 fixture를 3회 반복 평가한다. 비용 발생 결과를 보기 전에
다음 규칙으로 epsilon을 고정한다.

```text
epsilon = max(
  metric별 사전 정의 floor,
  3 × max(abs(repeated_score - median(repeated_scores)))
)
```

사전 정의 floor:

| Metric | Floor |
| --- | ---: |
| VQAScore | 0.001 |
| ImageReward | 0.01 |
| TIFA | 0.0 |

Issue #65 로컬 실행에서는 세 metric 모두 반복 편차가 0이어서 floor가 최종 threshold가 됐다.
Issue #66은 이 `calibration.json`을 파일럿 전에 입력으로 고정해야 하며 Vertex 결과를 본 뒤
threshold를 변경하면 안 된다.

## 실제 로컬 검증 기록

2026-07-13 CPU 전용 container에서 다음을 확인했다.

- Model cache 준비: 7개 exact-revision marker, 약 1,697초, provider 호출 없음
- 통합 fixture smoke: 세 adapter, 약 197초, provider 호출 없음
- VQAScore: `0.6201549768447876`, 세 번 동일, threshold `0.001`
- ImageReward: `-0.23932480812072754`, 세 번 동일, threshold `0.01`
- TIFA: `1.0`, 세 번 동일, threshold `0.0`
- TIFA free-form `mug`가 고정 choice `cup`으로 SBERT mapping된 상세 기록 보존
- Manifest의 fixture, score, calibration, report hash 모두 일치

이 수치는 fixture adapter smoke 기록이며 Raw/Enhanced 품질 비교 결과가 아니다.

## 실패 대응

- **cache incomplete:** `--prepare-models --prepare-only`를 명시적으로 다시 실행한다.
- **RAM guard:** Docker Desktop memory limit을 늘리거나 충분한 호스트에서 실행한다. 우회 후
  OOM은 유효한 평가 결과가 아니다.
- **CUDA requested/unavailable:** CPU로 실행하거나 별도 GPU lock 구현 Issue를 먼저 진행한다.
- **profile/input hash mismatch:** QA, canonical review, dependency lock을 임의로 덮어쓰지 말고
  변경 이유와 새 version을 review한다.
- **model initialization/inference failure:** 공개 오류의 첫 원인부터 수정한다. 다른 scorer나
  mock 점수로 조용히 대체하지 않는다.
- **non-finite score:** 해당 run을 실패 처리하고 report 근거로 사용하지 않는다.

## 종료 검증

```powershell
cd ../..
git check-ignore evals/prompt_enhancement/.model-cache
git check-ignore evals/prompt_enhancement/runs/issue65-all-scorers-smoke/manifest.json
git status --short --branch
git diff --cached --name-only
```

실제 Vertex 파일럿은 이 runbook 완료만으로 허용되지 않는다. 사용자 비용/요청 한도 승인과
개인 GCP account/project guard를 별도로 통과해야 한다.
