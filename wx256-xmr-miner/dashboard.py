#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = "http://127.0.0.1:8080"
NETWORK_API = "https://api.xmrig.com/1/network/XMR"
ROOT = "/dashboard"
CONFIG = "/data/config.json"
MINER = "/opt/xmrig"

miner_lock = threading.Lock()
miner_process = None
network_cache = {"ts": 0.0, "data": {}}
network_lock = threading.Lock()


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(cfg):
    os.makedirs("/data", exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG)


def miner_running():
    return miner_process is not None and miner_process.poll() is None


def stop_miner():
    global miner_process
    with miner_lock:
        if miner_process and miner_process.poll() is None:
            miner_process.terminate()
            try:
                miner_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                miner_process.kill()
                miner_process.wait(timeout=5)
        miner_process = None


def start_miner():
    global miner_process
    cfg = load_config()
    if not cfg.get("pool") or not cfg.get("wallet"):
        return False, "Pool URL and wallet address are required"

    stop_miner()

    args = [
        MINER,
        "--url=" + cfg["pool"],
        "--user=" + cfg["wallet"],
        "--pass=" + cfg.get("worker", "umbrel"),
        "--donate-level=" + str(cfg.get("donate_level", 1)),
        "--http-host=127.0.0.1",
        "--http-port=8080",
        "--print-time=60",
    ]

    threads = int(cfg.get("threads", 0))
    if threads > 0:
        args.append("--threads=" + str(threads))

    with miner_lock:
        miner_process = subprocess.Popen(args, cwd="/data")

    return True, "Mining started"


def fetch_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "Wx256-XMR-Miner/0.3.4"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_summary():
    try:
        return fetch_json(API + "/2/summary", timeout=3)
    except Exception:
        return {}


def get_network():
    global network_cache
    now = time.time()
    with network_lock:
        if now - network_cache["ts"] < 30 and network_cache["data"]:
            return network_cache["data"]

        try:
            data = fetch_json(NETWORK_API, timeout=5)
            network_cache = {"ts": now, "data": data}
            return data
        except Exception:
            return network_cache["data"]


def get_stats():
    summary = get_summary()
    network = get_network()

    results = summary.get("results") or {}
    connection = summary.get("connection") or {}
    hashrate = summary.get("hashrate") or {}
    total_hash = hashrate.get("total")
    if isinstance(total_hash, list):
        hash_value = total_hash[0] if total_hash else None
    else:
        hash_value = total_hash

    best_values = results.get("best") or []
    best_numbers = [float(v) for v in best_values if isinstance(v, (int, float)) and v > 0]
    best_diff = max(best_numbers) if best_numbers else None

    accepted = connection.get("accepted")
    if accepted is None:
        accepted = results.get("shares_good")

    rejected = connection.get("rejected")
    if rejected is None:
        shares_total = results.get("shares_total")
        shares_good = results.get("shares_good")
        if isinstance(shares_total, (int, float)) and isinstance(shares_good, (int, float)):
            rejected = max(0, shares_total - shares_good)

    pool_diff = connection.get("diff")
    if pool_diff is None:
        pool_diff = results.get("diff_current")

    network_diff = network.get("difficulty")
    network_height = network.get("height")

    block_candidate = (
        isinstance(best_diff, (int, float))
        and isinstance(network_diff, (int, float))
        and network_diff > 0
        and best_diff >= network_diff
    )

    cfg = load_config()
    return {
        "running": miner_running(),
        "hashrate": hash_value,
        "accepted": accepted,
        "rejected": rejected,
        "uptime": summary.get("uptime"),
        "worker": summary.get("worker_id") or cfg.get("worker", "umbrel"),
        "pool": connection.get("pool") or cfg.get("pool"),
        "pool_diff": pool_diff,
        "best_diff": best_diff,
        "network_difficulty": network_diff,
        "network_height": network_height,
        "block_candidate": block_candidate,
    }


class Handler(BaseHTTPRequestHandler):
    def send(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, code, obj):
        self.send(
            code,
            "application/json; charset=utf-8",
            json.dumps(obj).encode("utf-8"),
        )

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(ROOT + "/index.html", "rb") as f:
                self.send(200, "text/html; charset=utf-8", f.read())
            return

        if self.path == "/favicon.svg":
            with open(ROOT + "/favicon.svg", "rb") as f:
                self.send(200, "image/svg+xml", f.read())
            return

        if self.path == "/api/config":
            cfg = load_config()
            public = cfg.copy()
            if public.get("wallet"):
                public["wallet"] = public["wallet"][:8] + "…" + public["wallet"][-6:]
            self.json_response(
                200,
                {
                    "configured": bool(cfg.get("pool") and cfg.get("wallet")),
                    "config": public,
                    "running": miner_running(),
                },
            )
            return

        if self.path == "/api/stats":
            self.json_response(200, get_stats())
            return

        if self.path.startswith("/2/") or self.path.startswith("/1/"):
            try:
                with urllib.request.urlopen(API + self.path, timeout=5) as r:
                    data = r.read()
                self.send(200, "application/json", data)
            except Exception as e:
                self.send(
                    503,
                    "application/json",
                    json.dumps({"error": str(e)}).encode("utf-8"),
                )
            return

        self.send(404, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self):
        if self.path == "/api/stop":
            stop_miner()
            self.json_response(200, {"ok": True, "message": "Mining stopped"})
            return

        if self.path == "/api/start":
            ok, msg = start_miner()
            self.json_response(200 if ok else 400, {"ok": ok, "message": msg})
            return

        if self.path != "/api/config":
            self.send(404, "text/plain; charset=utf-8", b"Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))

            pool = str(body.get("pool", "")).strip()
            wallet = str(body.get("wallet", "")).strip()
            worker = str(body.get("worker", "umbrel")).strip() or "umbrel"
            threads = int(body.get("threads", 0))
            donate = int(body.get("donate_level", 1))

            if not pool or not wallet:
                raise ValueError("Pool URL and wallet address are required")
            if threads < 0 or donate < 0:
                raise ValueError("Threads and donation level cannot be negative")
            if threads > 1024:
                raise ValueError("CPU threads value is too high")
            if donate > 100:
                raise ValueError("Donation level must be between 0 and 100")

            save_config(
                {
                    "pool": pool,
                    "wallet": wallet,
                    "worker": worker,
                    "threads": threads,
                    "donate_level": donate,
                }
            )

            ok, msg = start_miner()
            self.json_response(200 if ok else 500, {"ok": ok, "message": msg})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.json_response(400, {"ok": False, "message": str(e)})

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
