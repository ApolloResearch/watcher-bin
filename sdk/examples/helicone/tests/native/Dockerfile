FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/observer
COPY requirements.txt pyproject.toml uv.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt
COPY wheels /opt/wheels
RUN python -m pip install --no-deps /opt/wheels/*.whl && python -m pip check
COPY tests ./tests
COPY probe.py ./probe.py
COPY _test_support ./_test_support
RUN --network=none python -m pytest --noconftest -c pyproject.toml tests -q -p no:cacheprovider --junitxml=/opt/observer/contracts.xml
RUN useradd --uid 1000 --create-home probe
ENV PYTHONDONTWRITEBYTECODE=1
USER probe
