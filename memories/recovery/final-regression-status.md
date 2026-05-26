# Final Regression Status

Date: 2026-05-27

이 문서는 KRAFTON take-home assignment 복구 작업의 비용 없는 최종 regression 확인
결과입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 실행하지 않았고,
`AI_PROVIDER=mock` 또는 config-only 경로로만 검증했습니다.

## 기준 상태

- 검증 시작 전 HEAD: `6bd0a2f docs: add phase2 final handoff`
- 검증 시작 전 `git status --short --branch`: `## main...origin/main`
- 검증 시작 전 staged 파일: 없음
- 검증 시작 전 Compose project container: 없음

## 실행한 명령과 결과

Backend:

```bash
cd backend
$env:AI_PROVIDER='mock'; python -m pytest
$env:AI_PROVIDER='mock'; python -m compileall app
$env:AI_PROVIDER='mock'; python -c "import app.main; print('import ok')"
```

결과:

- `python -m pytest`: 최초 최종 regression 기준 `65 passed in 1.85s`
- `python -m compileall app`: exit code `0`
- `python -c "import app.main; print('import ok')"`: `import ok`

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

결과:

- `npm run lint`: exit code `0`
- `npm run build`: exit code `0`
- Vite production build 완료
  - transformed modules: `90`
  - output includes `dist/index.html`, CSS bundle, JS bundle

Docker Compose:

```bash
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example ps
```

결과:

- `docker compose --env-file .env.example config --quiet`: exit code `0`
- `docker compose --env-file .env.example ps`: 실행 중인 project container 없음

## 확인한 범위

이번 최종 regression으로 확인한 것:

- backend mock/fake-only test suite 통과
- backend Python compile 통과
- `app.main` import 가능
- frontend TypeScript check 통과
- frontend production build 통과
- Docker Compose `.env.example` 기준 config 유효
- Compose container가 남아 있지 않음

이번 최종 regression에서 의도적으로 확인하지 않은 것:

- 실제 Vertex provider 인증
- 실제 Gemini prompt enhancement 호출
- 실제 Imagen image generation 호출
- 실제 Veo T2V/I2V 호출
- 실제 GCP quota, billing, region/model availability

위 항목은 비용이 발생할 수 있으므로 이번 복구 범위에서 제외했습니다.

## 최종 판단

비용 없는 복구/검증 기준에서는 현재 workspace를 종료 가능한 상태로 봅니다.
남은 리스크는 `AI_PROVIDER=vertex` live path 미검증이며, 이 리스크는 비용 발생 검수를
하지 않기로 한 사용자 결정에 따라 문서화된 상태로 남깁니다.

다음 인수인계자는 기본적으로 `AI_PROVIDER=mock` 기준 검증만 반복하고, 실제 provider
검증이 필요할 때는 먼저 비용 승인 여부를 다시 확인해야 합니다.

## Mock Veo Pipeline Follow-Up

Pipeline UI 확인 중 mock mode에서 T2V/I2V job이 `vertex_credentials_invalid`로
실패하는 문제가 확인되었습니다.

원인:

- `AI_PROVIDER=mock`에서 T2I와 prompt enhancement는 mock provider를 사용했습니다.
- 그러나 Veo T2V/I2V 경로는 mock branch가 없어서 `get_vertex_client()`로 떨어졌고,
  dummy credential을 실제 Vertex credential처럼 읽으려다 실패했습니다.

조치:

- `backend/app/services/mock_media.py`에 deterministic mock MP4-like bytes 생성을
  추가했습니다.
- `backend/app/services/vertex/veo.py`에 mock `submit_video`,
  `poll_operation`, `poll_operation_name` 경로를 추가했습니다.
- `backend/tests/test_mock_provider.py`에 mock T2V/I2V가 Vertex client를 만들지 않는
  regression test를 추가했습니다.

추가 검증:

```bash
cd backend
$env:AI_PROVIDER='mock'; python -m pytest tests/test_mock_provider.py -q
$env:AI_PROVIDER='mock'; python -m pytest tests/test_mock_provider.py tests/test_job_handlers.py tests/test_pipeline_api.py tests/test_pipeline_link.py -q
$env:AI_PROVIDER='mock'; python -m pytest
$env:AI_PROVIDER='mock'; python -m compileall app
```

결과:

- `tests/test_mock_provider.py -q`: `5 passed`
- mock provider/job handler/pipeline 묶음: `23 passed`
- full backend pytest: `67 passed in 1.77s`
- compileall: exit code `0`

Compose mock API 확인:

- backend container 재시작 후 `http://127.0.0.1:5173/api/health`는
  `ready=true`, `vertex.status=mock_provider`
- 새 mock pipeline parent job:
  `e65c229f-d069-42b4-a89f-3e287e240c4e` -> `completed`, image asset 1개
- 새 mock pipeline child job:
  `a51aaa83-6e81-4371-9e48-74ed0dc1c597` -> `completed`, `video/mp4` asset 1개

주의:

- 이 mock video는 실제 Veo 품질 검증물이 아니라 로컬 flow 확인용 deterministic
  placeholder입니다.
- 실제 Vertex/Gemini/Imagen/Veo 호출은 여전히 수행하지 않았습니다.
