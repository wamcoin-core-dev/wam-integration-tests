#!/usr/bin/env bash
# Requires an already provisioned Python, libevent and reviewed WAM daemon.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "Usage: scripts/run_isolated_linux.sh WAMD_PATH BINARY_SHA256 NEW_REPORT_DIR" >&2
  exit 2
fi
wam_binary="$1"
wam_digest="$2"
wam_reports="$3"
wam_python="$(command -v python3)"
# This wrapper fails if namespace creation is denied; it does not silently fall back.
# Both nodes and every HTTP test share only the namespace's loopback interface.
exec unshare --user --map-root-user --net -- bash -c '
  set -euo pipefail
  ip link set lo up
  exec "$1" -m wam_it regtest --wamd "$2" --sha256 "$3" --report-dir "$4"
' _ "$wam_python" "$wam_binary" "$wam_digest" "$wam_reports"
