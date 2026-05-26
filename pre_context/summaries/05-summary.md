# krafton_assignment_05 요약

## 핵심 주제

Phase 8 Veo T2V/I2V 구현을 어떻게 쪼갤지 계획하고, 이후 Veo service adapter, T2V/I2V handler, polling timeout/failure, operation name 기반 resume, startup orphan sweep까지 mock 기반으로 진행한 긴 세션입니다. 복구 시 Veo 관련 backend 설계와 테스트 경계를 확인하는 핵심 근거입니다.

## 주요 키워드

- Phase 8, Veo 3, T2V, I2V
- `backend/app/services/vertex/veo.py`
- `submit_video`, `poll_operation`, `poll_operation_by_name`, `VeoTimeoutError`
- long-running operation, `vertex_operation_name`, polling resume
- `handle_t2v`, `handle_i2v`, `_run_veo_job`
- inline video bytes, no `output_gcs_uri`, no GCS
- mock Vertex, no real Veo in tests
- `test_veo_service.py`, `test_t2v_flow.py`, `test_i2v_flow.py`, `test_job_runner.py`

## 복구에 중요한 내용

- Phase 8은 한 번에 T2V/I2V/LRO/restart 복구를 묶지 않고, `Veo SDK 경계 -> T2V -> I2V -> polling resume/startup sweep` 순서로 나누는 방향이 정리되었습니다.
- 첫 단위는 `backend/app/services/vertex/veo.py`의 `submit_video()` happy path였습니다. API, handler, runner, storage를 열지 않고 service boundary와 fake client 테스트만 고정하는 TDD 단위였습니다.
- Veo service는 `google-genai` 단일 SDK를 사용해야 하며, 자동 테스트에서 실제 Veo 호출은 금지됩니다. I2V까지 고려해 `image_bytes=None` 형태의 확장 가능한 signature가 논의되었습니다.
- Veo는 Imagen과 달리 long-running operation입니다. job state는 `queued -> generating -> polling -> downloading -> completed` 흐름을 사용하고, operation name을 DB에 저장해야 서버 재시작 후 이어갈 수 있습니다.
- T2V/I2V handler는 공통 `_run_veo_job(job, image_bytes=None)` 형태가 제안되었고, source asset validation, missing/non-image source asset, submit failure, poll failure, timeout 경로가 각각 테스트 대상으로 정리되었습니다.
- 가장 중요한 위험은 `polling resume`이었습니다. polling 중 서버가 죽었을 때 `vertex_operation_name`만으로 이어갈 수 있어야 하므로, `poll_operation_by_name` 또는 동등한 경계가 필요하다는 결론이 남았습니다.
- Phase 8 후반에는 T2V resume, I2V resume, runner startup orphan sweep을 묶어 진행했습니다. startup 시 `polling + vertex_operation_name` job을 resume task로 스케줄하는 흐름이 핵심입니다.
- 전체 backend regression 결과로 `169 passed in 1.45s`가 기록되었습니다.
- actual Veo T2V manual QA는 시도했지만 credentials가 terminal reset 이후 없어 API까지 도달하지 못했습니다. 따라서 복구 기준은 mock 기반 완료이며, 실제 Veo QA는 별도 선택 작업입니다.

## 확인해야 할 구현 흐름

- Veo service adapter가 `submit_video`, `poll_operation`, `poll_operation_by_name` 경계를 제공하는지 확인합니다.
- T2V generation request가 API에서 허용되고, handler가 submit -> polling -> downloading -> completed 흐름을 처리하는지 확인합니다.
- T2V submit failure, poll failure, polling timeout이 job failed/public error로 안전하게 기록되는지 확인합니다.
- I2V generation request가 source asset을 요구하고, missing/non-image source asset을 실행 단계에서 안전하게 막는지 확인합니다.
- I2V submit failure, poll failure, polling timeout이 T2V와 같은 정책으로 처리되는지 확인합니다.
- polling 상태와 `vertex_operation_name`만 남은 job이 operation name으로 재개되는지 확인합니다.
- runner startup 시 polling job을 resume task로 스케줄하는 orphan sweep 경계가 있는지 확인합니다.
- Phase 8 관련 테스트는 실제 Vertex/Veo 호출 없이 fake operation과 fake video bytes로 닫혀 있어야 합니다.

## 원문에서 찾아볼 위치

- Phase 8 분해 초안: 대략 129~226
- 첫 TDD 단위 `submit_video()` 프롬프트: 대략 233~325
- Phase 7 교훈을 Phase 8에 적용한 판단: 대략 344~395
- Phase 8 상위 계획 작성 프롬프트와 범위: 대략 487~537
- 상위 계획 본문: 대략 624~737
- polling resume 묶음 전환 판단: 대략 8147~8256
- T2V/I2V resume 및 startup sweep 결과: 대략 8270~8447
- Phase 8 문서/회귀 테스트 정리: 대략 8453~8666
- actual Veo manual QA 실패와 credential 주의: 대략 8712~9053
- 최종 Phase 8 handoff와 구현 단위 목록: 대략 9268~9309

## 복구 판단 메모

- `veo.py`가 없다면 `submit_video`, `poll_operation`, `poll_operation_by_name`, `VeoTimeoutError`를 우선 복구합니다.
- T2V/I2V는 실제 Vertex 호출 없이 fake operation/fake generated video bytes로 검증해야 합니다.
- `output_gcs_uri`를 쓰는 구현이 보이면 원래 방향과 다릅니다. Phase 8의 의도는 inline bytes를 받아 `DATA_DIR`에 저장하는 것입니다.
- polling resume은 기능 점수와 안정성 모두에 중요한 부분입니다. 단순 생성 성공보다 `vertex_operation_name` 저장과 재개 테스트를 우선 확인합니다.
