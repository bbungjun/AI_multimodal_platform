# Phase 2 Final Handoff

Date: 2026-05-27

이 문서는 KRAFTON take-home assignment 복구 작업의 현재 인수인계 상태를 한국어로
정리한 최종 확인용 메모입니다. 새 기능 개발 기록이 아니라, 남아 있는 코드/문서/
pre_context/memories를 근거로 어디까지 복구했고 무엇을 의도적으로 하지 않았는지
정리합니다.

## 한 줄 결론

현재 복구 상태는 비용 없는 `AI_PROVIDER=mock` 로컬 검증 기준으로 닫을 수 있습니다.
비용이 발생하는 실제 Vertex/Gemini/Imagen/Veo live QA는 실행하지 않기로 결정했으며,
`AI_PROVIDER=vertex` 경로는 코드 경계만 보존된 미검증 리스크로 남깁니다.

2026-05-28 후속 복구로 backend mock/fake-only 계약 테스트가 더 보강되었고,
최신 backend full pytest 기준은 `AI_PROVIDER=mock python -m pytest` -> `157 passed`
입니다. 이 후속 검증도 실제 Vertex/Gemini/Imagen/Veo 호출 없이 수행되었습니다.

## 현재 Git 기준

- Branch: `main`
- Remote: `origin` -> `https://github.com/bbungjun/AI_mult_modal.git`
- 이 메모 작성 전 HEAD: `167b3d2 docs: record no live provider qa decision`
- 이 메모 작성 시작 시 `git status --short --branch`: `## main...origin/main`
- 이 메모 작성 시작 시 staged 파일: 없음

## 복구 완료 범위

복구 완료로 보는 범위:

- FastAPI backend import/API skeleton
- Vertex service boundary
  - Imagen
  - Veo
  - public error mapping
  - `google-genai` / `genai.Client(vertexai=True, ...)` 경계
- local no-cost provider path
  - `AI_PROVIDER=mock`
  - deterministic T2I PNG
  - deterministic prompt enhancement draft
  - mock provider readiness
- backend mock/fake-only test suite
- React/Vite/TypeScript frontend lint/build
- Docker Compose mock smoke
- browser smoke
  - `/generate`
  - `/history`
  - `/jobs/{job_id}` image result preview
- repo hygiene
  - 실제 `.env` 미커밋
  - service-account JSON 미커밋
  - credential/API key/private secret 미커밋
  - generated runtime media 미커밋

## 확인된 검증 결과

최근 Phase 1 기준으로 기록된 검증 결과:

```bash
cd backend
python -m pytest
python -m compileall app
python -c "import app.main; print('import ok')"

cd ../frontend
npm run lint
npm run build

cd ..
docker compose --env-file .env.example config --quiet
```

결과:

- `python -m pytest`: `65 passed`
- `python -m compileall app`: 통과
- `python -c "import app.main; print('import ok')"`: `import ok`
- `npm run lint`: 통과
- `npm run build`: 통과
- `docker compose --env-file .env.example config --quiet`: 통과

Compose mock smoke에서 확인된 흐름:

- db healthy
- backend reachable
- frontend reachable
- backend direct `/api/health` -> `200`
- frontend proxy `/api/health` -> `200`
- frontend proxy `/api/generations` -> `200`
- mock T2I job 생성 및 완료
- 생성된 PNG asset을 `/files/...` 경로로 읽기 성공
- browser smoke에서 generate/history/job detail 확인

2026-05-28 이후 추가로 고정된 비용 없는 계약:

- rate limiter/retry
- Vertex auth/permission/quota/transient error mapping
- Veo safety/output failure classification
- generation/pipeline model and option validation
- `/files` range/header behavior
- T2I multi-image gallery and per-image I2V handoff
- Prompt Enhancement validation/linkage guards
- ERD SQLAlchemy relationship contract
- runner orphan sweep / resumable polling guard / startup ordering
- `state_history` `{state, at, detail}` payload detail contract

## Mock 경로와 Vertex 경로의 차이

`AI_PROVIDER=mock`:

- 로컬 복구와 자동화 테스트용 경로입니다.
- credential 없이 동작해야 합니다.
- Vertex/Gemini/Imagen/Veo 실제 호출을 하면 안 됩니다.
- 실제 AI 품질을 검증하지 않고, API/DB/job runner/storage/frontend preview 흐름을
  deterministic output으로 검증합니다.

`AI_PROVIDER=vertex`:

- 최종 제출 당시의 실제 provider 경로입니다.
- `google-genai`와 `genai.Client(vertexai=True, ...)` 경계를 유지합니다.
- Gemini 2.5 Flash, Imagen 4, Veo 3 실제 호출 대상입니다.
- GCP project, location, service-account JSON path, billing/quota/model access가 필요합니다.
- 이번 복구에서는 비용 문제 때문에 실제 live QA를 실행하지 않았습니다.

## 비용 발생 검수 결정

사용자 결정:

- 비용이 발생하는 검수는 하지 않습니다.
- 따라서 실제 Vertex/Gemini/Imagen/Veo 호출은 이번 복구 범위에서 제외합니다.
- `memories/recovery/phase2-vertex-live-qa-runbook.md`는 실행 기록이 아니라,
  나중에 비용 승인을 받고 live QA를 해야 할 경우의 참고 절차로만 보관합니다.

이 결정 때문에 남는 리스크:

- 실제 GCP credential로 provider client가 준비되는지 미확인
- 실제 Gemini prompt enhancement 품질/응답 shape 미확인
- 실제 Imagen image generation 품질/응답 shape 미확인
- 실제 Veo T2V/I2V operation submit/poll/result shape 미확인
- 실제 provider quota/rate limit/region availability 미확인

## 안전 상태

확인된 안전 상태:

- 실제 Vertex/Gemini/Imagen/Veo 호출 없음
- 실제 `.env` commit 없음
- service-account JSON commit 없음
- API key/private credential 출력 또는 commit 없음
- generated media/runtime asset commit 없음
- Redis, Celery, GCS, 새 DB, 새 frontend framework 도입 없음

계속 지켜야 할 규칙:

- `.env`, service-account JSON, credential 파일은 repo에 넣지 않습니다.
- credential 내용은 문서/로그/commit에 적지 않습니다.
- 테스트는 계속 mock/fake-only로 유지합니다.
- 유료 provider 호출은 명시적인 비용 승인 없이는 실행하지 않습니다.

## 다음 인수인계자에게

현재 상태에서 가장 안전한 다음 행동:

1. 이 메모와 `phase1-submission-summary.md`를 검토합니다.
2. 비용 없는 범위에서는 `AI_PROVIDER=mock` 기준 검증만 반복합니다.
3. 유료 live QA가 필요해지면 먼저 사용자에게 비용 승인 여부를 다시 확인합니다.
4. live QA를 하지 않는다면, `AI_PROVIDER=vertex` 미검증 리스크를 그대로 명시하고
   복구 작업을 닫습니다.

현재 추천은 복구 작업을 여기서 닫는 것입니다. 이유는 과제 복구 목적상 mock/local
흐름, API contract, frontend build, compose smoke, repo hygiene은 확인되었고, 남은
검증은 비용이 발생하는 외부 provider 검증뿐이기 때문입니다.
