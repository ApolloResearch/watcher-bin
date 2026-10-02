#!/usr/bin/env bash
# Prepare dependencies before executing native fixtures without external networking.
set -euo pipefail
example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
slug="$(basename "$example_dir")"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
run_dir="$(mktemp -d "$run_parent/watcher-${slug}.XXXXXX")"
mkdir -p "$run_dir/context" "$run_dir/dist" "$run_dir/evidence"
printf 'Fixture artifacts: %s\n' "$run_dir"
python_project="$example_dir"
if [[ "$slug" == openclaw ]]; then python_project="$example_dir/packages/python"; fi
sdk_wheel="${WATCHER_SDK_WHEEL:-}"
if [[ -z "$sdk_wheel" ]]; then
  uv build "$example_dir/../.." --wheel --out-dir "$run_dir/dist"
  sdk_wheel="$(compgen -G "$run_dir/dist/watcher_sdk-*.whl")"
fi
cp "$sdk_wheel" "$run_dir/context/"
uv build "$python_project" --wheel --out-dir "$run_dir/context"
uv export --project "$python_project" --frozen --no-emit-project --no-emit-package watcher-sdk \
  --format requirements-txt --output-file "$run_dir/context/requirements.txt" > "$run_dir/export.log"
cp "$example_dir/tests/native/upstream/"* "$run_dir/context/"
for asset in "$example_dir"/tests/native/contained/*; do
  if [[ -f "$asset" ]]; then cp "$asset" "$run_dir/context/"; fi
done
cp "$example_dir/tests/"test_*.py "$run_dir/context/"
mkdir -p "$run_dir/context/tests"
cp "$example_dir/tests/test_bridge.mjs" "$run_dir/context/tests/"
if [[ -d "$example_dir/tests/fixtures" ]]; then cp -R "$example_dir/tests/fixtures" "$run_dir/context/fixtures"; fi
if [[ "$slug" == openclaw ]]; then
  npm pack "$example_dir/packages/node" --pack-destination "$run_dir/dist" --ignore-scripts > "$run_dir/pack.log"
  cp "$run_dir"/dist/*.tgz "$run_dir/context/"
  mkdir -p "$run_dir/context/packages/node"
  tar -xf "$run_dir"/dist/*.tgz --strip-components=1 -C "$run_dir/context/packages/node"
fi
printf '%s\n' "$slug" > "$run_dir/context/slug.txt"
docker build --iidfile "$run_dir/image.id" --tag "watcher-example-$slug:$(basename "$run_dir")" \
  "$run_dir/context" > "$run_dir/build.log" 2>&1
image_id="$(cat "$run_dir/image.id")"
docker image inspect "$image_id" > "$run_dir/image-inspect.json"
if [[ "${WATCHER_EXAMPLE_BUILD_ONLY:-0}" == 1 ]]; then exit 0; fi
container_id=""
cleanup() { if [[ -n "$container_id" ]]; then docker rm -f "$container_id" >/dev/null; fi; }
trap cleanup EXIT
scenarios=(observe allow deny pending escalate deferred paused http-error timeout)
if [[ "$slug" == github-copilot-cli ]]; then scenarios+=(outer-timeout); else scenarios+=(missing-outcome identity-error no-context-access rewrite outer-timeout delayed-allow); fi
if [[ "$#" -gt 0 ]]; then scenarios=("$@"); fi
failed=0
for scenario in "${scenarios[@]}"; do
  case "$scenario" in observe|allow|deny|pending|escalate|deferred|paused|http-error|timeout|outer-timeout|missing-outcome|identity-error|no-context-access|rewrite|delayed-allow) ;; *) exit 2 ;; esac
  evidence_dir="$run_dir/evidence/$scenario"
  mkdir -p "$evidence_dir"
  container_id="$(docker create --pull never --network none --cap-drop ALL --security-opt no-new-privileges --read-only \
    --pids-limit 512 --memory 3g --cpus 2 --user "$(id -u):$(id -g)" --env HOME=/home/probe \
    --env "WATCHER_EXAMPLE_SCENARIO=$scenario" --tmpfs /tmp:rw,exec,nosuid,size=1g \
    --tmpfs "/home/probe:rw,exec,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=512m" \
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
  docker rm "$container_id" >/dev/null
  container_id=""
  printf '%s: exit %s\n' "$scenario" "$container_status"
  if [[ "$container_status" != 0 ]]; then failed=1; fi
done
exit "$failed"
