#!/usr/bin/env bash
# Acquire packages during preparation; every installed native fixture runs without external networking.
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$example_dir"
if [ -n "${WATCHER_EXAMPLE_RUN_DIR:-}" ]; then
  mkdir -p "$WATCHER_EXAMPLE_RUN_DIR"
  fixture_dir="$(mktemp -d "$WATCHER_EXAMPLE_RUN_DIR/goose.XXXXXX")"
else
  fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/watcher-goose-package.XXXXXX")"
fi
mkdir -p "$fixture_dir/source" "$fixture_dir/context" "$fixture_dir/evidence"
printf 'Native package artifacts: %s\n' "$fixture_dir"
if [ -n "${WATCHER_SDK_WHEEL:-}" ]; then
  cp "$WATCHER_SDK_WHEEL" "$fixture_dir/context/"
else
  uv build --project "$example_dir" "$example_dir/../.." --wheel --out-dir "$fixture_dir/sdk-dist"
  cp "$fixture_dir"/sdk-dist/*.whl "$fixture_dir/context/"
fi
uv build --project "$example_dir" --wheel "$example_dir" --out-dir "$fixture_dir/example-dist"
cp "$fixture_dir"/example-dist/*.whl "$fixture_dir/context/"
uv export --project "$example_dir" --frozen --no-emit-project --no-emit-package watcher-sdk \
  --format requirements.txt --output-file "$fixture_dir/context/requirements.txt" > "$fixture_dir/export.log"
cp "$example_dir/pyproject.toml" "$example_dir/uv.lock" "$fixture_dir/context/"
cp -R "$example_dir/tests" "$fixture_dir/context/tests"
for asset in "$example_dir"/tests/native/*; do
  if [ -f "$asset" ]; then cp "$asset" "$fixture_dir/context/"; fi
done
if [ -d "$example_dir/demo" ]; then
  cp -R "$example_dir/demo" "$fixture_dir/context/demo"
  for asset in "$example_dir"/demo/*; do
    if [ -f "$asset" ]; then cp "$asset" "$fixture_dir/context/"; fi
  done
fi
curl -fsSL https://github.com/aaif-goose/goose/releases/download/v1.50.0/goose-x86_64-unknown-linux-musl.tar.gz -o "$fixture_dir/context/goose.tar.gz"
base_tag="watcher-goose-base:$(basename "$fixture_dir")"
docker build --iidfile "$fixture_dir/evidence/base-image.id" --tag "$base_tag" --file "$example_dir/tests/native/Dockerfile" "$fixture_dir/context" > "$fixture_dir/build.log" 2>&1
base_id="$(cat "$fixture_dir/evidence/base-image.id")"
image_id="$base_id"
if [ -f "$example_dir/tests/native/Dockerfile.synchronous" ]; then
  docker build --iidfile "$fixture_dir/evidence/image.id" --build-arg "BASE_IMAGE=$base_tag" \
    --file "$example_dir/tests/native/Dockerfile.synchronous" "$fixture_dir/context" > "$fixture_dir/synchronous-build.log" 2>&1
  image_id="$(cat "$fixture_dir/evidence/image.id")"
fi
docker image inspect "$base_id" "$image_id" > "$fixture_dir/evidence/image-inspect.json"
scenarios=("$@")
if [ "$#" -eq 0 ]; then scenarios=(observe allow deny pending escalate deferred observe-mode paused observe-deferred paused-deferred grading-failure-allow missing-outcome identity-error http-error timeout unit); fi
if [[ "${WATCHER_EXAMPLE_BUILD_ONLY:-}" == "1" ]]; then
  printf "Prepared native image artifacts: %s\n" "$fixture_dir"
  exit 0
fi
container_id=""
cleanup() { if [ -n "$container_id" ]; then docker rm -f "$container_id" > /dev/null; fi; }
trap cleanup EXIT
failed=0
for scenario in "${scenarios[@]}"; do
  case "$scenario" in observe|allow|deny|pending|escalate|deferred|observe-mode|paused|observe-deferred|paused-deferred|grading-failure-allow|missing-outcome|identity-error|http-error|timeout|unit) ;; *) echo "Unknown scenario: $scenario" >&2; exit 2 ;; esac
  evidence_dir="$fixture_dir/evidence/$scenario"
  mkdir -p "$evidence_dir"
  chosen_image="$image_id"
  if [ "$scenario" = observe ]; then chosen_image="$base_id"; fi
  container_id="$(docker create --pull never --network none --cap-drop ALL --security-opt no-new-privileges --read-only \
    --pids-limit 256 --memory 2g --cpus 2 --user "$(id -u):$(id -g)" --env HOME=/home/probe \
    --env "WATCHER_EXAMPLE_SCENARIO=$scenario" --env WATCHER_EPHEMERAL_PRE_TOOL=1 \
    --tmpfs /tmp:rw,exec,nosuid,size=512m \
    --tmpfs "/home/probe:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=256m" \
    --mount "type=bind,source=$evidence_dir,target=/evidence" "$chosen_image")"
  docker inspect "$container_id" > "$evidence_dir/container-before.json"
  set +e
  docker start --attach "$container_id" > "$evidence_dir/run.log" 2>&1
  launcher_status=$?
  set -e
  docker inspect "$container_id" > "$evidence_dir/container-after.json"
  container_status="$(docker inspect --format '{{.State.ExitCode}}' "$container_id")"
  printf '%s\n' "$launcher_status" > "$evidence_dir/launcher-exit.txt"
  printf '%s\n' "$container_status" > "$evidence_dir/container-exit.txt"
  docker rm "$container_id" > /dev/null
  container_id=""
  if [ -f "$evidence_dir/environment.json" ] && [ ! -f "$fixture_dir/evidence/environment.json" ]; then
    cp "$evidence_dir/environment.json" "$fixture_dir/evidence/environment.json"
  fi
  printf '%s: exit %s\n' "$scenario" "$container_status"
  if [ "$launcher_status" -ne 0 ] || [ "$container_status" -ne 0 ]; then failed=1; fi
done
exit "$failed"
