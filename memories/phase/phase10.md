# Phase 10 — T2I -> I2V 파이프라인 계획

> 2026-05-23 기준 현재 핸드오프(Handoff) 계획. Phase 10은 백엔드 우선, TDD(테스트 주도 개발) 우선, 모의/가짜(Mock/Fake) 객체 기반으로 유지하며 실제 Vertex/Veo 호출은 포함하지 않습니다.
> 

## 범위 (Scope)

Phase 10은 기존의 생성 작업 시스템 위에 좁은 범위의 T2I -> I2V 파이프라인을 추가합니다. 이 파이프라인은 별도의 큐(Queue), Redis/Celery, GCS, 프론트엔드 UI를 추가하지 않고, 테스트에서 실제 Vertex/Veo를 호출하지 않으면서 완료된 T2I 이미지 에셋을 자식 I2V 작업과 연결해야 합니다.

## 현재 파이프라인 상태

- `backend/app/models.py`에 `Job.parent_job_id`, `Job.source_asset_id`, `Job.blocked` 필드가 이미 존재합니다.
- `JobResponse` 스키마가 `parent_job_id`, `source_asset_id`, `blocked`를 이미 노출하고 있습니다.
- 작업 러너(Job runner)가 차단된 작업을 필터링하는 로직이 이미 존재합니다:
`Job.state == pending AND Job.blocked IS false`.
- 개별 T2I, T2V, I2V 생성 요청 기능이 `backend/app/api/generations.py`에 이미 존재합니다.
- T2I 핸들러는 Imagen 생성이 성공한 후 이미지 `Asset` 행(Row)을 기록합니다.
- I2V 핸들러는 `source_asset_id`를 읽어 소스 에셋이 존재하고 이미지인지 검증한 후, 모킹 가능한(Mockable) Veo 서비스 경계로 소스 바이트(Bytes)를 전달합니다.
- `POST /api/pipelines`가 존재하며, 부모 T2I 작업과 차단된 자식 I2V 작업을 생성합니다.
- 파이프라인 ID는 부모 T2I 작업의 ID와 동일합니다.
- `backend/app/services/jobs/pipeline_link.py`는 파일을 복사하지 않고 `source_asset_id`를 통해 완료된 부모 이미지 에셋을 차단된 자식 작업과 연결합니다.
- T2I 핸들러 통합부(Integration)는 부모 작업이 성공적으로 완료되면 파이프라인 연결을 호출하고, 부모 작업이 실패하면 차단된 자식 작업으로 실패를 전파(Cascade)합니다.
- `GET /api/pipelines/{parent_job_id}`가 존재하며 `{id, parent, child}`를 반환합니다.
- 모의/가짜(Mock/Fake) 기반의 Phase 10 백엔드 작업이 완료되었습니다.
- 실제 Vertex/Veo/Gemini를 사용한 수동 QA는 자동화된 테스트 외부에서 자격 증명 및 런타임 설정이 준비될 때까지 연기되었습니다.
- 프론트엔드 파이프라인 UI는 이후 프론트엔드 단계로 연기되었습니다.
- Docker/README 마무리는 이후 문서화/배포 단계로 연기되었습니다.

## 범위 제어 (Scope Control)

다음 사항들은 Phase 10의 규모를 지나치게 키울 수 있으므로, 이후 명시적인 단위 요구사항이 나오기 전까지는 제외해야 합니다:

- 새로운 `pipelines` 데이터베이스 테이블 추가 또는 마이그레이션. 기존 `jobs` 관계를 우선적으로 사용하세요.
- 여러 개의 자식 작업, 다단계 DAG, 생성된 모든 이미지에 대한 팬아웃(Fan-out), 또는 임의의 파이프라인 그래프 구조.
- 파이프라인 레벨의 프롬프트 향상 또는 `auto_enhance=True` 실행. Phase 9의 향상 연결 기능은 생성 작업을 통해 여전히 사용할 수 있지만, 자동 향상은 여전히 제외됩니다.
- 프론트엔드 파이프라인 UI.
- Docker, README, 배포 또는 최종 문서 다듬기 작업.
- 테스트 코드에서의 실제 Vertex, Imagen, Veo 또는 Gemini 호출.
- GCS 출력 또는 서비스 계정/자격 증명 처리 방식의 변경.
- 기존 작업 상태 지원 범위를 넘어서는 전체 파이프라인 대상의 취소(Cancellation) 의미론(Semantics).

