#!/bin/sh
set -eu

: "${XMR_POOL:?XMR_POOL is required}
: "${XMR_WALLET:?XMR_WALLET is required}

WORKER="${XMR_WORKER:-umbrel}"
THREADS="${XMR_THREADS:-0}"
DONATE="${XMR_DONATE_LEVEL:-1}"

case "$THREADS" in ''|*[!0-9]*) echo "XMR_THREADS must be 0 or a positive integer" >&2; exit 1 ;; esac
case "$DONATE" in ''|*[!0-9]*) echo "XMR_DONATE_LEVEL must be a non-negative integer" >&2; exit 1 ;; esac

if [ ! -x /opt/xmrig ]; then echo "XMRig binary is missing" >&2; exit 1; fi
mkdir -p /data
chown 10001:10001 /data 2>/dev/null || true

/opt/xmrig --url="$XMR_POOL" --user="$XMR_WALLET" --pass="$WORKER" --donate-level="$DONATE" --http-host=127.0.0.1 --http-port=8080 --print-time=60 $( [ "$THREADS" != "0" ] && printf '%s' "--threads=$THREADS" ) &
MINER_PID=$!

su -s /bin/sh -c 'python3 /dashboard.py' xmrig &
WEB_PID=$!

trap 'kill "$MINER_PID" "$WEB_PID" 2>/dev/null || true; wait "$MINER_PID" 2>/dev/null || true' INT TERM EXIT
wait "$MINER_PID"