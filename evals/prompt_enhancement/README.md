# 프롬프트 향상 평가 패키지

이 디렉터리는 CreativeOps Studio의 원본 프롬프트(`raw`)와 검토 후 수락한 향상
프롬프트(`enhanced`)를 paired benchmark로 비교하기 위한 독립 평가 경계다. Production
backend/worker 이미지나 데이터베이스에 평가 전용 상태와 무거운 scorer 의존성을
추가하지 않는다.

Issue #61은 버전이 있는 파일 계약을 정의했고, Issue #62는 실제 제품 HTTP API를
사용하는 mock paired-generation runner를 추가했다. Issue #63은 실제 품질을 주장하지 않는
deterministic synthetic VQAScore, ImageReward, TIFA adapter와 case 단위 paired 통계를
추가했다. 실제 offline scorer는 후속 Issue #65 범위다.

`schemas.py`는 다음 artifact를 검증한다.

- `benchmark.v1.jsonl`: 언어, category, 원본/평가 프롬프트, 대상 모델과 생성 파라미터
- `manifest.json`: Git/provider/model/scorer 버전, lifecycle, paired checkpoint와 artifact hash
- `cleanup.json`: backend generation artifact 보존 정책과 job별 cleanup 상태
- `pairs.jsonl`: Raw/Enhanced 실행 프롬프트, job, asset, 실패와 retry 정보
- `scores.jsonl`: 이미지별 VQAScore, ImageReward, TIFA 결과
- `case_statistics.jsonl`: 프롬프트별 arm 평균, paired delta, tie threshold와 W/T/L
- `summary.json`: metric별 paired 통계와 slice 집계

`generate_pairs.py`는 prompt enhancement, T2I generation, job polling, asset metadata,
file serving, generation cleanup API를 순서대로 호출한다. Application DB/session, outbox,
Celery, storage helper 또는 Vertex client를 직접 import하지 않는다.

모든 JSON/JSONL record는 `schema_version`을 명시한다. 현재 지원 버전은 `1`뿐이며,
누락되거나 더 새로운 버전은 파일 경로와 문제 필드를 포함한 오류로 거부한다. Manifest는
임시 파일을 같은 디렉터리에 flush한 뒤 원자적으로 교체하므로 중단 후 checkpoint를 다시
읽을 수 있다.

## 로컬 검증

이 패키지는 `.env`, 애플리케이션 설정, Vertex credential을 읽지 않는다. 검증은 mock
provider 표시만 사용하며 외부 모델이나 API를 호출하지 않는다.

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python verify_mock.py
```

## Mock paired-generation 실행

기본 benchmark는 영어/한국어 4개 case로 구성되며 case마다 Raw 2장과 Enhanced 2장,
총 16개의 deterministic mock PNG를 만든다. 실행 프로세스와 backend health가 모두
mock임을 확인한 뒤에만 요청한다.

이미 실행 중인 mock Compose 사용:

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python generate_pairs.py --run-id mock-local-001
```

필요한 서비스까지 시작:

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python generate_pairs.py --compose --run-id mock-local-001
```

같은 Git SHA, dirty 상태, benchmark hash, enhancer/template 설정과 `run-id`로 다시
실행하면 완료 arm은 local file hash만 검증하고 새 enhancement/generation 요청을 만들지
않는다. Submitted checkpoint는 기존 job id를 polling한다. Pair 생성이 끝난 manifest는
다음 scorer 단계가 인수할 수 있도록 `lifecycle=scoring`으로 남는다.

## Mock metric과 통계 실행

Paired generation이 `scoring`까지 완료된 같은 run id를 사용한다. 두 명령은
`AI_PROVIDER=mock`을 요구하며 `.env`, provider client, 실제 scorer model을 읽거나 호출하지
않는다.

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python score_pairs.py --run-id mock-local-001
python summarize.py --run-id mock-local-001
```

`score_pairs.py`는 benchmark snapshot에서 case별 canonical 평가 프롬프트를 고르고 Raw와
Enhanced 모두 같은 prompt hash로 평가한다. 한국어 case에 검토된 영문 canonical prompt가
있으면 그 값을 사용한다. 실행 prompt 또는 향상 prompt를 Enhanced arm의 정답으로 사용하지
않는다.