## 파이프라인 모델

- 초기 구현에서는 별도의 `pipelines` 테이블을 추가하지 마세요.
- 파이프라인 ID는 부모 T2I 작업의 ID로 취급합니다.
- `POST /api/pipelines`는 하나의 트랜잭션 안에서 두 개의 `Job` 행을 생성합니다:
    - 부모 T2I 작업:
        - `mode=t2i`
        - `state=pending`
        - `blocked=false`
        - `prompt=image_prompt`
        - `parameters.number_of_images=1`
    - 자식 I2V 작업:
        - `mode=i2v`
        - `state=pending`
        - `blocked=true`
        - `parent_job_id=parent.id`
        - `source_asset_id=None` (부모가 완료될 때까지)
        - `prompt=video_prompt`
- `GET /api/pipelines/{parent_job_id}`는 부모 작업과 자식 I2V 작업을 반환합니다. 만약 어떤 이유로든 자식이 여러 개 존재한다면, 가장 먼저 생성된 자식을 반환하고 팬아웃 지원은 Phase 10에서 제외합니다.
- 각 작업은 기존 `/api/generations` 엔드포인트를 통해 계속 조회할 수 있도록 유지합니다.

## T2I 에셋 -> I2V 소스 정책

- 파이프라인의 T2I 부모 작업은 정확히 **하나의 이미지**만 생성해야 합니다. 이는 자식 I2V 작업과 연결할 때의 모호함을 방지하기 위함입니다.
- 자식 I2V 작업은 유효한 이미지 에셋을 사용할 수 있을 때까지 `blocked=true` 상태를 유지해야 합니다.
- 부모 작업이 `completed` 상태에 도달하면, 부모의 출력 이미지 에셋을 찾습니다:
    - 해당 에셋은 부모 작업에 속해야 합니다.
    - 에셋의 `kind`는 `image`여야 합니다.
    - 만약 어떤 이유로든 이미지가 여러 개 존재한다면, 안정적인 영속성 정렬 순서(`created_at` 기준 후 `id` 기준)에 따라 첫 번째 이미지를 선택하고 팬아웃은 나중으로 미룹니다.
- 파일을 복사하지 않고 참조(Reference) 방식으로 연결합니다:
    - `child.source_asset_id=asset.id`로 설정합니다.
    - `child.blocked=false`로 설정합니다.
    - `child.state=pending` 상태를 유지합니다.
- 이를 통해 다음번 러너 폴링 때 기존의 pending/unblocked 쿼리를 통해 자식 I2V 작업을 자연스럽게 가져가서 처리할 수 있게 됩니다.
- 부모 실패의 전파(Cascade)는 첫 번째 링크 서비스 슬라이스가 아닌, Unit 3의 핸들러 통합부에서 처리합니다.
- 부모 작업이 취소된 경우, 이후 단계에서 명시적으로 스코프를 지정하기 전까지는 전체 파이프라인 취소 처리를 연기합니다. 최소한으로 허용되는 정책은 자식을 계속 차단 상태로 두거나, 정제된 부모 종료 에러(sanitized parent-terminal error)와 함께 자식을 실패 처리하는 것입니다.

## 실패 정책 (Failure Policy)

자식 I2V 작업을 시작하기 전에 다음과 같은 경우 거부(Reject)하거나 실패 처리합니다:

- 원본/부모 작업이 없는 경우:
    - API 조회 시 `404`를 반환해야 합니다.
    - 링크 서비스는 아무 작업도 하지 않거나(No-op) 새 작업을 생성하지 않고 타입이 지정된 실패 결과를 반환해야 합니다.
- 부모 작업의 상태가 적절하지 않은 경우:
    - 자식 소스 연결 전에 부모가 반드시 `completed` 상태여야 합니다.
    - pending/queued/generating/polling/downloading 상태인 부모는 자식의 차단을 해제해서는 안 됩니다.
    - 실패한 부모의 전파 처리는 Unit 3 핸들러 통합부의 책임입니다.
- 부모 작업의 모드가 적절하지 않은 경우:
    - 부모 모드는 반드시 `t2i`여야 합니다. T2I가 아닌 부모는 유효한 파이프라인 소스가 아닙니다.
- 에셋이 없는 경우:
    - 완료된 부모 작업에 이미지 출력이 없는 경우, 차단된 자식 작업을 정제된 `pipeline_source_asset_missing` 에러와 함께 실패 처리해야 합니다.
