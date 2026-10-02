#!/usr/bin/env bash
# Prepare an installed image; the backend runner owns isolated runtime execution.
set -euo pipefail
native_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$native_dir/build.py"
