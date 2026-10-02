FROM python:3.12.13-slim-bookworm
WORKDIR /opt/fixture
COPY requirements.lock.txt watcher_sdk-*.whl watcher_crewai_example-0.1.0-py3-none-any.whl ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock.txt \
    && pip install --no-cache-dir --no-deps ./watcher_sdk-*.whl ./watcher_crewai_example-0.1.0-py3-none-any.whl \
    && pip check
COPY demo ./demo
COPY tests ./tests
COPY pyproject.toml ./
ENV OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true CREWAI_TESTING=true CREWAI_TRACING_ENABLED=false \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NO_PROXY=127.0.0.1,localhost
RUN useradd --uid 1000 --create-home probe
USER probe
LABEL native.package="crewai" native.version="1.3.0"
ENTRYPOINT ["python", "/opt/fixture/tests/native/run_fixture.py"]
