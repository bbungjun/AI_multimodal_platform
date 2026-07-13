FROM python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SCORER_MODEL_CACHE=/model-cache

WORKDIR /workspace/evals/prompt_enhancement

COPY offline/requirements-runtime.lock.txt /tmp/requirements-runtime.lock.txt
COPY offline/requirements-adapters.lock.txt /tmp/requirements-adapters.lock.txt

RUN python -m pip install --require-hashes -r /tmp/requirements-runtime.lock.txt \
    && python -m pip download --no-deps --require-hashes \
        -r /tmp/requirements-adapters.lock.txt -d /tmp/adapter-wheels \
    && python -m pip install --no-deps /tmp/adapter-wheels/*.whl \
    && rm -rf /tmp/adapter-wheels

COPY . /workspace/evals/prompt_enhancement

RUN useradd --create-home --uid 10001 scorer \
    && mkdir -p /model-cache /runs \
    && chown -R scorer:scorer /model-cache /runs /workspace

USER scorer

CMD ["python", "-m", "offline.run_smoke", "--help"]
