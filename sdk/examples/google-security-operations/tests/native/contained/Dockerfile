FROM python:3.12-bookworm
WORKDIR /fixture
COPY requirements.txt /fixture/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY wheels /fixture/wheels
RUN pip install --no-cache-dir --no-deps /fixture/wheels/*.whl
COPY runtime-requirements.txt /fixture/runtime-requirements.txt
RUN python -m venv /opt/example-runtime \
    && /opt/example-runtime/bin/pip install --no-cache-dir --require-hashes -r runtime-requirements.txt \
    && /opt/example-runtime/bin/pip install --no-cache-dir --no-deps /fixture/wheels/*.whl
COPY . /fixture
RUN mkdir /evidence
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/fixture/entry.py"]
