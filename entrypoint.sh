#!/bin/sh
set -eu

: "${XMR_POOL:?XMR_POOL is required}"
: "${XMR_WALLET:?XMR_WALLET is required}"

WORKER="${XMR_WORKER:-umbrel}"
THREADS="${XMR_THREADS:-0}"
DONATE="${XMR_DONATE_LEVEL:-1}"

mkdir -p /data

set -- --url="$XMR_POOL" --user="$XMR_WALLET" --pass="$WORKER" --donate-level="$DONATE" --http-host=0.0.0.0 --http-port=8080 --print-time=60

if [ "$THREADS" != "0" ]; then
  set -- "$@" "--threads=$THREADS"
fi

exec /opt/xmrig/xmrig "$@"