- 이미지가 아닌 에셋인 경우:
    - 부모 출력 에셋의 `kind != image`인 경우, 차단된 자식 작업을 `pipeline_source_asset_not_image` 에러와 함께 실패 처리해야 합니다.
- 자식 작업의 상태가 적절하지 않은 경우:
    - `pending` 상태이면서 차단된(`blocked=true`) 자식 작업만 링크 서비스에 의해 차단이 해제되어야 합니다.
    - 이미 종료(Terminal) 상태인 자식 작업은 수정되어서는 안 됩니다.

## 제안된 구현 단위 (Proposed Units)

### Unit 1 — 파이프라인 API 계약 및 작업 생성

- 상태: `1622326` 커밋에서 완료.
- 생성 응답(Create response)에 대해서만 파이프라인 요청/응답 스키마를 추가합니다. 조회/상세 응답(Read/detail response)은 Unit 4에서 다룹니다.
- `backend/app/api/pipelines.py`를 추가하고 `main.py`에 연결합니다.
- `POST /api/pipelines`는 하나의 트랜잭션에서 부모 T2I 작업과 차단된 자식 I2V 작업을 생성합니다.
- 본 단위는 부모/자식 작업 생성 형태에만 집중합니다.
- 기존의 모델 허용 목록(Allowlist)/접두사(Prefix) 검증 로직이 새로운 정책 도입 없이 호출할 수 있을 정도로 깔끔하게 분리되어 있다면 이를 재사용합니다. 재사용을 위해 새로운 검증 디자인이 필요하다면 지원되지 않는 모델의 거부 처리는 나중으로 미룹니다.
- `auto_enhance=True`는 지원하지 않으며 스키마에서 제외합니다.
- 테스트 케이스:
    - 성공 경로(Happy path)는 부모 및 자식 작업 데이터를 반환합니다.
    - 부모는 차단 해제된 T2I pending 상태입니다.
    - 자식은 `parent_job_id`가 있고 `source_asset_id`가 없는 차단된 I2V pending 상태입니다.
    - 지원되지 않는 모델은 기존 생성 검증을 직접 재사용할 수 있는 경우에만 작업 생성 전에 거부됩니다.
    - 실수로 Vertex/Veo/Enhancer가 호출되지 않도록 방어막을 구성합니다.

### Unit 2 — 파이프라인 링크 서비스 (Link Service)

- 상태: `061cc2f` 커밋에서 완료.
- 소형 서비스인 `backend/app/services/jobs/pipeline_link.py`를 추가합니다.
- 완료된 부모 작업 ID가 주어지면, 차단된 자식 작업과 부모의 출력 이미지를 찾아 해결(Resolve)합니다.
- 유효한 이미지 에셋을 가진 완료된 부모 작업에 대해, 자식의 `source_asset_id`를 설정하고 `blocked=false`로 변경합니다.
- 본 단위는 완료된 부모의 이미지 연결에 집중합니다. 부모 실패 전파 로직은 여기에 추가하지 마세요.
- 모의 세션(Fake sessions)을 통해 먼저 필요한 실패 케이스들을 직접 다룹니다:
    - 부모는 완료되었으나 에셋이 없는 경우.
    - 부모는 완료되었으나 이미지가 아닌 에셋인 경우.
    - 자식이 이미 종료 상태인 경우.
- 자식의 실패를 기록할 때 `transition(...)`을 통한 상태 변경을 유지합니다.

### Unit 3 — 핸들러 통합 (Handler Integration)

- 상태: `98b8c65` 커밋에서 완료.
- `handle_t2i`가 이미지 에셋을 성공적으로 기록하고 부모를 `completed` 상태로 전환한 후에 링크 서비스를 호출합니다.
- 만약 부모 T2I 처리가 실패하여 부모가 실패로 표시되면, 차단된 자식 작업으로 정제된 실패를 전파합니다.
- 테스트 케이스:
    - 모킹된 T2I 성공 시 이미지를 저장하고, 자식의 차단을 해제하며, `source_asset_id`를 할당합니다.
    - 러너는 차단된 상태 동안 자식을 무시하고, 연결이 완료된 후에 자식을 가져갑니다.
    - 모킹된 부모 실패 시 Veo 호출 없이 자식을 실패로 표시합니다.
    - 실제 Vertex/Veo 호출은 발생하지 않습니다.

