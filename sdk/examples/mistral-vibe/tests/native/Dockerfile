FROM ghcr.io/astral-sh/uv:0.12.15 AS uv

FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git libstdc++6 ripgrep && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/native-runtime
COPY native-runtime/pyproject.toml native-runtime/uv.lock ./
RUN uv lock --check --project /opt/native-runtime && UV_PROJECT_ENVIRONMENT=/opt/native uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python
WORKDIR /opt/fixture
COPY pyproject.toml uv.lock requirements.txt *.whl ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt && python -m pip install --no-deps ./*.whl && python -m pip check
COPY . /opt/fixture
RUN useradd --uid 1000 --create-home probe
USER probe
ENV PYTHONDONTWRITEBYTECODE=1
ENV SDK50_HARNESS=mistral-vibe
LABEL native.package="mistral-vibe" native.version="2.25.4" native.revision="d4b3223bbd74f83cbc08da4b9c3776c8ad196955"
ENTRYPOINT ["python", "/opt/fixture/native-entry.py"]
