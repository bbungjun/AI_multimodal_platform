# Phase 5 — Rate Limiting and Retry Utilities

## 현재 구조 요약

Phase 5 목표는 Vertex 실제 호출 없이, 후속 잡 러너와 Vertex 핸들러가 공유할 모델별 sliding-window rate limiter와 retry/backoff 유틸을 만드는 것이었다.

현재 Phase 5 관련 구조는 다음과 같다.

```text
/home/user/backend/
├── app/
│   └── services/
│       ├── rate_limit.py
│       └── retry.py
└── tests/
    ├── test_rate_limiter.py
    └── test_retry.py
```

프론트엔드는 수정하지 않았고, Vertex 실제 생성 호출도 추가하지 않았다.

## 생성/수정한 주요 파일

- `backend/app/services/rate_limit.py`
  - `SlidingWindowLimiter` 추가.
  - `RateLimit`, `RateLimitError`, `UnknownModelRateLimitError` 추가.
  - 모델별 기본 limiter registry `LIMITERS` 추가.
  - `get_limiter(model_id)`, `acquire(model_id)` 추가.
- `backend/app/services/retry.py`
  - `with_retry(awaitable_factory, ...)` 추가.
  - retryable status 기본값 `429, 500, 502, 503, 504, 408` 정의.
  - exponential backoff와 `max_delay` cap 적용.
  - `RetryConfigError` 추가.
- `backend/tests/test_rate_limiter.py`
  - capacity 내 즉시 통과, window slide 후 대기, 동시 acquire, 기본 모델 limiter 등록, unknown model 테스트 추가.
- `backend/tests/test_retry.py`
  - retryable 실패 후 성공, non-retryable 4xx 즉시 실패, max attempts 중단, backoff cap, response status code, `retryable=True` 예외 테스트 추가.

## 구현한 핵심 내용

- limiter는 `asyncio.Lock`과 `collections.deque`를 사용해 모델별 최근 acquire 시각을 sliding window로 관리한다.
- `acquire()`는 즉시 통과하면 `0.0`, 대기했다면 누적 대기 시간을 반환한다.
- `current_size()`와 `estimate_wait()`는 현재 window 내 이벤트 수와 예상 대기 시간을 계산한다.
- 기본 모델 제한은 Imagen 모델 75/min, Veo 모델 10/min, Gemini enhance 모델 60/min으로 등록했다.
- 테스트를 빠르게 유지하기 위해 `SlidingWindowLimiter`는 clock/sleep 주입을 지원한다.
- `with_retry()`는 호출마다 새 coroutine을 만드는 `awaitable_factory`를 받는다.
- retry 여부는 예외의 `retryable=True`, `status_code`, `code`, `status`, `response.status_code` 순서로 확인한다.
- backoff는 `base * 2 ** (attempt - 1)`이며 `max_delay`를 넘지 않는다.

## 검증한 명령과 결과

- `python3 -m compileall app`
  - 통과. `services/rate_limit.py`, `services/retry.py` 컴파일 성공.
- `.venv/bin/python -m pytest tests/test_rate_limiter.py tests/test_retry.py`
  - 통과. `17 passed`.
- `.venv/bin/python -m pytest`
  - 통과. `133 passed`.
- `DATA_DIR=/tmp/codex-phase5-assets PYTHONPATH=. .venv/bin/python -c "import app.main; print('backend import ok')"`
  - 통과. FastAPI `app.main:app` import 성공.

## 커밋 해시와 커밋 메시지

- `6bc48d8f700ee4aea6cfeb8d483b39750b3d26e5`
  - `feat: add rate limiting and retry utilities`

## 다음 Phase에서 이어받을 때 주의할 점

- Phase 6 잡 러너는 모델 호출 직전에 `await rate_limit.acquire(model_id)`를 호출하는 흐름으로 연결해야 한다.
- `with_retry()`에는 이미 생성된 coroutine이 아니라, 매 attempt마다 새 coroutine을 반환하는 factory를 넘겨야 한다.
- 실제 Vertex 핸들러에서는 Phase 4의 `VertexServiceError.retryable`과 status code 매핑을 같이 활용해야 한다.
- limiter registry는 프로세스 메모리 기반이다. 현재 MVP 구조에서는 in-process runner 전제와 맞지만, 다중 worker/process로 늘리면 공유 limiter가 필요하다.
- 테스트에서 실제 60초 window를 기다리지 않도록 clock/sleep 주입 패턴을 유지한다.