### Unit 4 — 파이프라인 조회 API 및 회귀 테스트 (Regression)

- 상태: `6aead88` 커밋에서 완료.
- `GET /api/pipelines/{parent_job_id}`를 추가하거나 완성합니다.
- 다음을 포함하는 컴팩트한 응답을 반환합니다:
    - 부모 작업 ID인 `id`.
    - 부모의 `GenerationResponse`.
    - 자식의 `GenerationResponse`.
- 테스트 케이스:
    - 부모가 없는 경우 `404`를 반환합니다.
    - 자식이 없는 부모의 경우 기존 API 에러 스타일에 따라 명확한 `404` 또는 `409`를 반환합니다.
    - 성공 응답에는 부모 에셋 및 자식 연결 필드가 포함됩니다.
- 집중적인 파이프라인/생성/작업 러너 테스트를 실행한 후, 더 넓은 범위의 백엔드 회귀 테스트를 실행합니다.

## 테스트 전략 (Test Strategy)

- 생성 흐름 테스트에 사용된 기존의 모의 세션/팩토리(Fake session/factory) 패턴을 사용합니다.
- `handlers.imagen`, `handlers.veo`, `rate_limit.acquire` 및 모든 Enhancer/Vertex 클라이언트 경계를 몽키패치(Monkeypatch)하여 실수로 실제 프로바이더가 호출될 경우 테스트가 실패하도록 만듭니다.
- 요청/응답 계약 확인을 위해서는 API 레벨 테스트를 선호하고, 연결(Linkage) 예외 케이스 확인을 위해서는 서비스 레벨 테스트를 선호합니다.
- 자격 증명, `.env`, 서비스 계정 JSON 파일 또는 외부 네트워크 접근을 요구하거나, 출력하거나, 이에 의존하지 마세요.

## 마지막으로 확인된 정상(Green) 기준선

- Unit 4A 집중 테스트:
`backend/.venv/bin/pytest backend/tests/test_pipeline_api.py` -> `5 passed`.
- 관련 파이프라인/작업 회귀 테스트:
`backend/.venv/bin/pytest backend/tests/test_pipeline_api.py backend/tests/test_pipeline_link.py backend/tests/test_t2i_flow.py backend/tests/test_i2v_flow.py backend/tests/test_job_runner.py`
-> `46 passed`.
- 전체 백엔드 테스트: `backend/.venv/bin/pytest backend/tests` -> `206 passed`.

## 완료된 커밋 목록

1. `a2aedd1 docs: narrow phase 10 pipeline units`
2. `1622326 feat: add pipeline creation API`
3. `061cc2f feat: add pipeline link service`
4. `98b8c65 feat: integrate pipeline link with t2i handler`
5. `6aead88 feat: add pipeline read API`

## 완료된 동작

- `POST /api/pipelines` 엔드포인트 구현.
- 부모 T2I + 차단된 자식 I2V 작업 생성 로직.
- 파이프라인 ID와 부모 작업 ID의 일치화.
- 완료된 부모 이미지 에셋이 `child.source_asset_id`와 연결되며 자식의 차단이 해제됨.
- 부모 T2I 실패가 자식에게 `pipeline_parent_failed`로 전파됨.
- `GET /api/pipelines/{parent_job_id}` 엔드포인트 구현.
- 테스트는 모의/가짜 프로바이더 경계를 사용함; 자동화된 테스트에서 실제 Vertex/Veo/Gemini 호출을 수행하지 않음.

## 연기된 사항 (Deferred)

- 실제 Vertex/Veo/Gemini를 사용한 수동 QA.
- 프론트엔드 파이프라인 UI.
- Docker/README 마무리 작업.
- 자격 증명, `.env`, 서비스 계정 내용 및 런타임 시크릿 처리 방식의 변경 (Phase 10에서 요청되거나 출력되거나 필요하지 않았음).

## 권장하는 첫 번째 구현 단위

Phase 10 백엔드 작업은 완료되었습니다. 권장하는 다음 단계: 프로젝트 작업 순서에 따라 프론트엔드 파이프라인 UI와 함께 계획된 다음 페이즈를 시작하거나 Docker/README 마무리 작업으로 이동하세요. 실제 Vertex/Veo/Gemini 수동 QA는 자격 증명 및 런타임 구성이 준비될 때까지 연기된 상태를 유지합니다.