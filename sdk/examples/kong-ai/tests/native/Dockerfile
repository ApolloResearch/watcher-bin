FROM python:3.12.13-slim-bookworm
WORKDIR /opt/fixture
COPY requirements.lock.txt watcher_sdk-*.whl watcher_kong_ai_example-*.whl ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock.txt \
    && pip install --no-cache-dir --no-deps ./watcher_sdk-*.whl ./watcher_kong_ai_example-*.whl \
    && pip check
COPY tests ./tests
COPY demo ./demo
COPY pyproject.toml ./
RUN mkdir /opt/watcher-kong && cp tests/native/probe.py /opt/watcher-kong/probe.py \
    && useradd --uid 1000 --create-home probe
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER probe
CMD ["python", "/opt/fixture/tests/native/run_fixture.py"]
