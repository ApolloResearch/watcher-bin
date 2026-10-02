#!/usr/bin/env bash
# Build an API-only native fixture and plugin from one verified upstream archive.
# The embedded page is upstream's source index; this test binary has no built UI.
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
build_dir="${WATCHER_BIFROST_BUILD_DIR:-$(mktemp -d /tmp/watcher-bifrost-build.XXXXXX)}"
mkdir -p "$build_dir"
build_dir="$(cd -- "$build_dir" && pwd)"
revision=048492cff9cf451baf7bfcb13bc0342383788f15
archive="$build_dir/bifrost.tar.gz"
archive_hash=841354245484817867ded681c90e4d8dd1719db612d90ec1ee0a667290ba2da8
if [ ! -f "$archive" ]; then
  curl --fail --location --output "$archive" "https://codeload.github.com/maximhq/bifrost/tar.gz/$revision"
fi
printf '%s  %s\n' "$archive_hash" "$archive" | sha256sum --check --status
if [ "$(go env GOVERSION)" != go1.27.0 ]; then
  echo 'This pinned source requires Go 1.27.0 for both gateway and plugin.' >&2
  exit 2
fi
source_dir="$build_dir/source"
if [ ! -d "$source_dir" ]; then
  mkdir "$source_dir"
  tar --extract --gzip --file "$archive" --directory "$source_dir" --strip-components=1
fi
plugin_dir="$build_dir/watcher-plugin"
mkdir -p "$plugin_dir" "$build_dir/bin" "$source_dir/transports/bifrost-http/ui"
cp "$example_dir/gateway/main.go" "$example_dir/gateway/main_test.go" "$plugin_dir/"
cp "$source_dir/ui/index.html" "$source_dir/transports/bifrost-http/ui/index.html"
cat > "$plugin_dir/go.mod" <<'EOF'
module watcher-bifrost-example

go 1.27.0

require github.com/maximhq/bifrost/core v1.10.2
EOF
export GOMAXPROCS=2 GOMEMLIMIT=1500MiB CGO_ENABLED=1 GOTOOLCHAIN=local
export GOCACHE="$build_dir/go-cache" GOMODCACHE="$build_dir/go-modules"
modules=("$source_dir/core" "$source_dir/framework" "$source_dir/transports" "$plugin_dir")
for module in "$source_dir"/plugins/*/go.mod; do modules+=("$(dirname -- "$module")"); done
workspace="$build_dir/go.work"
if [ ! -f "$workspace" ]; then
  (cd "$build_dir" && GOWORK=off go work init "${modules[@]}")
fi
export GOWORK="$workspace"
(cd "$source_dir/transports/bifrost-http" && go build -buildvcs=false -p 2 -trimpath -o "$build_dir/bin/bifrost-http" .)
(cd "$plugin_dir" && go build -buildvcs=false -p 2 -trimpath -buildmode=plugin -o "$build_dir/bin/watcher.so" .)
(cd "$plugin_dir" && go test -c -buildvcs=false -p 2 -trimpath -o "$build_dir/bin/watcher-tests" .)
go version -m "$build_dir/bin/bifrost-http" > "$build_dir/gateway-build-info.txt"
go version -m "$build_dir/bin/watcher.so" > "$build_dir/plugin-build-info.txt"
sha256sum "$archive" "$build_dir/bin/bifrost-http" "$build_dir/bin/watcher.so" "$build_dir/bin/watcher-tests" > "$build_dir/sha256.txt"
printf 'BIFROST_BINARY=%s\nBIFROST_PLUGIN=%s\n' "$build_dir/bin/bifrost-http" "$build_dir/bin/watcher.so"
