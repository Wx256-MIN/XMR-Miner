#!/bin/sh
set -eu

if [ ! -x /opt/xmrig ]; then echo "XMRig binary is missing" >&2; exit 1; fi
mkdir -p /data
chmod 700 /data 2>/dev/null || true
exec python3 /dashboard.py