`summarize.py`는 이미지 점수를 먼저 case/arm별 평균으로 줄인 뒤 case별
`Enhanced - Raw` delta를 계산한다. 그 case delta로 평균·중앙값, fixed-seed paired bootstrap
95% 신뢰구간, metric별 tie threshold 기반 W/T/L, 언어/category slice를 만든다. 세 지표는
별도로만 기록하며 종합 점수를 만들지 않는다. Mock report의 수치는 orchestration 검증용
synthetic evidence이고 이미지 품질 또는 prompt enhancement 효과의 근거가 아니다.

완료된 run에서 두 명령을 다시 실행하면 manifest에 기록된 artifact hash를 검증한 뒤 기존
결과를 재사용한다. 같은 입력과 고정된 통계 설정은 byte-stable artifact를 만든다.

기본 정책은 local run artifact를 항상 보존하고, local copy와 hash checkpoint가 끝난
terminal generation job 및 backend asset file만 삭제하는 것이다. Prompt enhancement는
public delete API가 없으므로 provenance row가 남는다. Backend generation job/asset도
보존해야 하면 다음처럼 실행한다.

```powershell
python generate_pairs.py --run-id mock-local-keep-001 --keep-artifacts
```

실패 job은 public error, retry count와 함께 `failed` manifest에 기록한 다음 기본 cleanup
정책을 적용한다. 실패·중단 manifest와 이미 내려받은 local file은 삭제하지 않는다.
통제된 mock failure 경로는 기본 성공 benchmark와 분리된 fixture로 확인할 수 있다.

```powershell
python generate_pairs.py `
  --benchmark fixtures/benchmark.failure.v1.jsonl `
  --run-id mock-failure-001
# 의도된 non-zero 종료와 mock_provider_failure manifest를 확인한다.
```

## 로컬 artifact 경계

실행 결과는 아래 구조를 사용한다.

```text
runs/<run-id>/
  manifest.json
  cleanup.json
  pairs.jsonl
  images/
  scores.jsonl
  case_statistics.jsonl
  summary.json
  report.md
```

`runs/`와 `.model-cache/`는 Git에서 제외된다. 생성 이미지, checkpoint, credential,
token, 개인 PC absolute path는 커밋하지 않는다. 검토된 집계 결과를 보존해야 한다면 로컬
run 디렉터리를 그대로 추가하지 말고 별도의 versioned evidence 위치로 필요한 요약만 복사해
검토한다.

## 계약상 안전장치

- Mock provider run은 반드시 `evidence_kind=synthetic`이고 report는 실제 이미지 품질 근거가
  아니라는 경고를 명시한다.
- Raw/Enhanced generation은 model, aspect ratio, sample count가 같고 case id 정렬 기준으로
  제출 순서를 번갈아 적용한다.
- 세 metric adapter와 tie threshold를 각각 기록하며 종합 점수를 만들지 않는다. 집계 전에
  프롬프트별 arm 평균과 paired delta를 `case_statistics.jsonl`에 보존한다.
- 모든 이미지별 score는 해당 case의 동일한 original/reviewed canonical prompt hash를
  사용해야 한다.
- 실행 프롬프트 hash는 공백을 포함한 정확한 UTF-8 텍스트의 SHA-256이다.
- Asset 경로는 run 디렉터리 기준 상대경로만 허용하고 absolute path와 `..` traversal을
  거부한다.
- 완료 arm은 요청한 sample 수만큼 job/asset/hash를 가져야 한다.
- 별도 versioned `cleanup.json`은 `delete_backend`/`keep_backend` 정책과 job별
  `retained`/`deleted` 상태를 기록한다. 이미 병합된 v1 arm schema는 변경하지 않는다.
- 중복 case checkpoint와 서로 맞지 않는 run id, target model, arm 순서를 거부한다.
- 현재 API는 template source digest를 반환하지 않으므로 `template_sha256`은 명시적으로
  제출한 template version marker의 hash다. 실제 template digest API가 생기면 source
  digest로 교체한다.
