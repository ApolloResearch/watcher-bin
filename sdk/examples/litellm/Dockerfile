# Build from the SDK directory: docker build -f examples/litellm/Dockerfile .
ARG PYTHON_IMAGE=python:3.12-slim
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 openssl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE THIRD_PARTY_LICENSES.md /build/sdk/
COPY src /build/sdk/src
COPY examples/litellm/pyproject.toml examples/litellm/uv.lock examples/litellm/README.md /build/sdk/examples/litellm/
COPY examples/litellm/src /build/sdk/examples/litellm/src
RUN uv export --directory /build/sdk/examples/litellm --frozen --no-dev --no-emit-project \
      --no-emit-package watcher-sdk --output-file /tmp/requirements.lock.txt \
    && uv pip install --system --require-hashes --no-deps -r /tmp/requirements.lock.txt \
    && uv pip install --system --no-deps /build/sdk /build/sdk/examples/litellm \
    && uv pip check --system
RUN python -c 'from importlib.util import find_spec; from pathlib import Path; import subprocess; spec = find_spec("litellm"); subprocess.run(["prisma", "generate", "--schema", str(Path(spec.origin).parent / "proxy/schema.prisma")], check=True)'
ENV DISABLE_SCHEMA_UPDATE=true PYTHONDONTWRITEBYTECODE=1 GITHUB_COPILOT_TOKEN_DIR=/tmp/github-copilot
CMD ["uvicorn", "watcher_litellm.copilot:app", "--host", "0.0.0.0", "--port", "4000", "--workers", "1"]
