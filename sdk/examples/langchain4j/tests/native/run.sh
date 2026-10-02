#!/usr/bin/env bash
# Exercise installed artifacts outside the checkout, with loopback-only fixture networking.
set -euo pipefail
example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
slug="$(basename "$example_dir")"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
run_dir="$(mktemp -d "$run_parent/watcher-${slug}-packages.XXXXXX")"
mkdir -p "$run_dir/dist" "$run_dir/installed/reports"
printf 'Installed-artifact test directory: %s\n' "$run_dir"
sdk_wheel="${WATCHER_SDK_WHEEL:-}"
if [[ -z "$sdk_wheel" ]]; then
  uv build "$example_dir/../.." --wheel --out-dir "$run_dir/dist"
  sdk_wheels=("$run_dir"/dist/watcher_sdk-*.whl)
  test "${#sdk_wheels[@]}" -eq 1
  sdk_wheel="${sdk_wheels[0]}"
  test -f "$sdk_wheel"
fi
uv build "$example_dir/packages/python" --wheel --out-dir "$run_dir/dist"
uv export --project "$example_dir/packages/python" --frozen --no-emit-project \
  --no-emit-package watcher-sdk --format requirements-txt --output-file "$run_dir/requirements.txt" > "$run_dir/export.log"
uv venv --python 3.12 "$run_dir/venv"
uv pip install --python "$run_dir/venv/bin/python" --require-hashes --no-deps -r "$run_dir/requirements.txt"
uv pip install --python "$run_dir/venv/bin/python" --no-deps \
  "$sdk_wheel" "$run_dir"/dist/watcher_*_bridge-*.whl
uv pip check --python "$run_dir/venv/bin/python"
cp -R "$example_dir/tests" "$run_dir/installed/tests"
cp "$example_dir/pytest.ini" "$run_dir/installed/pytest.ini"
if [[ -d "$example_dir/packages/java" ]]; then
  mvn -q -f "$example_dir/packages/java/pom.xml" package dependency:copy-dependencies \
    "-DoutputDirectory=$run_dir/installed/java/lib"
  mkdir -p "$run_dir/installed/java/lib"
  cp "$example_dir"/packages/java/target/*.jar "$run_dir/installed/java/lib/"
fi
cd "$run_dir/installed"
isolate="$example_dir/../run-without-network.sh"
fixture_path="$run_dir/installed/node_modules/.bin:$PATH"
java_bin="${JAVA_BIN:-$(command -v java || true)}"
if [[ "$slug" == langchain4j ]]; then
  env -i PATH="$fixture_path" TERM=dumb "$isolate" env JAVA_BIN="$java_bin" \
    WATCHER_JAVA_CLASSPATH="$run_dir/installed/java/lib/*" \
    "$run_dir/venv/bin/python" -m pytest --noconftest -c pytest.ini tests --junitxml=reports/python.xml
else
  env -i PATH="$fixture_path" TERM=dumb "$isolate" \
    "$run_dir/venv/bin/python" -m pytest --noconftest -c pytest.ini tests --junitxml=reports/python.xml
fi
if [[ -f tests/test_plugin.mjs ]]; then
  env -i PATH="$fixture_path" TERM=dumb "$isolate" node --test --test-reporter=junit \
    --test-reporter-destination=reports/node.xml tests/test_plugin.mjs
fi
if [[ "$slug" == roo-code ]]; then
  node --check node_modules/watcher-roo-example/src/extension.cjs
fi
"$run_dir/venv/bin/python" - "$slug" "$run_dir" "$sdk_wheel" <<'PY'
import hashlib,importlib.metadata,json,os,platform,subprocess,sys,zipfile
from pathlib import Path
slug,root,sdk=sys.argv[1:];root=Path(root)
receipt={'slug':slug,'python':platform.python_version(),'watcher_sdk':importlib.metadata.version('watcher-sdk'),
         'sdk_revision':None,'sdk_wheel_sha256':hashlib.sha256(Path(sdk).read_bytes()).hexdigest(),
         'python_distributions':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
         'artifact_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'dist').iterdir() if p.suffix in {'.whl','.tgz'}},
         'run_directory':str(root)}
if (root/'installed/node_modules').is_dir():
 receipt['node']=subprocess.check_output(['node','--version'],text=True).strip()
 receipt['node_distributions']={str(p.parent.relative_to(root/'installed/node_modules')):json.loads(p.read_text()).get('version') for p in (root/'installed/node_modules').glob('**/package.json') if p.parent.name!='node_modules'}
if (root/'installed/java').is_dir():
 receipt['java_artifacts']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'installed/java/lib').glob('*.jar')}
(root/'installed/reports/installed-versions.json').write_text(json.dumps(receipt,indent=2)+'\n')
environment={'platform':platform.platform(),'runtimes':{'python':platform.python_version()},'upstream_versions':{},'watcher_sdk':{'version':receipt['watcher_sdk'],'revision':receipt['sdk_revision'],'artifact_sha256':receipt['sdk_wheel_sha256']}}
if 'node' in receipt:
 environment['runtimes']['node']=receipt['node']
 environment['upstream_versions']={name:version for name,version in receipt['node_distributions'].items() if name in {'ai','@mastra/core','zod','@cline/core'}}
if slug=='roo-code':environment['upstream_versions']['roo-code']=None
if slug=='langchain4j':
 environment['runtimes']['java']=subprocess.check_output([os.environ.get('JAVA_BIN','java'),'-version'],stderr=subprocess.STDOUT,text=True).strip().splitlines()[0]
 for group,artifact in [('dev.langchain4j','langchain4j-open-ai'),('com.fasterxml.jackson.core','jackson-databind')]:
  jars=list((root/'installed/java/lib').glob(artifact+'-*.jar'))
  assert len(jars)==1
  with zipfile.ZipFile(jars[0]) as jar:
   properties=jar.read(f'META-INF/maven/{group}/{artifact}/pom.properties').decode()
   environment['upstream_versions'][artifact]=next(line.split('=',1)[1] for line in properties.splitlines() if line.startswith('version='))
(root/'installed/reports/environment.json').write_text(json.dumps(environment,indent=2)+'\n')
PY
printf 'Retained artifact test reports: %s\n' "$run_dir/installed/reports"
