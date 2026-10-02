#!/usr/bin/env bash
# Run a local fixture with loopback networking, a fresh home and the caller's UID.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: run-without-network.sh COMMAND [ARG ...]" >&2
  exit 2
fi

fixture_home="$(mktemp -d "${TMPDIR:-/tmp}/watcher-sdk-fixture-home.XXXXXX")"

exec sudo --non-interactive --preserve-env=PATH,HOME,JAVA_HOME,JAVA_BIN,UV_CACHE_DIR \
  unshare --net -- bash -euo pipefail -c '
    ip link set lo up
    test "$(ip -o link show | wc -l)" -eq 1
    test -z "$(ip route show default)"
    fixture_home="$1"
    shift
    exec setpriv --reuid="$SUDO_UID" --regid="$SUDO_GID" --init-groups -- \
      env HOME="$fixture_home" XDG_CONFIG_HOME="$fixture_home/.config" \
      XDG_CACHE_HOME="$fixture_home/.cache" XDG_DATA_HOME="$fixture_home/.local/share" \
      XDG_STATE_HOME="$fixture_home/.local/state" "$@"
  ' isolated-fixture "$fixture_home" "$@"
