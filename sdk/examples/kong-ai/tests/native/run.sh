#!/usr/bin/env bash
# Build independent artifacts; run Kong and fixtures in one isolated namespace.
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
fixture_dir="$(mktemp -d "$run_parent/kong.XXXXXX")"
mkdir -p "$fixture_dir/context" "$fixture_dir/evidence" "$fixture_dir/dist"
printf 'Native fixture artifacts: %s\n' "$fixture_dir"
if [ -z "${WATCHER_SDK_WHEEL:-}" ]; then
  uv build "$example_dir/../.." --wheel --out-dir "$fixture_dir/sdk-dist"
  sdk_wheels=("$fixture_dir"/sdk-dist/watcher_sdk-*.whl)
  test "${#sdk_wheels[@]}" -eq 1
  WATCHER_SDK_WHEEL="${sdk_wheels[0]}"
fi
uv export --project "$example_dir" --frozen --no-emit-project --no-emit-package watcher-sdk \
  --output-file "$fixture_dir/context/requirements.lock.txt" > "$fixture_dir/export.log" 2>&1
uv build "$example_dir" --wheel --out-dir "$fixture_dir/dist" > "$fixture_dir/wheel.log" 2>&1
cp "$WATCHER_SDK_WHEEL" "$fixture_dir/context/"
cp "$fixture_dir"/dist/*.whl "$fixture_dir/context/"
cp -R "$example_dir/demo" "$example_dir/tests" "$fixture_dir/context/"
cp "$example_dir/pyproject.toml" "$example_dir/tests/native/Dockerfile" "$fixture_dir/context/"
cp -R "$example_dir/gateway/kong/plugins/watcher" "$fixture_dir/plugin"
docker build --iidfile "$fixture_dir/evidence/image.id" "$fixture_dir/context" > "$fixture_dir/build.log" 2>&1
image_id="$(cat "$fixture_dir/evidence/image.id")"
kong_image='kong@sha256:12972ce1ab6396083e56e7d46fce084836c98cc819344bef44a1f583ec3ab191'
docker image inspect "$kong_image" > /dev/null 2>&1 || docker pull "$kong_image"
docker image inspect "$image_id" > "$fixture_dir/evidence/image-inspect.json"
docker image inspect "$kong_image" > "$fixture_dir/evidence/kong-image.json"
client_id=""
kong_id=""
cleanup() {
  if [ -n "$kong_id" ]; then docker rm -f "$kong_id" >/dev/null; fi
  if [ -n "$client_id" ]; then docker rm -f "$client_id" >/dev/null; fi
}
trap cleanup EXIT
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges \
  --memory 256m --cpus 1 --entrypoint kong "$kong_image" version > "$fixture_dir/evidence/kong-version.txt"
client_id="$(docker create --network none --cap-drop ALL --security-opt no-new-privileges --read-only \
  --pids-limit 256 --memory 1g --cpus 1 --user "$(id -u):$(id -g)" --env HOME=/home/probe \
  --tmpfs /tmp:rw,nosuid,size=256m \
  --tmpfs "/home/probe:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=256m" \
  --mount "type=bind,source=$fixture_dir/evidence,target=/evidence" "$image_id")"
docker inspect "$client_id" > "$fixture_dir/evidence/container-before.json"
docker start "$client_id" > /dev/null
ready_deadline=$((SECONDS + 90))
until [ -f "$fixture_dir/evidence/companion-ready" ]; do
  if [ "$(docker inspect --format '{{.State.Running}}' "$client_id")" != true ] || [ "$SECONDS" -ge "$ready_deadline" ]; then
    docker logs "$client_id" > "$fixture_dir/evidence/run.log" 2>&1
    exit 1
  fi
  sleep 0.2
done
kong_id="$(docker create --network "container:$client_id" --cap-drop ALL --security-opt no-new-privileges --read-only \
  --pids-limit 128 --memory 512m --cpus 1 --user "$(id -u):$(id -g)" \
  --tmpfs "/tmp:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=128m" \
  --env KONG_DATABASE=off --env KONG_DECLARATIVE_CONFIG=/evidence/kong.yaml \
  --env KONG_PLUGINS=bundled,watcher --env KONG_PROXY_LISTEN=127.0.0.1:11867 \
  --env KONG_ADMIN_LISTEN=off --env KONG_NGINX_WORKER_PROCESSES=1 --env KONG_PREFIX=/tmp/kong \
  --mount "type=bind,source=$fixture_dir/evidence,target=/evidence,readonly" \
  --mount "type=bind,source=$fixture_dir/plugin,target=/usr/local/share/lua/5.1/kong/plugins/watcher,readonly" \
  "$kong_image")"
docker inspect "$kong_id" > "$fixture_dir/evidence/kong-container-before.json"
docker start "$kong_id" > /dev/null
status="$(docker wait "$client_id")"
docker logs "$client_id" > "$fixture_dir/evidence/run.log" 2>&1
docker logs "$kong_id" > "$fixture_dir/evidence/kong.log" 2>&1
docker inspect "$client_id" > "$fixture_dir/evidence/container-after.json"
docker inspect "$kong_id" > "$fixture_dir/evidence/kong-container-after.json"
printf '%s\n' "$status" > "$fixture_dir/evidence/container-exit.txt"
docker rm -f "$kong_id" > /dev/null
kong_id=""
docker rm "$client_id" > /dev/null
client_id=""
exit "$status"
