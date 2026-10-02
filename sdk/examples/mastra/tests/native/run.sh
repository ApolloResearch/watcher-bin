#!/usr/bin/env bash
# Build both components, install them outside the checkout, then run isolated fixtures.
set -euo pipefail

example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
run_dir="$(mktemp -d "$run_parent/watcher-mastra-packages.XXXXXX")"
printf 'Mastra artifact test directory: %s\n' "$run_dir"
mkdir -p "$run_dir/dist" "$run_dir/installed"

sdk_wheel="${WATCHER_SDK_WHEEL:-}"
if [[ -z "$sdk_wheel" ]]; then
  uv build "$example_dir/../.." --wheel --out-dir "$run_dir/dist"
  sdk_wheels=("$run_dir"/dist/watcher_sdk-*.whl)
  test "${#sdk_wheels[@]}" -eq 1
  sdk_wheel="${sdk_wheels[0]}"
  test -f "$sdk_wheel"
fi
test -f "$sdk_wheel"
uv build "$example_dir/packages/python" --wheel --out-dir "$run_dir/dist"
uv export --project "$example_dir/packages/python" --frozen --no-emit-project \
  --no-emit-package watcher-sdk --format requirements-txt --output-file "$run_dir/requirements.txt"
uv venv --python 3.12 "$run_dir/venv"
uv pip install --python "$run_dir/venv/bin/python" --require-hashes --no-deps -r "$run_dir/requirements.txt"
uv pip install --python "$run_dir/venv/bin/python" --no-deps \
  "$sdk_wheel" "$run_dir/dist/watcher_mastra_bridge-0.1.0-py3-none-any.whl"
uv pip check --python "$run_dir/venv/bin/python"

npm pack "$example_dir/packages/node" --pack-destination "$run_dir/dist" --ignore-scripts
node "$example_dir/tests/native/install-node-package.mjs" \
  "$example_dir/packages/node/package.json" "$example_dir/packages/node/package-lock.json" \
  "$run_dir/dist/watcher-mastra-example-0.1.0.tgz" "$run_dir/installed"
cp -R "$example_dir/tests" "$run_dir/installed/tests"
mkdir "$run_dir/installed/tests/native/_test_support"
cp "$example_dir/../_test_support/readback.py" "$run_dir/installed/tests/native/_test_support/"
sha256sum "$run_dir/installed/tests/native/_test_support/readback.py" > "$run_dir/test-support-sha256.txt"
cp -R "$example_dir/packages/python/tests" "$run_dir/installed/python-tests"
cp -R "$example_dir/packages/node/tests" "$run_dir/installed/node-tests"
cp "$example_dir/pytest.ini" "$run_dir/installed/pytest.ini"
mkdir -p "$run_dir/installed/reports"
cp "$run_dir/installed/locked-node-install.json" "$run_dir/installed/reports/locked-node-install.json"
if [[ "${WATCHER_EXAMPLE_BUILD_ONLY:-}" == "1" ]]; then
  printf "Prepared installed artifacts: %s\n" "$run_dir"
  exit 0
fi
cd "$run_dir/installed"

# The shared namespace wrapper leaves only loopback available to native fixtures.
isolate="$example_dir/../run-without-network.sh"
env -i PATH="$PATH" "$isolate" node --test --test-reporter=junit \
  --test-reporter-destination="$run_dir/installed/reports/node.xml" node-tests/test_*.mjs
env -i PATH="$PATH" "$isolate" "$run_dir/venv/bin/python" -m pytest --noconftest -c pytest.ini \
  python-tests tests --junitxml="$run_dir/installed/reports/python.xml"
"$run_dir/venv/bin/python" -c \
  'import watcher_mastra_bridge; print("Installed bridge:", watcher_mastra_bridge.__file__)'
node --input-type=module -e \
  'console.log("Installed Node adapter:", import.meta.resolve("watcher-mastra-example/monitoring"))'
printf 'Retained artifact test reports: %s\n' "$run_dir/installed/reports"

"$run_dir/venv/bin/python" - "$run_dir" "$sdk_wheel" <<'PYTHON'
import hashlib,importlib.metadata,json,platform,subprocess,sys
from pathlib import Path
root,sdk=map(Path,sys.argv[1:])
environment={'platform':platform.platform(),'runtimes':{'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip()},'upstream_versions':{name:json.loads((root/'installed/node_modules'/name/'package.json').read_text())['version'] for name in ['@mastra/core','ai','zod']},'watcher_sdk':{'version':importlib.metadata.version('watcher-sdk'),'revision':None,'artifact_sha256':hashlib.sha256(sdk.read_bytes()).hexdigest()}}
(root/'installed/reports/environment.json').write_text(json.dumps(environment,indent=2)+'\n')
PYTHON
