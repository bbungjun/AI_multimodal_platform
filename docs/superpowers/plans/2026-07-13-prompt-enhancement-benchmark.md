# 프롬프트 향상 벤치마크 및 Mock 우선 평가 계획

**상태:** GitHub Issue
[#59](https://github.com/bbungjun/AI_multimodal_platform/issues/59)에서 계획됨

**구현 대기열:**
[#60](https://github.com/bbungjun/AI_multimodal_platform/issues/60)부터
[#66](https://github.com/bbungjun/AI_multimodal_platform/issues/66)까지

## 목적

CreativeOps Studio는 Gemini 프롬프트 향상 결과를 생성하고, 사용자가 이를 검토·편집·수락할
수 있다. 하지만 현재 제품에는 수락한 프롬프트가 원본 프롬프트보다 실제 이미지 품질을
개선하는지 측정하는 장치가 없다. 텍스트 응답 형식, provider 안정성, 이미지 생성 성공 여부는
필요한 운영 검증이지만 프롬프트 향상의 제품 가치를 증명하지는 못한다.

이 계획은 사용자의 원본 프롬프트로 만든 이미지와 수락된 향상 프롬프트로 만든 이미지를
재현 가능한 방식으로 비교하는 T2I 벤치마크를 추가한다. 첫 번째 완료 경계는 완전히
deterministic한 `AI_PROVIDER=mock` 흐름이다. 이 계획 자체는 실제 Gemini 또는 Imagen 호출을
허용하지 않는다. 비용이 발생하는 Vertex 파일럿은 mock gate를 통과하고 사용자가 명시적으로
승인한 뒤에만 시작하는 별도 마지막 Task다.

## 핵심 결정

- 첫 평가는 T2I만 대상으로 한다. T2V와 I2V에는 시간축과 소스 이미지 보존을 평가하는 별도
  지표가 필요하므로 이번 범위에서 제외한다.
- 비교군은 `raw`와 `enhanced` 두 개의 paired arm으로 고정한다.
- 두 arm 모두 동일한 사용자의 원본 의도를 기준으로 평가한다. 향상 프롬프트를 Enhanced arm의
  정답으로 사용하지 않는다.
- VQAScore, ImageReward, TIFA를 각각 보고한다. 근거 없는 종합 점수는 만들지 않는다.
- 개별 이미지가 아니라 하나의 벤치마크 프롬프트를 통계 단위로 사용한다.
- 평가 harness와 무거운 scorer 의존성은 production backend/worker 의존성과 분리한다.
- 기존 HTTP prompt enhancement, generation, job, asset, storage 계약을 재사용해 실제 제품
  경로를 검증한다.
- 생성 이미지, 모델 cache, run artifact는 로컬 ignored 파일로 유지한다. 버전이 있는 schema,
  benchmark 정의, 검토된 집계 보고서만 커밋할 수 있다.
- Mock 점수는 orchestration 검증용이다. 항상 synthetic임을 표시하고 이미지 품질 근거로
  사용하지 않는다.

## 필수 실행 프롬프트 계약

ADR 0004는 generation payload로 제출된 프롬프트가 source of truth라고 규정한다. 런타임이 이
계약을 지키기 전에는 벤치마크 결과를 신뢰할 수 없다.

현재 수락 흐름에서는 사용자가 편집한 `prompt`와 기존 `enhancement_id`가 함께 전송될 수 있다.
백엔드는 저장된 enhancement component에서 숨겨진 provider prompt를 가져와 실행 시 더 높은
우선순위로 사용할 수 있다. 따라서 사용자가 확인한 텍스트와 Imagen에 실제 전달한 텍스트가
달라질 위험이 있다.

Issue #60은 paired 평가 전에 다음 불변조건을 확립해야 한다.

1. `GenerationCreate.prompt`가 generation provider에 전달되는 정확한 텍스트다.
2. `enhancement_id`는 provenance만 기록하며 제출된 프롬프트를 몰래 덮어쓰지 않는다.
3. `Job.prompt`는 감사 가능한 실제 실행 프롬프트로 유지된다.
4. `PromptEnhancement.original`, `PromptEnhancement.enhanced`, enhancer 모델, template 버전,
   target mode/model, creativity preset은 enhancement provenance로 유지된다.
5. 각 evaluation arm은 실제 실행 프롬프트의 SHA-256 hash를 기록한다.
6. 이후 provider 전용 번역이 필요해지면 사용자가 확인하고 명시적으로 제출 또는 수락할 수
   있어야 한다. 오래된 숨은 rewrite로 실행해서는 안 된다.

이 계약을 적용한 요청은 다음처럼 명확해진다.

```text
raw arm:
  prompt = original_prompt
  enhancement_id = null

enhanced arm:
  prompt = accepted_enhanced_prompt
  enhancement_id = persisted enhancement id
```

## 평가 지표 계약

벤치마크 case `i`에서 `p_i`는 사용자의 원본 프롬프트 또는 검토 후 고정한 canonical 평가
프롬프트다. `R_i`는 Raw 이미지 집합, `E_i`는 Enhanced 이미지 집합이다.

```text
VQA delta(i) = mean(VQAScore(p_i, E_i))
             - mean(VQAScore(p_i, R_i))

Reward delta(i) = mean(ImageReward(p_i, E_i))
                - mean(ImageReward(p_i, R_i))

TIFA delta(i) = mean(TIFA(p_i, E_i))
              - mean(TIFA(p_i, R_i))
```

두 arm의 reference prompt는 같아야 한다. Enhanced arm을 향상 프롬프트로 평가하면 enhancer가
임의로 추가한 세부사항까지 정답으로 인정하게 되므로 사용자의 원래 의도 보존을 측정할 수 없다.

| 지표 | 역할 | 해석 |
| --- | --- | --- |
| VQAScore | 주 정합성 신호 | 이미지가 원본 요청 전체를 묘사하는가 |
| ImageReward | 학습된 선호 신호 | 결과가 시각적으로 더 선호되거나 완성도가 높은가 |
| TIFA | 세부 충실도 진단 | 객체·속성·개수·관계 중 무엇을 충족했는가 |

FID, SSIM, LPIPS, 단순 pixel 차이는 이번 작업의 acceptance metric이 아니다. 이 값들은 분포나
이미지 차이를 측정할 수 있지만 어느 쪽이 사용자의 요청을 더 잘 만족하는지는 판단하지 못한다.

## 평가 패키지 경계

초기 harness는 production 코드와 분리된 영역에 둔다.

```text
evals/prompt_enhancement/
  README.md
  pyproject.toml
  schemas.py
  benchmark.v1.jsonl
  generate_pairs.py
  score_pairs.py
  summarize.py
  fixtures/
```

이 경계는 PyTorch, scorer checkpoint, evaluator 전용 라이브러리가 `backend/pyproject.toml`과
production backend/worker 이미지에 들어가는 것을 막는다. Runner는 기존 애플리케이션 HTTP
API를 호출하며 DB session을 직접 import하거나 outbox, dispatcher, state machine, storage
helper를 우회하지 않는다.

첫 구현에서는 evaluation 상태를 새 DB table이 아니라 버전이 있는 로컬 artifact에 기록한다.
평가를 온라인 제품 기능으로 이동하거나 새 queue/DB state machine을 추가하려면 이후 제품 결정과
ADR이 필요하다.

## 버전이 있는 데이터 계약

### Benchmark case

각 JSONL record는 최소한 다음 필드를 가진다.

```json
{
  "schema_version": 1,
  "case_id": "en-short-subject-001",
  "source": "creativeops-benchmark-v1",
  "language": "en",
  "category": "short_subject",
  "original_prompt": "a small blue cup on a desk",
  "evaluation_prompt": "a small blue cup on a desk",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced",
  "aspect_ratio": "1:1",
  "samples_per_arm": 2,
  "enabled": true
}
```

공개 scorer 모델의 한국어 성능이 동등하지 않을 수 있으므로 한국어 case에는 검토된
`evaluation_prompt_en`을 추가할 수 있다. 원본 한국어 프롬프트, canonical 영어 평가 프롬프트,
검토 상태를 모두 보존하고 한국어 결과를 영어 결과에 조용히 섞지 않고 별도 보고한다.

### Run manifest

Run manifest에는 다음 정보를 기록한다.

- schema version과 run id
- Git commit SHA와 dirty worktree 여부
- provider mode
- benchmark 파일 hash
- enhancer 모델과 enhancement template 버전/hash
- generation 모델과 실제 적용된 generation parameter
- metric adapter 이름, 모델 revision, 설정
- 시작/완료 시각과 현재 lifecycle 상태
- Raw/Enhanced 요청 순서 정책
- prompt hash, job id, asset id, file hash, 실패와 retry 횟수
- mock/real evidence 구분
- bootstrap seed, resample 횟수, metric별 tie threshold

### 로컬 artifact 배치

```text
evals/prompt_enhancement/runs/<run-id>/
  manifest.json
  pairs.jsonl
  images/
  scores.jsonl
  summary.json
  report.md
```

`runs/` 전체와 evaluator model cache는 ignore한다. 생성 media, credential, token, 개인 로컬
경로가 없는지 검토한 집계 보고서만 별도 versioned evidence 위치에 복사할 수 있다.

## 평가 lifecycle

로컬 evaluation manifest는 application job 상태와 분리된 orchestration 상태를 추적한다. 개별
generation job은 계속 기존 application state machine을 사용한다.

```text
planned
  -> enhancing
  -> generating_raw
  -> generating_enhanced
  -> collecting_assets
  -> scoring
  -> summarizing
  -> completed
```

각 단계는 통제된 public error code와 resumable checkpoint를 남기고 `failed`로 전환할 수 있다.
같은 run id를 다시 실행하면 완료한 arm/job 기록을 재사용하고 generation job을 중복 생성하지
않아야 한다.

시간대별 provider 상태가 항상 같은 arm에 유리하게 작용하지 않도록 `case_id`에 따라
Raw/Enhanced 제출 순서를 번갈아 적용한다.

## 벤치마크 구성

### Mock fixture

4~6개의 deterministic case로 다음을 포함한다.

- 영어와 한국어
- 짧은 프롬프트와 이미 상세한 프롬프트
- 다중 객체, 개수 또는 공간 관계 프롬프트
- 통제된 enhancement 또는 generation 실패 1건

Fixture는 상태 흐름과 보고서 schema 검증에만 사용한다.

### Vertex 파일럿

Mock gate 통과와 명시적 승인 후 Issue #66은 다음 한도로 제한한다.

- 벤치마크 case 20개
- case별 Raw 2장과 Enhanced 2장
- prompt enhancement 요청 최대 20회
- 생성 이미지 최대 80장
- `balanced` creativity preset
- 승인된 Imagen 모델 1개와 aspect ratio 1개

요청 수, 실패 수, latency, 비용과 관련된 operation 수를 기록한다. 파일럿 완료가 full benchmark
자동 시작을 의미하지 않는다.

### Full benchmark 후보

이후 후보 benchmark는 100개 프롬프트로 구성한다.

- 한국어 50개, 영어 50개
- 짧은 subject, 상세 subject, 다중 객체, 개수/공간, style/lighting category 균형
- case별 Raw 4장과 Enhanced 4장

최대 800장의 이미지가 생성되므로 파일럿 보고서를 검토한 뒤 별도 결정을 내려야 한다.

## 통계 프로토콜

1. 생성 이미지마다 세 지표를 계산한다.
2. case와 arm 안에서 이미지 점수 평균을 구한다.
3. case마다 Enhanced 평균에서 Raw 평균을 뺀 paired delta를 계산한다.
4. 같은 프롬프트의 상관된 이미지를 독립 표본으로 취급하지 않도록 개별 이미지가 아닌 case
   delta를 집계한다.
5. 평균 delta, 중앙값 delta, paired bootstrap 95% 신뢰구간을 보고한다. Bootstrap seed와
   iteration 횟수는 run manifest에 기록한다.
6. 비용 발생 실행 전에 기록한 scorer별 epsilon으로 win/tie/loss를 계산한다. Task #65에서
   반복 score noise를 통해 epsilon을 보정하며 Vertex 결과를 본 뒤 선택하지 않는다.
7. 언어, 프롬프트 category, 프롬프트 구체성별 결과를 분리한다.
8. 누락되거나 실패한 case를 별도로 보고하고 조용히 제외하지 않는다.

종합 점수는 만들지 않는다. 강한 제품 근거는 VQAScore와 ImageReward가 개선되면서 TIFA가
유의미하게 악화되지 않는 결과다. 일부 category에서만 효과가 있으면 UI도 보편적인 품질 향상을
주장하지 않고 적용 조건을 좁혀야 한다.

## 단계별 Task

### Task 1 — 실행 프롬프트 source-of-truth와 provenance

**Issue:** [#60](https://github.com/bbungjun/AI_multimodal_platform/issues/60)

**의존성:** 없음

**구현:**

- 사용자가 편집한 enhancement 수락 흐름의 regression test를 추가한다.
- 제출된 generation prompt가 정확한 provider input이 되도록 한다.
- 숨은 override 없이 enhancement 연결을 provenance로 보존한다.
- benchmark에 필요한 enhancer/template/model metadata를 기록한다.

**완료 기준:** API와 job handler test가 수락·편집한 prompt가 mock mode의 실제 실행 prompt임을
증명한다.

### Task 2 — Benchmark와 artifact schema

**Issue:** [#61](https://github.com/bbungjun/AI_multimodal_platform/issues/61)

**의존성:** Task 1

**구현:**

- 분리된 evaluation package 골격을 만든다.
- benchmark, run, arm, asset, score, summary schema를 검증 가능하게 정의한다.
- 호환되지 않는 schema version을 거부하고 manifest를 resumable하게 쓴다.
- run artifact와 model cache ignore 규칙을 추가한다.

**완료 기준:** 정상 fixture가 round-trip하고 잘못되거나 호환되지 않는 manifest가 구체적인
오류와 함께 실패한다.

### Task 3 — Mock paired-generation runner

**Issue:** [#62](https://github.com/bbungjun/AI_multimodal_platform/issues/62)

**의존성:** Task 1, Task 2

**구현:**

- `AI_PROVIDER=mock`을 강제한다.
- prompt enhancement와 generation HTTP API를 호출한다.
- parameter가 일치하는 Raw/Enhanced job을 만들고 terminal 상태까지 polling한다.
- public file 경계로 asset을 받아 hash를 기록한다.
- 완료 case를 중복 job 없이 resume한다.
- Raw/Enhanced 제출 순서를 번갈아 적용한다.

**완료 기준:** Vertex client를 만들지 않고 fixture run이 완전한 paired manifest와 로컬 이미지
artifact를 생성한다.

### Task 4 — Mock metric adapter와 통계

**Issue:** [#63](https://github.com/bbungjun/AI_multimodal_platform/issues/63)

**의존성:** Task 2, Task 3

**구현:**

- 공통 scorer adapter 계약을 정의한다.
- deterministic synthetic VQAScore, ImageReward, TIFA adapter를 추가한다.
- 두 arm 모두 original/canonical prompt로 평가하도록 강제한다.
- 이미지·case·전체·slice별 통계를 계산한다.
- `summary.json`과 `report.md`를 만든다.

**완료 기준:** 고정 fixture 입력이 byte-stable한 통계 결과를 만들고 모든 synthetic score가 mock
evidence로 명확히 표시된다.

### Task 5 — Mock end-to-end gate

**Issue:** [#64](https://github.com/bbungjun/AI_multimodal_platform/issues/64)

**의존성:** Task 1~4

**구현:**

- benchmark manifest부터 최종 report까지 실행하는 mock-only smoke 명령을 추가한다.
- 중단 후 resume와 통제된 실패 1건을 검증한다.
- provider credential과 remote scorer가 필요하지 않음을 증명한다.
- 유료 실행 go/no-go checklist를 문서화한다.
- 변경 범위에 맞는 repository quality gate를 실행한다.

**완료 기준:** 전체 흐름이 fresh mock mode에서 통과하고 아래 mock gate 항목이 모두 충족된다.

### Task 6 — 실제 offline scorer adapter

**Issue:** [#65](https://github.com/bbungjun/AI_multimodal_platform/issues/65)

**의존성:** Task 4, Task 5

**구현:**

- VQAScore, ImageReward, TIFA 모델/code revision을 pin한다.
- 의존성을 production application 이미지와 분리한다.
- benchmark용 TIFA question-answer set을 고정하고 검토한다.
- 한국어 canonical prompt를 검증하고 별도 보고한다.
- Vertex 파일럿 전에 scorer별 tie threshold를 보정한다.

**완료 기준:** Vertex를 호출하지 않고 로컬 fixture 이미지를 세 실제 adapter가 모두 평가하며
모델 revision과 한계가 기록된다.

### Task 7 — 비용 제한 Vertex 파일럿

**Issue:** [#66](https://github.com/bbungjun/AI_multimodal_platform/issues/66)

**의존성:** Task 5, Task 6, 사용자의 명시적 승인

**구현:**

- 개인 GCP account/project guard와 Vertex readiness를 검증한다.
- 승인된 최대 20 case, 80 image 파일럿만 실행한다.
- 로컬 scorer로 평가하고 paired report를 생성한다.
- provider failure, request 수, latency, 비용 관련 count를 기록한다.
- full benchmark 또는 제품 통합이 타당한지 판단한다.

**완료 기준:** 보고서가 실제 Vertex 근거와 mock 흐름 검증을 구분하고 진행·축소·수정·중단 중
하나를 권고한다.

## Mock-to-Vertex Go/No-Go Gate

다음 항목이 모두 충족되기 전에는 실제 prompt enhancement 또는 Imagen 요청을 실행하지 않는다.

- [ ] Issue #60이 정확한 execution prompt 계약을 증명한다.
- [ ] 버전이 있는 benchmark와 run schema가 검증된다.
- [ ] Raw/Enhanced mock job이 동일 parameter로 완료된다.
- [ ] Resume가 완료 작업을 중복 생성하지 않는다.
- [ ] 통제된 실패가 report를 손상시키지 않고 기록된다.
- [ ] 세 mock metric adapter 결과가 서로 분리되어 있다.
- [ ] 두 arm이 같은 original/canonical prompt로 평가된다.
- [ ] Paired 통계와 신뢰구간이 재현된다.
- [ ] Artifact와 model cache가 ignored 상태이며 staged되지 않는다.
- [ ] Test가 mock mode에서 Vertex client를 생성하지 않음을 증명한다.
- [ ] 실제 offline scorer revision과 한계가 기록된다.
- [ ] 사용자가 파일럿 요청·이미지 한도를 명시적으로 승인한다.

## 검증 전략

각 Task는 focused unit test부터 실행한다. Task 5에서는 전체 비용 없는 gate를 실행한다.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest

cd ..\frontend
npm run build

cd ..
docker compose --env-file .env.example config --quiet
python scripts/verify_local.py
git diff --check
git status --short --branch
git diff --cached --name-only
```

Issue #61~#64에서 evaluation 전용 검증 명령을 추가한다. 이 명령은 `.env` 사용을 거부하고,
mock mode를 요구하며, 환경변수 값을 출력하지 않아야 한다.

## 위험과 통제

- **Enhancer 자기평가:** enhancer 모델이 reference prompt를 만들거나 자기 rewrite를 직접
  평가하지 못하게 한다. 원본 또는 고정된 prompt가 reference다.
- **한국어 scorer 편향:** 검토된 canonical 평가 텍스트를 사용하고 한국어 결과를 별도 slice로
  보고한다.
- **Metric gaming:** 종합 점수를 만들지 않고 결과를 본 뒤 threshold를 바꾸지 않는다.
- **생성 무작위성:** arm마다 여러 이미지를 만들고 case 단위로 paired 집계한다. Provider가
  명시적으로 지원할 때만 matched seed를 사용한다.
- **Production image 비대화:** 무거운 scorer 의존성은 evaluation package에만 둔다.
- **비용 초과:** Mock gate 뒤에 hard cap이 있는 파일럿을 두며 full benchmark는 별도 결정한다.
- **거짓 mock 근거:** Mock report에 synthetic evidence 표시를 강제하고 제품 품질 근거로
  인정하지 않는다.

## 연구 참고자료

- [VQAScore와 GenAI-Bench](https://arxiv.org/abs/2406.13743)
- [TIFA](https://openaccess.thecvf.com/content/ICCV2023/papers/Hu_TIFA_Accurate_and_Interpretable_Text-to-Image_Faithfulness_Evaluation_with_Question_Answering_ICCV_2023_paper.pdf)
- [ImageReward](https://arxiv.org/abs/2304.05977)
- [GenEval](https://arxiv.org/abs/2310.11513)
- [Promptist](https://arxiv.org/abs/2212.09611)
