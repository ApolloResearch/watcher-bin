#!/usr/bin/env bash
set -euo pipefail
runner_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$runner_dir/run-contained.sh"
bash "$runner_dir/run-synchronous-contained.sh"
