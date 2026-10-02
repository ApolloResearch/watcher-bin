FROM python:3.12.13-slim-bookworm
WORKDIR /opt/fixture
COPY requirements.lock.txt watcher_sdk-*.whl watcher_litellm_example-*.whl ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock.txt \
    && pip install --no-cache-dir --no-deps ./watcher_sdk-*.whl ./watcher_litellm_example-*.whl \
    && pip check
COPY tests ./tests
COPY pyproject.toml ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LITELLM_LOCAL_MODEL_COST_MAP=True DO_NOT_TRACK=1
RUN useradd --uid 1000 --create-home probe
USER probe
LABEL native.package="litellm"
ENTRYPOINT ["python", "/opt/fixture/tests/native/run_fixture.py"]
