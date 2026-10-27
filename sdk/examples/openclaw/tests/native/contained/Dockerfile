FROM node:24.22.1-bookworm-slim AS native
WORKDIR /opt/native
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
RUN --network=none node node_modules/openclaw/scripts/postinstall-bundled-plugins.mjs
RUN npm ls --all --json > /opt/native/dependency-graph.json || test -s /opt/native/dependency-graph.json

FROM python:3.12.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git libstdc++6 ripgrep && rm -rf /var/lib/apt/lists/*
COPY --from=native /usr/local/bin/node /usr/local/bin/node
COPY --from=native /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
COPY --from=native /opt/native /opt/native
WORKDIR /opt/fixture
COPY . /opt/fixture
RUN chmod +x /opt/fixture/bridge_entry.py
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt
RUN pip install --no-cache-dir --no-deps ./watcher_*.whl
RUN pip check
RUN ln -s /opt/native/node_modules /opt/fixture/node_modules && useradd --uid 1000 --create-home probe
ENV PYTHONDONTWRITEBYTECODE=1 PATH="/opt/native/node_modules/.bin:${PATH}"
USER probe
ENTRYPOINT ["python", "/opt/fixture/entry.py"]
