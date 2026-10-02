FROM node:24.11.1-bookworm-slim AS native
RUN npm install --prefix /opt/native --ignore-scripts --no-audit --no-fund @google/gemini-cli@0.61.0-nightly.20260914.g9c1b0a610

FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git libstdc++6 ripgrep && rm -rf /var/lib/apt/lists/*
COPY --from=native /usr/local/bin/node /usr/local/bin/node
COPY --from=native /opt/native /opt/native
WORKDIR /opt/fixture
COPY pyproject.toml uv.lock requirements.txt *.whl ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt && python -m pip install --no-deps ./*.whl && python -m pip check
COPY . /opt/fixture
RUN useradd --uid 1000 --create-home probe
USER probe
ENV PYTHONDONTWRITEBYTECODE=1
ENV SDK50_HARNESS=gemini-cli
ENTRYPOINT ["python", "/opt/fixture/native-entry.py"]
