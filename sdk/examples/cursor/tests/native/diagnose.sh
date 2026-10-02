#!/usr/bin/env bash
# Diagnose the pinned standalone CLI without credentials, host config or outbound runtime access.
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
diagnostic_dir="$(mktemp -d "${TMPDIR:-/tmp}/watcher-cursor-contained.XXXXXX")"
mkdir -p "$diagnostic_dir/context" "$diagnostic_dir/evidence"
package_url="https://downloads.cursor.com/lab/2026.09.10-fd3934a/linux/x64/agent-cli-package.tar.gz"
curl --fail --location --silent --show-error --max-time 180 "$package_url" \
  --output "$diagnostic_dir/context/agent-cli-package.tar.gz"
python3 -c 'import hashlib,pathlib,sys; path=pathlib.Path(sys.argv[1]); digest=hashlib.sha256(path.read_bytes()).hexdigest(); assert digest == "27997c8391ad853a5a732b1845db8ef82a8ba6afb0f7829cc739464f8966e96e", digest; print(digest)' \
  "$diagnostic_dir/context/agent-cli-package.tar.gz" > "$diagnostic_dir/evidence/package-sha256.txt"
cp "$example_dir/tests/native/Dockerfile" "$example_dir/tests/native/run_diagnostic.py" \
  "$example_dir/tests/native/capture_hook.py" "$diagnostic_dir/context/"
image_tag="watcher-example-cursor:$(basename "$diagnostic_dir")"
docker build --platform linux/amd64 --network none --iidfile "$diagnostic_dir/evidence/image.id" \
  --tag "$image_tag" "$diagnostic_dir/context" > "$diagnostic_dir/build.log" 2>&1
image_id="$(cat "$diagnostic_dir/evidence/image.id")"
docker image inspect "$image_id" > "$diagnostic_dir/evidence/image-inspect.json"
container_id=""
cleanup() {
  if [ -n "$container_id" ]; then docker rm -f "$container_id" > /dev/null; fi
}
trap cleanup EXIT
container_id="$(docker create --network none --cap-drop ALL --security-opt no-new-privileges --read-only \
  --pids-limit 256 --memory 2g --cpus 2 --user "$(id -u):$(id -g)" \
  --env HOME=/home/probe --env NO_COLOR=1 --env TERM=dumb \
  --tmpfs /tmp:rw,nosuid,size=512m \
  --tmpfs "/home/probe:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=256m" \
  --tmpfs "/workspace:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=128m" \
  --mount "type=bind,source=$diagnostic_dir/evidence,target=/evidence" "$image_id")"
docker inspect "$container_id" > "$diagnostic_dir/evidence/container-before.json"
printf 'Cursor CLI diagnostic artifacts: %s\n' "$diagnostic_dir"
docker start --attach "$container_id" > "$diagnostic_dir/evidence/run.log" 2>&1
docker inspect "$container_id" > "$diagnostic_dir/evidence/container-after.json"
container_status="$(docker inspect --format '{{.State.ExitCode}}' "$container_id")"
docker rm "$container_id" > /dev/null
container_id=""
if [ -f "$diagnostic_dir/evidence/summary.json" ]; then cat "$diagnostic_dir/evidence/summary.json"; fi
exit "$container_status"
