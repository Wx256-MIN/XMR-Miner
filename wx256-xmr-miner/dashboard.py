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
NETWORKS_API = "https://api.xmrig.com/1/networks"
NETWORK_CACHE_SECONDS = 10
NETWORK_REFRESH_SECONDS = 10
KRYPTEX_API_TIMEOUT = 8
ROOT = "/dashboard"
CONFIG = "/data/config.json"
MINER = "/opt/xmrig"

COINS = {
    "xmr": {
        "name": "Monero",
        "symbol": "XMR",
        "algorithm": "rx/0",
        "algorithm_name": "RandomX",
        "coin_arg": "monero",
        "wallet_label": "Monero wallet address",
        "wallet_placeholder": "4... or 8...",
    },
    "tari": {
        "name": "Tari",
        "symbol": "XTM",
        "algorithm": "rx/0",
        "algorithm_name": "RandomX (RandomXT)",
        "coin_arg": None,
        "wallet_label": "Tari wallet address",
        "wallet_placeholder": "Tari XTM address",
    },
}

DEFAULT_COIN = "xmr"

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


def get_coin_config(cfg=None):
    cfg = cfg or load_config()
    coin = str(cfg.get("coin", DEFAULT_COIN)).lower()
    return coin if coin in COINS else DEFAULT_COIN


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

    coin = get_coin_config(cfg)
    coin_cfg = COINS[coin]
    stop_miner()

    args = [
        MINER,
        "--url=" + cfg["pool"],
        "--algo=" + coin_cfg["algorithm"],
        "--user=" + cfg["wallet"],
        "--pass=" + cfg.get("worker", "umbrel"),
        "--donate-level=" + str(cfg.get("donate_level", 1)),
        "--http-host=127.0.0.1",
        "--http-port=8080",
        "--print-time=60",
    ]

    if coin_cfg["coin_arg"]:
        args.insert(3, "--coin=" + coin_cfg["coin_arg"])

    threads = int(cfg.get("threads", 0))
    if threads > 0:
        args.append("--threads=" + str(threads))

    with miner_lock:
        miner_process = subprocess.Popen(args, cwd="/data")

    return True, "Mining started"


def fetch_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "Wx256-XMR-Miner/0.4.3", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_summary():
    try:
        return fetch_json(API + "/2/summary", timeout=3)
    except Exception:
        return {}


def fetch_text(url, timeout=8):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Wx256-XMR-Miner/0.4.3",
            "Accept": "text/html,application/xhtml+xml,application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_numeric(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        try:
            number = float(text)
            return number if number > 0 else None
        except ValueError:
            return None
    return None


def find_number(value, keys):
    if isinstance(value, dict):
        for key in keys:
            candidate = parse_numeric(value.get(key))
            if candidate is not None:
                return candidate
        for child in value.values():
            found = find_number(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_number(child, keys)
            if found is not None:
                return found
    return None


def parse_kryptex_difficulty_page(html):
    # Kryptex's public XTM coin page currently renders a human-readable
    # network difficulty such as "40.08 GH". This is a fallback only when
    # the documented JSON API is unavailable or changes response shape.
    import re

    patterns = [
        r"mining difficulty of\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(KH|MH|GH|TH|PH|H)\\b",
        r"difficulty[^0-9]{0,80}([0-9]+(?:\\.[0-9]+)?)\\s*(KH|MH|GH|TH|PH|H)\\b",
    ]
    multipliers = {
        "H": 1,
        "KH": 1_000,
        "MH": 1_000_000,
        "GH": 1_000_000_000,
        "TH": 1_000_000_000_000,
        "PH": 1_000_000_000_000_000,
    }
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1)) * multipliers[match.group(2).upper()]
            if value > 0:
                return value
    return None


def fetch_tari_network(cfg):
    # Kryptex documents /api/v1/net/stats/{coin} as the public endpoint for
    # network hashrate and difficulty. The XTM pool slug is xtm-rx.
    endpoints = [
        "https://pool.kryptex.com/api/v1/net/stats/xtm-rx",
        "https://pool.kryptex.com/api/v1/net/stats/xtm",
        "https://pool.kryptex.com/api/v1/coin/xtm-rx/info",
        "https://pool.kryptex.com/api/v1/coin/xtm/info",
        "https://pool.kryptex.com/xtm-rx/about-coin",
    ]

    last_error = None
    for endpoint in endpoints:
        try:
            if endpoint.endswith("about-coin"):
                difficulty = parse_kryptex_difficulty_page(
                    fetch_text(endpoint, timeout=KRYPTEX_API_TIMEOUT)
                )
                if difficulty is not None:
                    return {
                        "difficulty": difficulty,
                        "height": None,
                        "algo": "rx/0",
                        "source": "kryptex-page",
                    }
                last_error = "Kryptex about-coin page did not contain a parseable difficulty"
                continue

            data = fetch_json(endpoint, timeout=KRYPTEX_API_TIMEOUT)
            difficulty = find_number(
                data,
                (
                    "difficulty",
                    "network_difficulty",
                    "networkDifficulty",
                    "networkDiff",
                    "difficulty_current",
                    "difficultyCurrent",
                ),
            )
            height = find_number(
                data,
                ("height", "network_height", "networkHeight", "block_height", "blockHeight"),
            )
            if difficulty is not None:
                return {
                    "difficulty": difficulty,
                    "height": height,
                    "algo": "rx/0",
                    "source": "kryptex-api",
                }
            last_error = "Kryptex API returned no difficulty field"
        except Exception as e:
            last_error = str(e)

    return None

