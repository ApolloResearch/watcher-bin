#!/usr/bin/env bash
# Build package artifacts, then run LiteLLM with only container loopback.
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -n "${WATCHER_EXAMPLE_RUN_DIR:-}" ]; then
  mkdir -p "$WATCHER_EXAMPLE_RUN_DIR"
  fixture_dir="$(mktemp -d "$WATCHER_EXAMPLE_RUN_DIR/litellm.XXXXXX")"
else
  fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/watcher-litellm-package.XXXXXX")"
fi
mkdir -p "$fixture_dir/context" "$fixture_dir/evidence" "$fixture_dir/dist"
if [ -z "${WATCHER_SDK_WHEEL:-}" ]; then
  uv build --exclude-newer '7 days' "$example_dir/../.." --wheel --out-dir "$fixture_dir/sdk-dist"
  sdk_wheels=("$fixture_dir"/sdk-dist/watcher_sdk-*.whl)
  test "${#sdk_wheels[@]}" -eq 1
  WATCHER_SDK_WHEEL="${sdk_wheels[0]}"
fi
test -f "$WATCHER_SDK_WHEEL"
uv export --project "$example_dir" --frozen --no-emit-project --no-emit-package watcher-sdk \
  --output-file "$fixture_dir/context/requirements.lock.txt" > "$fixture_dir/export.log" 2>&1
uv build "$example_dir" --wheel --out-dir "$fixture_dir/dist" > "$fixture_dir/build-wheel.log" 2>&1
cp "$WATCHER_SDK_WHEEL" "$fixture_dir/context/"
example_wheels=("$fixture_dir"/dist/watcher_litellm_example-*.whl)
test "${#example_wheels[@]}" -eq 1
cp "${example_wheels[0]}" "$fixture_dir/context/"
cp -R "$example_dir/tests" "$fixture_dir/context/"
cp "$example_dir/pyproject.toml" "$example_dir/tests/native/Dockerfile" "$fixture_dir/context/"
image_tag="watcher-example-litellm:$(basename "$fixture_dir")"
printf 'Native fixture artifacts: %s\n' "$fixture_dir"
docker build --iidfile "$fixture_dir/evidence/image.id" --tag "$image_tag" "$fixture_dir/context" > "$fixture_dir/build-container.log" 2>&1
image_id="$(cat "$fixture_dir/evidence/image.id")"
docker image inspect "$image_id" > "$fixture_dir/evidence/image-inspect.json"
container_id=""
cleanup() {
  if [ -n "$container_id" ]; then docker rm -f "$container_id" > /dev/null; fi
}
trap cleanup EXIT
container_id="$(docker create --network none --cap-drop ALL --security-opt no-new-privileges --read-only \
  --pids-limit 256 --memory 2g --cpus 2 \
  --user "$(id -u):$(id -g)" --env HOME=/home/probe \
  --tmpfs /tmp:rw,nosuid,size=512m \
  --tmpfs "/home/probe:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=256m" \
  --mount "type=bind,source=$fixture_dir/evidence,target=/evidence" "$image_id")"
docker inspect "$container_id" > "$fixture_dir/evidence/container-before.json"
set +e
docker start --attach "$container_id" > "$fixture_dir/evidence/run.log" 2>&1
launcher_status=$?
set -e
docker inspect "$container_id" > "$fixture_dir/evidence/container-after.json"
container_status="$(docker inspect --format '{{.State.ExitCode}}' "$container_id")"
printf '%s\n' "$launcher_status" > "$fixture_dir/evidence/launcher-exit.txt"
printf '%s\n' "$container_status" > "$fixture_dir/evidence/container-exit.txt"
docker rm "$container_id" > /dev/null
container_id=""
if [ -f "$fixture_dir/evidence/summary.json" ]; then cat "$fixture_dir/evidence/summary.json"; fi
exit "$container_status"
