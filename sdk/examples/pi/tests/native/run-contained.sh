#!/usr/bin/env bash
# Build package artifacts before running a native harness with no external network.
set -euo pipefail
example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
slug="$(basename "$example_dir")"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
fixture_dir="$(mktemp -d "$run_parent/watcher-${slug}-contained.XXXXXX")"
mkdir -p "$fixture_dir/context" "$fixture_dir/evidence" "$fixture_dir/dist"
printf 'Native fixture artifacts: %s\n' "$fixture_dir"
sdk_wheel="${WATCHER_SDK_WHEEL:-}"
if [[ -z "$sdk_wheel" ]]; then
  uv build "$example_dir/../.." --wheel --out-dir "$fixture_dir/dist"
  sdk_wheels=("$fixture_dir"/dist/watcher_sdk-*.whl)
  test "${#sdk_wheels[@]}" -eq 1
  sdk_wheel="${sdk_wheels[0]}"
  test -f "$sdk_wheel"
fi
cp "$sdk_wheel" "$fixture_dir/context/"
uv build "$example_dir/packages/python" --wheel --out-dir "$fixture_dir/context"
uv export --project "$example_dir/packages/python" --frozen --no-emit-project \
  --no-emit-package watcher-sdk --format requirements-txt --output-file "$fixture_dir/context/requirements.txt" > "$fixture_dir/export.log"
npm pack "$example_dir/packages/node" --pack-destination "$fixture_dir/dist" --ignore-scripts
cp "$fixture_dir"/dist/*.tgz "$fixture_dir/context/adapter.tgz"
cp "$example_dir/tests/native/upstream/package.json" "$fixture_dir/context/upstream-package.json"
cp "$example_dir/tests/native/upstream/package-lock.json" "$fixture_dir/context/upstream-package-lock.json"
cp "$example_dir/packages/node/package.json" "$fixture_dir/context/native-package.json"
cp "$example_dir/packages/node/package-lock.json" "$fixture_dir/context/native-package-lock.json"
cp "$example_dir/packages/node/package-lock.json" "$fixture_dir/context/package-lock.json"
printf '%s\n' '{"private":true,"type":"module"}' > "$fixture_dir/context/package.json"
cp "$example_dir/tests/native/install-node-package.mjs" "$fixture_dir/context/"
cp "$example_dir/tests/native/contained/"* "$fixture_dir/context/"
cp "$example_dir/tests/"test_*.py "$fixture_dir/context/"
if [[ -f "$example_dir/tests/test_plugin.mjs" ]]; then cp "$example_dir/tests/test_plugin.mjs" "$fixture_dir/context/"; fi
if [[ -f "$example_dir/tests/native/native_probe.py" ]]; then cp "$example_dir/tests/native/native_probe.py" "$fixture_dir/context/"; fi
cp -R "$example_dir/tests/fixtures" "$fixture_dir/context/fixtures"
printf '[pytest]\ntestpaths = .\naddopts = --import-mode=importlib -q\nasyncio_default_fixture_loop_scope = function\n' > "$fixture_dir/context/pytest.ini"
mode=observe
if [[ "${1:-}" == --enforce ]]; then mode=enforce; shift; fi
scenarios=(observe)
dockerfile=Dockerfile
if [[ "$mode" == enforce ]]; then
  dockerfile=Dockerfile.synchronous
  scenarios=("$@")
  if [[ "$#" == 0 ]]; then scenarios=(allow deny pending escalate deferred observe-mode paused observe-deferred paused-deferred grading-failure-allow missing-outcome identity-error http-error timeout); fi
fi
image_tag="watcher-package-${slug}:$(basename "$fixture_dir")"
docker build --iidfile "$fixture_dir/evidence/image.id" --tag "$image_tag" \
  -f "$fixture_dir/context/$dockerfile" "$fixture_dir/context" > "$fixture_dir/build.log" 2>&1
image_id="$(cat "$fixture_dir/evidence/image.id")"
docker image inspect "$image_id" > "$fixture_dir/evidence/image-inspect.json"
if [[ "${WATCHER_EXAMPLE_BUILD_ONLY:-}" == "1" ]]; then
  printf "Prepared native image artifacts: %s\n" "$fixture_dir"
  exit 0
fi
container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then docker rm -f "$container_id" > /dev/null; fi
}
trap cleanup EXIT
failed=0
for scenario in "${scenarios[@]}"; do
  case "$scenario" in observe|allow|deny|pending|escalate|deferred|observe-mode|paused|observe-deferred|paused-deferred|grading-failure-allow|missing-outcome|identity-error|http-error|timeout) ;; *) exit 2 ;; esac
  evidence_dir="$fixture_dir/evidence/$scenario"
  mkdir -p "$evidence_dir"
  container_id="$(docker create --pull never --network none --cap-drop ALL --security-opt no-new-privileges --read-only \
    --pids-limit 256 --memory 2g --cpus 2 --user "$(id -u):$(id -g)" --env HOME=/home/probe \
    --env "WATCHER_EXAMPLE_SCENARIO=$scenario" --tmpfs /tmp:rw,exec,nosuid,size=512m \
    --tmpfs "/home/probe:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=256m" \
    --mount "type=bind,source=$evidence_dir,target=/evidence" "$image_id")"
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
  printf '%s: exit %s\n' "$scenario" "$container_status"
  if [[ "$container_status" != 0 ]]; then failed=1; fi
done
exit "$failed"
