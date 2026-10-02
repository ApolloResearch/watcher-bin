FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/fixture
COPY pyproject.toml uv.lock requirements.txt *.whl ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt && python -m pip install --no-deps ./*.whl && python -m pip check
COPY . /opt/fixture
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c 'import tiktoken; tiktoken.get_encoding("o200k_base"); tiktoken.get_encoding("cl100k_base")'
RUN useradd --uid 1000 --create-home probe
USER probe
ENV PYTHONDONTWRITEBYTECODE=1
LABEL native.package="aider-chat" native.version="0.86.2" native.revision="253f0368b873ba30d8ee26e463718f0c03614ddf"
ENTRYPOINT ["python", "/opt/fixture/native-entry.py"]
