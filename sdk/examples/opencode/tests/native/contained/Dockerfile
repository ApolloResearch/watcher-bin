FROM node:24.11.1-bookworm-slim AS native
WORKDIR /opt/native
COPY upstream-package.json ./package.json
COPY upstream-package-lock.json ./package-lock.json
RUN npm ci --ignore-scripts --no-audit --no-fund
RUN npm ls --all --json > /opt/native/dependency-graph.json

COPY adapter.tgz install-node-package.mjs native-package.json native-package-lock.json /opt/adapter-build/
RUN node /opt/adapter-build/install-node-package.mjs /opt/adapter-build/native-package.json /opt/adapter-build/native-package-lock.json /opt/adapter-build/adapter.tgz /opt/adapter

FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git libstdc++6 ripgrep && rm -rf /var/lib/apt/lists/*
COPY --from=native /usr/local/bin/node /usr/local/bin/node
COPY --from=native /opt/native /opt/native
COPY --from=native /opt/adapter /opt/adapter
WORKDIR /opt/fixture
COPY . /opt/fixture
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt
RUN pip install --no-cache-dir --no-deps ./watcher_sdk-*.whl ./watcher_*_bridge-*.whl
RUN pip check
RUN ln -s /opt/adapter/node_modules /opt/fixture/node_modules && useradd --uid 1000 --create-home probe
RUN chmod 755 /opt/fixture/capture-python.sh
ENV SDK50_HARNESS=opencode PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/adapter/node_modules/.bin:${PATH}"
USER probe
ENV WATCHER_NATIVE_DRIVER=run_fixture.py
ENTRYPOINT ["python", "/opt/fixture/run_entry.py"]
