#!/usr/bin/env bash
# Download dependencies first, then query real services in network-disabled namespaces.
set -euo pipefail
example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
run_parent="${WATCHER_EXAMPLE_RUN_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$run_parent"
run_dir="$(mktemp -d "$run_parent/watcher-otlp-services.XXXXXX")"
printf 'Service fixture artifacts: %s\n' "$run_dir"
mkdir "$run_dir/source"
cp "$example_dir/tests/native/verify_services.py" "$run_dir/source/"
cp -R "$example_dir/tests/native/services" "$run_dir/source/"
sha256sum "$run_dir/source/verify_services.py" "$run_dir/source/services/"* > "$run_dir/source/SHA256SUMS"
selected="${WATCHER_OTLP_DESTINATION:-all}"
[[ "$selected" == all || "$selected" == loki || "$selected" == opensearch ]]
real_source="${WATCHER_OTLP_REAL_SOURCE:-0}"
[[ "$real_source" == 0 || "$real_source" == 1 ]]
if [[ "$real_source" == 1 ]]; then
  [[ -n "${WATCHER_OTLP_RELAY_DIR:-}" && -n "${WATCHER_OTLP_HELPER_DIR:-}" ]]
  [[ -f "${WATCHER_OTLP_INPUT:-}" && -n "${WATCHER_OTLP_FIXTURE_IMAGE:-}" ]]
  # The optional live-Watcher harness supplies a standalone stdlib relay.
  cp "$WATCHER_OTLP_HELPER_DIR/native.py" "$run_dir/source/relay.py"
  sha256sum "$run_dir/source/relay.py" >> "$run_dir/source/SHA256SUMS"
fi
fixture_image="${WATCHER_OTLP_FIXTURE_IMAGE:-}"
if [[ -z "$fixture_image" ]]; then
  mkdir "$run_dir/preparation"
  WATCHER_EXAMPLE_RUN_DIR="$run_dir/preparation" bash "$example_dir/tests/native/run.sh" > "$run_dir/preparation.log" 2>&1
  images=("$run_dir"/preparation/watcher-opentelemetry.*/image.id)
  [[ "${#images[@]}" == 1 ]]
  fixture_image="$(cat "${images[0]}")"
