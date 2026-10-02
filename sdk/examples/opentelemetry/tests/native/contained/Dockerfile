FROM python:3.12-bookworm
WORKDIR /fixture
COPY requirements.txt /fixture/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY wheels /fixture/wheels
RUN pip install --no-cache-dir --no-deps /fixture/wheels/*.whl
COPY . /fixture
RUN mkdir /evidence && cp /fixture/otelcol-contrib /usr/local/bin/otelcol-contrib
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOME=/tmp/probe-home
CMD ["python", "/fixture/entry.py"]
