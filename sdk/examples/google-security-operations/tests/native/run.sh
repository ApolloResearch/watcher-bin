#!/usr/bin/env bash
# Install packages separately, then exercise the complete example without networking.
set -euo pipefail
example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
slug="$(basename "$example_dir")"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
run_dir="$(mktemp -d "$run_parent/watcher-${slug}.XXXXXX")"
mkdir -p "$run_dir/context/wheels" "$run_dir/evidence"
printf 'Fixture artifacts: %s\n' "$run_dir"
sdk_wheel="${WATCHER_SDK_WHEEL:-}"
if [[ -z "$sdk_wheel" ]]; then
  uv build "$example_dir/../.." --wheel --out-dir "$run_dir/context/wheels"
else
  cp "$sdk_wheel" "$run_dir/context/wheels/"
fi
uv build "$example_dir" --wheel --out-dir "$run_dir/context/wheels"
uv export --project "$example_dir" --frozen --no-emit-project --no-emit-package watcher-sdk \
  --format requirements-txt --output-file "$run_dir/context/requirements.txt" > "$run_dir/export.log"
uv export --project "$example_dir" --frozen --no-dev --no-emit-project --no-emit-package watcher-sdk \
  --format requirements-txt --output-file "$run_dir/context/runtime-requirements.txt" > "$run_dir/runtime-export.log"
cp -R "$example_dir/demo" "$run_dir/context/demo"
cp -R "$example_dir/tests" "$run_dir/context/tests"
cp "$example_dir/pyproject.toml" "$run_dir/context/"
cp "$example_dir/tests/native/contained/"* "$run_dir/context/"
docker build --iidfile "$run_dir/image.id" --tag "watcher-example-$slug:$(basename "$run_dir")" \
  "$run_dir/context" > "$run_dir/build.log" 2>&1
image_id="$(cat "$run_dir/image.id")"
docker image inspect "$image_id" > "$run_dir/image-inspect.json"
container_id=""
cleanup() { if [[ -n "$container_id" ]]; then docker rm -f "$container_id" >/dev/null; fi; }
trap cleanup EXIT
container_id="$(docker create --pull never --network none --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 2g --cpus 2 "$image_id")"
docker inspect "$container_id" > "$run_dir/evidence/container-before.json"
set +e
docker start --attach "$container_id" > "$run_dir/evidence/run.log" 2>&1
launcher_status=$?
set -e
docker inspect "$container_id" > "$run_dir/evidence/container-after.json"
container_status="$(docker inspect --format '{{.State.ExitCode}}' "$container_id")"
printf '%s\n' "$launcher_status" > "$run_dir/evidence/launcher-exit.txt"
printf '%s\n' "$container_status" > "$run_dir/evidence/container-exit.txt"
docker cp "$container_id:/evidence/." "$run_dir/evidence/"
docker rm "$container_id" >/dev/null
container_id=""
exit "$container_status"
