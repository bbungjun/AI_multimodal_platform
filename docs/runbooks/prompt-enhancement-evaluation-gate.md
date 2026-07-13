# Prompt Enhancement 평가 Go/No-Go Runbook

이 runbook은 prompt enhancement의 실제 품질 평가나 유료 Vertex 파일럿 전에 반드시
통과해야 하는 비용 없는 mock gate를 정의한다. Mock 결과는 evaluation orchestration의
증거이며 이미지 품질 증거가 아니다.

## 범위

Gate는 다음 경계를 한 번에 검증한다.

- 검토된 benchmark snapshot과 run provenance 생성
- Gemini mock prompt enhancement
- 동일 parameter의 Raw/Enhanced Imagen mock generation
- 세 개의 deterministic synthetic metric
- case 단위 paired delta와 bootstrap 통계
- summary/report 및 artifact hash
- 완료 run 재실행 시 중복 generation 방지
- 명시적 mock provider failure와 cleanup 보존
- run/media/model-cache Git hygiene

실제 Gemini, Imagen, Veo, VQAScore, ImageReward, TIFA 모델은 호출하거나 다운로드하지 않는다.

## 사전 조건

- Issue #60~#63 변경이 `main`에 반영되어 있어야 한다.
- Docker와 Compose를 사용할 수 있어야 한다.
- repository root의 `.env.example`이 `AI_PROVIDER=mock`이어야 한다.
- process environment도 명시적으로 `AI_PROVIDER=mock`이어야 한다.
- `.env`, ADC, service-account JSON 또는 API key는 이 절차에 전달하지 않는다.

## 실행

Repository root에서 다음을 실행한다.

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python run_mock_e2e.py --compose --run-id mock-gate-YYYYMMDD-001
```

이미 같은 checkout의 mock Compose 서비스가 준비되어 있으면 `--compose`를 생략할 수 있다.
중단되면 같은 Git SHA, dirty-worktree 상태, benchmark와 run id로 명령을 다시 실행한다.
Submitted job checkpoint를 polling하고 완료된 job과 artifact는 재사용한다.

## 통과 조건

명령이 exit code `0`과 다음 형태의 마지막 줄을 출력해야 한다.

```text
MOCK EVALUATION GATE PASSED — SYNTHETIC EVIDENCE ONLY. ...
```

성공 run에서 확인할 조건:

- `manifest.json.lifecycle == completed`
- 모든 case의 Raw/Enhanced arm이 `completed`
- `scores.jsonl`에 이미지마다 VQAScore, ImageReward, TIFA가 각각 존재
- `case_statistics.jsonl`에 case/metric별 arm 평균과 paired delta가 존재
- `summary.json`에 세 metric, bootstrap 95% CI, W/T/L, 언어/category slice가 존재
- `report.md`에 synthetic evidence 경고가 존재
- manifest의 benchmark, cleanup, pair, score, case statistics, summary, report hash가 일치
- 내부 resume 검증 전후 job id, asset hash, artifact hash와 report가 동일

`<run-id>-failure`에서 확인할 조건:

- `manifest.json.lifecycle == failed`
- `last_error.code == mock_provider_failure`
- 실패 arm, retry count와 cleanup state가 보존
- `scores.jsonl`, `case_statistics.jsonl`, `summary.json`, `report.md`가 생성되지 않음
- 기본 cleanup 정책에서는 backend generation/asset이 삭제됨

두 run 디렉터리와 `.model-cache`는 Git status와 staged 목록에 나타나면 안 된다.

## 실패 시 처리

- Health가 `mock_provider`/`credentials=not_required`가 아니면 즉시 중단하고 Compose env를
  고친다. Vertex mode로 우회하지 않는다.
- `submitted` checkpoint에서 중단됐으면 같은 run id로 재실행한다. 새 run을 먼저 만들지
  않는다.
- Manifest incompatibility가 나오면 Git SHA, dirty 상태, benchmark hash 또는 enhancer
  설정이 바뀐 것이다. 기존 artifact를 덮어쓰지 말고 원인을 기록한 뒤 새 run id를 사용한다.
- Artifact hash가 다르면 해당 run을 품질 근거로 사용하지 않는다. 로컬 파일 변경 원인을
  확인하고 fresh run으로 재검증한다.
- Controlled failure가 성공해버리거나 다른 code로 실패하면 mock failure contract 회귀로
  취급한다.

## 유료 Vertex Go/No-Go

다음 항목이 모두 충족되어야 Vertex 파일럿을 검토할 수 있다.

- [x] 정확한 execution prompt와 enhancement provenance가 저장된다.
- [x] versioned benchmark/run/artifact schema가 검증된다.
- [x] matched Raw/Enhanced mock generation과 resume가 검증된다.
- [x] 동일 canonical prompt를 사용하는 세 mock metric과 paired 통계가 검증된다.
- [x] 이 mock end-to-end gate와 controlled failure가 통과한다.
- [x] generated media, run artifact와 evaluator cache가 Git에서 제외된다.
- [x] Issue #65의 실제 offline scorer revision, model cache, TIFA QA와 한계가 검증된다.
- [x] scorer별 tie threshold가 실제 score noise 기준으로 고정된다.
- [ ] 사용자가 Vertex 파일럿의 최대 case/image 수와 예상 비용을 명시적으로 승인한다.
- [ ] 개인 GCP account/project guard와 Vertex readiness를 실행 직전에 확인한다.

하나라도 미충족이면 결론은 **No-Go**다. Mock gate 통과만으로 실제 Vertex 요청을 시작하지
않는다. 현재 승인 전 파일럿 상한 후보는 20 case, 80 image이며 자동 실행하지 않는다.
실제 scorer 재현 절차와 CPU/GPU 한계는
`docs/runbooks/prompt-enhancement-offline-scorers.md`를 따른다.

## 종료 검증

```powershell
cd ../..
git status --short --branch
git diff --cached --name-only
git check-ignore evals/prompt_enhancement/runs/mock-gate-YYYYMMDD-001/manifest.json
git check-ignore evals/prompt_enhancement/.model-cache/.probe
```

Run artifact는 ignored local evidence로 유지한다. 검토된 실제 결과를 보존할 때만 별도
versioned evidence 위치로 필요한 요약을 복사하고, synthetic/real evidence를 명확히 구분한다.
