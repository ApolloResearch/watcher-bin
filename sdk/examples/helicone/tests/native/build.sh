#!/usr/bin/env bash
# Build the installed receiver fixture; the backend runner owns isolated execution.
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
run_dir="$(mktemp -d "$run_parent/watcher-helicone-receiver.XXXXXX")"
mkdir -p "$run_dir/context/wheels"
printf 'Receiver fixture artifacts: %s\n' "$run_dir"
if [[ -n "${WATCHER_SDK_WHEEL:-}" ]]; then
  cp "$WATCHER_SDK_WHEEL" "$run_dir/context/wheels/"
else
  uv build "$example_dir/../.." --wheel --out-dir "$run_dir/context/wheels"
fi
uv build "$example_dir" --wheel --out-dir "$run_dir/context/wheels"
uv export --project "$example_dir" --frozen --no-emit-project --no-emit-package watcher-sdk \
  --format requirements-txt --output-file "$run_dir/context/requirements.txt" > "$run_dir/export.log"
cp "$example_dir/pyproject.toml" "$example_dir/uv.lock" "$run_dir/context/"
cp -R "$example_dir/tests" "$run_dir/context/tests"
mkdir "$run_dir/context/_test_support"
cp "$example_dir/../_test_support/readback.py" "$run_dir/context/_test_support/"
sha256sum "$run_dir/context/_test_support/readback.py" > "$run_dir/test-support-sha256.txt"
cp "$example_dir/tests/native/probe.py" "$example_dir/tests/native/Dockerfile" "$run_dir/context/"
docker build --iidfile "$run_dir/image.id" "$run_dir/context" > "$run_dir/build.log" 2>&1
image_id="$(cat "$run_dir/image.id")"
docker image inspect "$image_id" > "$run_dir/image-inspect.json"
printf 'Prepared receiver image: %s\n' "$image_id"
