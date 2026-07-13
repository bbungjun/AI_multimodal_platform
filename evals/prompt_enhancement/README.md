# 프롬프트 향상 평가 패키지

이 디렉터리는 CreativeOps Studio의 원본 프롬프트(`raw`)와 검토 후 수락한 향상
프롬프트(`enhanced`)를 paired benchmark로 비교하기 위한 독립 평가 경계다. Production
backend/worker 이미지나 데이터베이스에 평가 전용 상태와 무거운 scorer 의존성을
추가하지 않는다.

현재 Issue #61 범위는 생성이나 점수 계산이 아니라 버전이 있는 파일 계약이다.
`schemas.py`는 다음 artifact를 검증한다.

- `benchmark.v1.jsonl`: 언어, category, 원본/평가 프롬프트, 대상 모델과 생성 파라미터
- `manifest.json`: Git/provider/model/scorer 버전, lifecycle, paired checkpoint와 artifact hash
- `pairs.jsonl`: Raw/Enhanced 실행 프롬프트, job, asset, 실패와 retry 정보
- `scores.jsonl`: 이미지별 VQAScore, ImageReward, TIFA 결과
- `summary.json`: metric별 paired 통계와 slice 집계

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

## 로컬 artifact 경계

실행 결과는 아래 구조를 사용한다.

```text
runs/<run-id>/
  manifest.json
  pairs.jsonl
  images/
  scores.jsonl
  summary.json
  report.md
```

`runs/`와 `.model-cache/`는 Git에서 제외된다. 생성 이미지, checkpoint, credential,
token, 개인 PC absolute path는 커밋하지 않는다. 검토된 집계 결과를 보존해야 한다면 로컬
run 디렉터리를 그대로 추가하지 말고 별도의 versioned evidence 위치로 필요한 요약만 복사해
검토한다.

## 계약상 안전장치

- Mock provider run은 반드시 `evidence_kind=synthetic`이다.
- 세 metric adapter와 tie threshold를 각각 기록하며 종합 점수를 만들지 않는다.
- 실행 프롬프트 hash는 공백을 포함한 정확한 UTF-8 텍스트의 SHA-256이다.
- Asset 경로는 run 디렉터리 기준 상대경로만 허용하고 absolute path와 `..` traversal을
  거부한다.
- 완료 arm은 요청한 sample 수만큼 job/asset/hash를 가져야 한다.
- 중복 case checkpoint와 서로 맞지 않는 run id, target model, arm 순서를 거부한다.