fi
docker image inspect "$fixture_image" > "$run_dir/fixture-image.json"
loki_image='grafana/loki@sha256:31628519045e7f28692a7ae73b4a3fd293dccb425585ed5d16ceea3b5c9592e6'
search_image='opensearchproject/opensearch@sha256:e96cc6ae1500a073d973c0906f30f7cf4d9c461f32f855f9242a2da933660cdd'
prepper_image='opensearchproject/data-prepper@sha256:45d644fe7ec1724866d22e8c5cb5ddca9f963a4c5ecff872048e93c45de001df'
containers=()
cleanup() {
  local run_status=$? cleanup_status=0 remove_status inspect_status
  trap - EXIT
  for container in "${containers[@]}"; do
    docker logs "$container" > "$run_dir/$container.log" 2>&1 || true
    docker inspect "$container" > "$run_dir/$container.json" 2>&1 || true
    if docker rm -f "$container" > "$run_dir/$container.remove.log" 2>&1; then
      remove_status=0
    else
      remove_status=$?
      cleanup_status=1
    fi
    if docker inspect "$container" > "$run_dir/$container.removed.json" 2> "$run_dir/$container.removed.stderr"; then
      inspect_status=0
      cleanup_status=1
    else
      inspect_status=$?
    fi
    printf '%s\t%s\t%s\n' "$container" "$remove_status" "$inspect_status" >> "$run_dir/removal-receipts.tsv"
  done
  if [[ "$run_status" == 0 && "$cleanup_status" != 0 ]]; then run_status=1; fi
  exit "$run_status"
}
trap cleanup EXIT
run_probe() {
  local destination="$1" namespace="$2" probe result
  local -a options=() command=(python /fixture/tests/native/verify_services.py "$destination")
  mkdir -p "$run_dir/$destination"
  if [[ "$real_source" == 1 ]]; then
    cp "$WATCHER_OTLP_INPUT" "$run_dir/$destination/input.json"
    options+=(--user "$(id -u):$(id -g)" --env HOME=/home/probe --env WATCHER_OTLP_REAL_SOURCE=1 --env WATCHER_NATIVE_TIMEOUT_SECONDS=360
      --tmpfs "/home/probe:rw,nosuid,uid=$(id -u),gid=$(id -g),mode=0700,size=64m"
      --mount "type=bind,source=$run_dir/$destination,target=/evidence"
      --mount "type=bind,source=$WATCHER_OTLP_RELAY_DIR,target=/watcher,readonly"
      --mount "type=bind,source=$run_dir/source/relay.py,target=/probe/native.py,readonly")
    command=(python /probe/native.py python /fixture/tests/native/verify_services.py "$destination")
  fi
  probe="$(docker create --pull never --network "container:$namespace" --cap-drop ALL \
    --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 1 \
    --mount "type=bind,source=$run_dir/source/verify_services.py,target=/fixture/tests/native/verify_services.py,readonly" \
    "${options[@]}" "$fixture_image" "${command[@]}")"
  containers+=("$probe")
  printf '%s\n' "$probe" >> "$run_dir/container-ids.txt"
  docker inspect "$probe" > "$run_dir/$destination/container-before.json"
  set +e
  docker start --attach "$probe" > "$run_dir/$destination/run.log" 2>&1
  set -e
  result="$(docker inspect --format '{{.State.ExitCode}}' "$probe")"
  docker inspect "$probe" > "$run_dir/$destination/container-after.json"
  if [[ "$real_source" == 0 ]]; then docker cp "$probe:/evidence/." "$run_dir/$destination/"; fi
  printf '%s\n' "$result" > "$run_dir/$destination/exit.txt"
  [[ "$(docker inspect --format '{{.State.Running}}' "$probe")" == false ]]
  if [[ "$result" != 0 ]]; then
    exit "$result"
  fi
  [[ -f "$run_dir/$destination/result.json" ]]
}
# Only one destination stack runs at a time; the JVM services have explicit heaps.
if [[ "$selected" == all || "$selected" == loki ]]; then
docker pull "$loki_image" > "$run_dir/pull-loki.log" 2>&1
docker image inspect "$loki_image" > "$run_dir/loki-image.json"
loki="$(docker create --pull never --network none --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 768m --cpus 1 \
  --mount "type=bind,source=$run_dir/source/services/loki.yaml,target=/etc/loki/fixture.yaml,readonly" \
  "$loki_image" -config.file=/etc/loki/fixture.yaml)"
containers+=("$loki")
printf '%s\n' "$loki" >> "$run_dir/container-ids.txt"
docker start "$loki" > /dev/null
run_probe loki "$loki"
docker stop --time 10 "$loki" > /dev/null
fi

if [[ "$selected" == all || "$selected" == opensearch ]]; then
docker pull "$search_image" > "$run_dir/pull-opensearch.log" 2>&1
docker pull "$prepper_image" > "$run_dir/pull-data-prepper.log" 2>&1
docker image inspect "$search_image" "$prepper_image" > "$run_dir/opensearch-images.json"
search="$(docker create --pull never --network none --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 512 --memory 1536m --cpus 1 --ulimit nofile=65536:65536 \
  -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true -e DISABLE_INSTALL_DEMO_CONFIG=true \
  -e 'OPENSEARCH_JAVA_OPTS=-Xms384m -Xmx384m' \
  "$search_image")"
containers+=("$search")
printf '%s\n' "$search" >> "$run_dir/container-ids.txt"
docker start "$search" > /dev/null
prepper="$(docker create --pull never --network "container:$search" --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 768m --cpus 1 -e 'JAVA_OPTS=-Xms128m -Xmx384m' \
  --mount "type=bind,source=$run_dir/source/services/pipelines.yaml,target=/usr/share/data-prepper/pipelines/pipelines.yaml,readonly" \
  --mount "type=bind,source=$run_dir/source/services/data-prepper-config.yaml,target=/usr/share/data-prepper/config/data-prepper-config.yaml,readonly" \
  "$prepper_image")"
containers+=("$prepper")
printf '%s\n' "$prepper" >> "$run_dir/container-ids.txt"
docker start "$prepper" > /dev/null
run_probe opensearch "$search"
fi
