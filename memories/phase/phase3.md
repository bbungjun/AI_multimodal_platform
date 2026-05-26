# Phase 3 — Safe Local Asset Storage

## 현재 구조 요약

Phase 3 목표는 Vertex 호출 없이 로컬 파일 저장과 파일 서빙 기반을 만드는 것이었다. 결과 파일은 job UUID별 하위 디렉터리에 저장하고, DB에는 storage가 반환하는 상대 경로를 저장할 수 있도록 준비했다.

현재 Phase 3 관련 구조는 다음과 같다.

```text
/home/user/backend/
├── app/
│   ├── main.py
│   └── services/
│       └── storage.py
└── tests/
    └── test_storage.py
```

프론트엔드는 수정하지 않았고, Vertex API 초기화나 호출도 추가하지 않았다.

## 생성/수정한 주요 파일

- `backend/app/services/storage.py`
  - `save_bytes(job_id, filename, data)` 추가.
  - `read_bytes(local_path)` 추가.
  - `_safe_path()`, `_validate_filename()`, `_ensure_inside_root()` 등 path safety helper 추가.
  - storage 전용 `StoragePathError` 추가.
- `backend/app/main.py`
  - FastAPI `StaticFiles`를 `/files`에 mount.
  - `follow_symlink=False`, `check_dir=False` 설정 사용.
- `backend/tests/test_storage.py`
  - 정상 저장/읽기 테스트 추가.
  - unsafe filename/path 차단 테스트 추가.
  - 심볼릭 링크를 이용한 DATA_DIR 외부 우회 시도 차단 테스트 추가.

## 구현한 핵심 내용

- `save_bytes()`는 job id를 UUID로 검증하고, `DATA_DIR/<job_uuid>/<filename>` 형태로 파일을 저장한다.
- 저장 성공 시 DB에 저장하기 좋은 상대 경로 `<job_uuid>/<filename>`을 반환한다.
- 파일명은 path separator, 빈 문자열, `.`/`..`, 공백 포함 이름, 허용되지 않은 문자를 거부한다.
- `read_bytes()`는 상대 POSIX 경로만 허용하고 `<job_uuid>/<filename>` 형태를 강제한다.
- `..`, 절대경로, nested path, backslash, UUID가 아닌 job path는 `StoragePathError`로 차단한다.
- 저장 시 디렉터리와 대상 경로가 storage root 내부인지 확인하고, 가능한 환경에서는 `O_NOFOLLOW`와 directory fd 기반 open을 사용해 symlink 우회를 차단한다.
- 읽기 시 `resolve()` 결과가 storage root 밖으로 나가면 차단한다.
- `/files` static mount를 추가해 이후 생성된 로컬 asset을 HTTP로 서빙할 수 있게 했다.

## 검증한 명령과 결과

- `python3 -m compileall app`
  - 통과. `main.py`와 `services/storage.py` 컴파일 성공.
- `.venv/bin/python -m pytest tests/test_storage.py`
  - 통과. `17 passed`.
- `DATA_DIR=<temp-data-dir> PYTHONPATH=. .venv/bin/python -c "import app.main; print('backend import ok')"`
  - 통과. FastAPI `app.main:app` import 성공.

## 커밋 해시와 커밋 메시지

- `8641272888724790287a5e56673d0ce9f9e5b435`
  - `feat: add safe local asset storage`

## 다음 Phase에서 이어받을 때 주의할 점

- 후속 생성 핸들러는 사용자 입력 파일명을 그대로 사용하지 말고, 고정된 출력 파일명 또는 검증된 파일명만 `save_bytes()`에 전달해야 한다.
- DB의 `Asset.local_path`에는 `save_bytes()`가 반환한 상대 경로만 저장하는 흐름을 유지해야 한다.
- `/files`는 공개 서빙 경로이므로 credentials, `.env` 값, 서비스 계정 파일, 내부 로그 같은 민감 데이터를 `DATA_DIR` 아래에 저장하면 안 된다.
- storage helper는 로컬 파일 기반 MVP용이다. GCS나 외부 object storage로 바꾸는 작업은 이 Phase 범위가 아니다.
- Vertex 호출은 아직 구현하지 않았다. 이후 Phase에서 생성 결과 bytes를 받은 뒤 storage helper에 연결하면 된다.
