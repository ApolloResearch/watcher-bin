FROM python:3.12.13-slim-bookworm
WORKDIR /opt/fixture
COPY pyproject.toml uv.lock requirements.txt *.whl ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt && python -m pip install --no-deps ./*.whl && python -m pip check
COPY . /opt/fixture
RUN useradd --uid 1000 --create-home probe
USER probe
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/opt/fixture/native-entry.py"]
