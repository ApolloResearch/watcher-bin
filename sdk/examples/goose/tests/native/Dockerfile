FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git libstdc++6 ripgrep && rm -rf /var/lib/apt/lists/*
COPY goose.tar.gz /tmp/goose.tar.gz
RUN echo "ff8c51428180142e5c92e2a0b67b3d1762698499d028f6f5fe370fdbec8c84af  /tmp/goose.tar.gz" | sha256sum -c - && tar -xzf /tmp/goose.tar.gz -C /usr/local/bin && rm /tmp/goose.tar.gz
WORKDIR /opt/fixture
COPY pyproject.toml uv.lock requirements.txt *.whl ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt && python -m pip install --no-deps ./*.whl && python -m pip check
COPY . /opt/fixture
RUN useradd --uid 1000 --create-home probe
USER probe
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/opt/fixture/native-entry.py"]
