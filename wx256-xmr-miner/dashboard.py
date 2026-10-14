#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
import urllib.request
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = "http://127.0.0.1:8080"
NETWORK_API = "https://api.xmrig.com/1/network/XMR"
NETWORKS_API = "https://api.xmrig.com/1/networks"
NETWORK_CACHE_SECONDS = 10
NETWORK_REFRESH_SECONDS = 10
ROOT = "/dashboard"
CONFIG = "/data/config.json"
MINER = "/opt/xmrig"
CPUMINER = "/opt/cpuminer"

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
    "zeph": {
        "name": "Zephyr",
        "symbol": "ZEPH",
        "algorithm": "rx/0",
        "algorithm_name": "RandomX",
        "coin_arg": "zephyr",
        "wallet_label": "Zephyr wallet address",
        "wallet_placeholder": "ZEPH wallet address",
    },
    "ltcdoge": {
        "name": "Litecoin + Dogecoin",
        "symbol": "LTC + DOGE",
        "algorithm": "scrypt",
        "algorithm_name": "Scrypt (merged mining)",
        "coin_arg": None,
        "wallet_label": "Pool username / wallet",
        "wallet_placeholder": "Pool username or wallet address",
    },
}

DEFAULT_COIN = "xmr"

miner_lock = threading.Lock()
miner_process = None
miner_engine = "xmrig"
miner_log_lock = threading.Lock()
miner_logs = []
MAX_MINER_LOG_LINES = 400
scrypt_stats_lock = threading.Lock()
scrypt_stats = {"hashrate": None, "accepted": 0, "rejected": 0, "started_at": None}
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


def get_engine_config(cfg=None):
    cfg = cfg or load_config()
    engine = str(cfg.get("engine", "xmrig")).strip().lower()
    return engine if engine in ("xmrig", "cpuminer-opt") else "xmrig"


def miner_running():
    return miner_process is not None and miner_process.poll() is None


def update_scrypt_stats(line):
    """Parse CPUMiner-opt share and periodic summaries for dashboard metrics."""
    line = re.sub(r"^\[[^\]]+\]\s*", "", str(line).strip())
    with scrypt_stats_lock:
        # Share result format: "5 Accepted 5 S0 R0 B0, 400.092 sec (159ms)".
        share = re.search(
            r"^\d+\s+(?:Accepted|Rejected|Stale)\s+(\d+)\s+S(\d+)\s+R(\d+)\s+B\d+",
            line,
            re.IGNORECASE,
        )
        if share:
            scrypt_stats["accepted"] = int(share.group(1))
            scrypt_stats["rejected"] = int(share.group(3))

        # Periodic session summary lines: "Accepted 37 144 25.1%".
        accepted = re.search(r"^Accepted\s+\d+\s+(\d+)\s+[0-9.]+%", line, re.IGNORECASE)
        if accepted:
            scrypt_stats["accepted"] = int(accepted.group(1))
        rejected = re.search(r"^Rejected\s+\d+\s+(\d+)\s+[0-9.]+%", line, re.IGNORECASE)
        if rejected:
            scrypt_stats["rejected"] = int(rejected.group(1))

        # CPUMiner-opt emits a reference-rate estimate in its early "TTF @"
        # work lines, then emits measured/effective rates in the periodic
        # "Hash rate" summary. Parse both so the dashboard has a rate before
        # the first five-minute summary arrives.
        rate = re.search(
            r"Hash\s+rate\s+([0-9]+(?:\.[0-9]+)?)\s*([kMGT]?)\s*h/s",
            line,
            re.IGNORECASE,
        )
        if not rate:
            rate = re.search(
                r"\bTTF\s*@\s*([0-9]+(?:\.[0-9]+)?)\s*([kMGT]?)\s*h/s",
                line,
                re.IGNORECASE,
            )
        if rate:
            scale = {"": 1, "K": 1_000, "M": 1_000_000, "G": 1_000_000_000, "T": 1_000_000_000_000}
            scrypt_stats["hashrate"] = float(rate.group(1)) * scale.get(rate.group(2).upper(), 1)


def append_miner_log(line):
    line = str(line).rstrip("\r\n")
    # Remove ANSI color/control sequences before displaying miner output.
    line = re.sub(r"\x1b(?:[@-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", line)
    line = line.replace("\x1b", "")
    line = "".join(ch for ch in line if ch == "\t" or ord(ch) >= 32)
    if not line:
        return
    if miner_engine == "cpuminer-opt":
        update_scrypt_stats(line)
    timestamp = time.strftime("%H:%M:%S")
    with miner_log_lock:
        miner_logs.append(f"[{timestamp}] {line}")
        if len(miner_logs) > MAX_MINER_LOG_LINES:
            del miner_logs[:-MAX_MINER_LOG_LINES]


def read_miner_output(process):
    try:
        if process.stdout is None:
            return
        for line in iter(process.stdout.readline, ""):
            append_miner_log(line)
    except Exception as exc:
        append_miner_log("Log reader error: " + str(exc))
    finally:
        try:
            if process.stdout:
                process.stdout.close()
        except Exception:
            pass


def get_miner_logs():
    with miner_log_lock:
        return list(miner_logs)


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
    global miner_process, miner_engine
    cfg = load_config()
    if not cfg.get("pool") or not cfg.get("wallet"):
        return False, "Pool URL and wallet/username are required"

    engine = get_engine_config(cfg)
    coin = get_coin_config(cfg)
    stop_miner()
    with miner_log_lock:
        miner_logs.clear()
    threads = int(cfg.get("threads", 0))

    if engine == "cpuminer-opt":
        if coin != "ltcdoge":
            return False, "CPUMiner-opt currently supports the Litecoin + Dogecoin Scrypt option only"

        pool_url = str(cfg["pool"]).strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", pool_url):
            pool_url = "stratum+tcp://" + pool_url

        username = str(cfg["wallet"]).strip()
        worker = str(cfg.get("worker", "umbrel")).strip()
        # Most Scrypt pools accept account.worker or wallet.worker. If the
        # user already supplied a suffix, do not append another one.
        if worker and "." not in username:
            username += "." + worker
        password = str(cfg.get("pool_password", "1") or "1")

        args = [
            CPUMINER,
            "--algo=scrypt",
            "--url=" + pool_url,
            "--user=" + username,
            "--pass=" + password,
            "--no-color",
        ]
        if threads > 0:
            args.append("--threads=" + str(threads))

        miner_engine = "cpuminer-opt"
        with scrypt_stats_lock:
            scrypt_stats.update({
                "hashrate": None,
                "accepted": 0,
                "rejected": 0,
                "started_at": time.time(),
            })
        append_miner_log("Starting CPUMiner-opt (Scrypt) with pool " + pool_url +
                         " and " + (str(threads) if threads > 0 else "automatic") + " CPU threads.")
    else:
        coin_cfg = COINS[coin]
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
            "--no-color",
        ]
        if coin_cfg["coin_arg"]:
            args.insert(3, "--coin=" + coin_cfg["coin_arg"])
        if threads > 0:
            args.append("--threads=" + str(threads))

        miner_engine = "xmrig"
        append_miner_log("Starting XMRig: " + " ".join(args))

    try:
        with miner_lock:
            miner_process = subprocess.Popen(
                args,
                cwd="/data",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
        threading.Thread(
            target=read_miner_output,
            args=(miner_process,),
            daemon=True,
        ).start()
    except Exception as exc:
        append_miner_log("Failed to start " + ("CPUMiner-opt" if engine == "cpuminer-opt" else "XMRig") + ": " + str(exc))
        miner_process = None
        return False, "Failed to start miner: " + str(exc)

    return True, "Mining started"


def fetch_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "Wx256-XMR-Miner/0.4.9", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_text(url, timeout=5):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Wx256-XMR-Miner/0.4.9",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def get_summary():
    try:
        return fetch_json(API + "/2/summary", timeout=3)
    except Exception:
        return {}


def fetch_tari_network(cfg):
    # Kryptex XTM-RX is the authoritative source requested for Tari
    # network difficulty. The public chart page is the UI source, while
    # Kryptex's public network endpoint supplies the numeric value used
    # by that chart. Never accept pool/share difficulty here.
    import re

    units = {
        "H": 1,
        "KH": 1_000,
        "MH": 1_000_000,
        "GH": 1_000_000_000,
        "TH": 1_000_000_000_000,
        "PH": 1_000_000_000_000_000,
    }

    def normalize(value):
        if isinstance(value, (int, float)) and value >= 1_000_000_000:
            return float(value)
        if isinstance(value, str):
            match = re.search(
                r"([0-9]+(?:\\.[0-9]+)?)\\s*(H|KH|MH|GH|TH|PH)\\b",
                value,
                re.IGNORECASE,
            )
            if match:
                number = float(match.group(1)) * units[match.group(2).upper()]
                return number if number >= 1_000_000_000 else None
            try:
                number = float(value.replace(",", "").strip())
                return number if number >= 1_000_000_000 else None
            except ValueError:
                return None
        return None

    def find_network_difficulty(value, in_difficulty=False):
        if isinstance(value, dict):
            for key, item in value.items():
                key_lower = str(key).lower()
                if "difficulty" in key_lower:
                    found = find_network_difficulty(item, True)
                    if found:
                        return found
                elif in_difficulty:
                    found = find_network_difficulty(item, True)
                    if found:
                        return found
        elif isinstance(value, list):
            for item in value:
                found = find_network_difficulty(item, in_difficulty)
                if found:
                    return found
        elif in_difficulty:
            return normalize(value)
        return None

    # Numeric network data from the same Kryptex source used by the
    # XTM-RX difficulty chart. Try the XTM-RX identifier first.
    endpoints = [
        "https://pool.kryptex.com/api/v1/net/stats/xtm-rx",
        "https://pool.kryptex.com/api/v1/net/stats/xtm",
    ]

    for endpoint in endpoints:
        try:
            data = fetch_json(endpoint, timeout=8)
            difficulty = find_network_difficulty(data)
            if difficulty:
                height = data.get("height") if isinstance(data, dict) else None
                return {
                    "difficulty": difficulty,
                    "height": height,
                    "algo": "rx/0",
                    "source": "kryptex-xtm-rx",
                }
        except Exception:
            pass

    # Kryptex also exposes the XTM-RX difficulty in the server-rendered
    # About XTM page. Use it when the public JSON endpoint is unavailable
    # or changes response shape.
    try:
        html = fetch_text(
            "https://pool.kryptex.com/xtm-rx/about-coin",
            timeout=8,
        )
        text = re.sub(r"<[^>]+>", " ", html)
        marker = "mining difficulty of"
        pos = text.lower().find(marker)
        if pos >= 0:
            tail = text[pos + len(marker):pos + len(marker) + 120]
            match = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)\b",
                tail,
                re.IGNORECASE,
            )
            if match:
                difficulty = float(match.group(1)) * units[match.group(2).upper()]
                if difficulty >= 1_000_000_000:
                    return {
                        "difficulty": difficulty,
                        "height": None,
                        "algo": "rx/0",
                        "source": "kryptex-xtm-rx-about",
                    }
    except Exception:
        pass

    # Finally inspect the difficulty chart page. The chart is normally
    # rendered client-side, so only accept an explicitly embedded value.
    try:
        html = fetch_text(
            "https://pool.kryptex.com/xtm-rx/difficulty",
            timeout=8,
        )
        patterns = [
            r'(?i)"(?:difficulty|networkDifficulty|network_difficulty)"\s*[:=]\s*"?([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)?',
            r'(?i)(?:network[ _-]?difficulty)[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if not match:
                continue
            number = float(match.group(1))
            unit = (match.group(2) or "H").upper()
            difficulty = number * units[unit]
            if difficulty >= 1_000_000_000:
                return {
                    "difficulty": difficulty,
                    "height": None,
                    "algo": "rx/0",
                    "source": "kryptex-xtm-rx-chart",
                }
    except Exception:
        pass

    return None

def fetch_zeph_network(cfg):
    # Kryptex ZEPH difficulty chart is the requested authoritative source.
    # The API provides the live numeric value; About ZEPH is the fallback.
    import re

    units = {"H": 1, "KH": 1_000, "MH": 1_000_000, "GH": 1_000_000_000,
             "TH": 1_000_000_000_000, "PH": 1_000_000_000_000_000}

    def normalize(value):
        if isinstance(value, (int, float)) and value >= 1_000_000_000:
            return float(value)
        if isinstance(value, str):
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)\b",
                              value, re.IGNORECASE)
            if match:
                number = float(match.group(1)) * units[match.group(2).upper()]
                return number if number >= 1_000_000_000 else None
            try:
                number = float(value.replace(",", "").strip())
                return number if number >= 1_000_000_000 else None
            except ValueError:
                return None
        return None

    def find_network_difficulty(value, in_difficulty=False):
        if isinstance(value, dict):
            for key, item in value.items():
                key_lower = str(key).lower()
                if "difficulty" in key_lower:
                    found = find_network_difficulty(item, True)
                    if found:
                        return found
                elif in_difficulty:
                    found = find_network_difficulty(item, True)
                    if found:
                        return found
        elif isinstance(value, list):
            for item in value:
                found = find_network_difficulty(item, in_difficulty)
                if found:
                    return found
        elif in_difficulty:
            return normalize(value)
        return None

    try:
        data = fetch_json("https://pool.kryptex.com/api/v1/net/stats/zeph", timeout=8)
        difficulty = find_network_difficulty(data)
        if difficulty:
            height = data.get("height") if isinstance(data, dict) else None
            return {"difficulty": difficulty, "height": height, "algo": "rx/0",
                    "source": "kryptex-zeph-api"}
    except Exception:
        pass

    try:
        html = fetch_text("https://pool.kryptex.com/zeph/about-coin", timeout=8)
        text = re.sub(r"<[^>]+>", " ", html)
        marker = "mining difficulty of"
        pos = text.lower().find(marker)
        if pos >= 0:
            tail = text[pos + len(marker):pos + len(marker) + 120]
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)\b",
                              tail, re.IGNORECASE)
            if match:
                difficulty = float(match.group(1)) * units[match.group(2).upper()]
                if difficulty >= 1_000_000_000:
                    return {"difficulty": difficulty, "height": None, "algo": "rx/0",
                            "source": "kryptex-zeph-about"}
    except Exception:
        pass

    # Final fallback: only accept explicitly embedded values from the
    # requested chart page, never explanatory unit examples.
    try:
        html = fetch_text("https://pool.kryptex.com/zeph/difficulty", timeout=8)
        patterns = [
            r'(?i)"(?:difficulty|networkDifficulty|network_difficulty)"\s*[:=]\s*"?([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)?',
            r'(?i)(?:network[ _-]?difficulty)[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(H|KH|MH|GH|TH|PH)\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if not match:
                continue
            number = float(match.group(1))
            unit = (match.group(2) or "H").upper()
            difficulty = number * units[unit]
            if difficulty >= 1_000_000_000:
                return {"difficulty": difficulty, "height": None, "algo": "rx/0",
                        "source": "kryptex-zeph-chart"}
    except Exception:
        pass

    return None


def fetch_network():
    cfg = load_config()
    if get_engine_config(cfg) == "cpuminer-opt" or get_coin_config(cfg) == "ltcdoge":
        return None
    if get_coin_config(cfg) == "tari":
        return fetch_tari_network(cfg)
    if get_coin_config(cfg) == "zeph":
        return fetch_zeph_network(cfg)

    try:
        data = fetch_json(NETWORK_API, timeout=5)
        if isinstance(data, dict) and isinstance(data.get("difficulty"), (int, float)):
            return data
    except Exception:
        pass

    try:
        data = fetch_json(NETWORKS_API, timeout=5)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and str(item.get("coin", "")).upper() == "XMR":
                    if isinstance(item.get("difficulty"), (int, float)):
                        return item
    except Exception:
        pass

    return None


def refresh_network(force=False):
    global network_cache
    now = time.time()

    with network_lock:
        if (
            not force
            and network_cache["data"]
            and now - network_cache["ts"] < NETWORK_CACHE_SECONDS
        ):
            return network_cache["data"]

    data = fetch_network()
    if data is not None:
        with network_lock:
            network_cache = {"ts": time.time(), "data": data}
            return data

    with network_lock:
        return network_cache["data"]


def network_refresh_loop():
    while True:
        try:
            refresh_network(force=True)
        except Exception:
            pass
        time.sleep(NETWORK_REFRESH_SECONDS)


def get_network():
    cfg = load_config()
    if get_engine_config(cfg) == "cpuminer-opt" or get_coin_config(cfg) == "ltcdoge":
        return {}
    with network_lock:
        cached = network_cache["data"]
        age = time.time() - network_cache["ts"]

    if cached and age < NETWORK_CACHE_SECONDS:
        return cached

    if not cached:
        return refresh_network(force=True)

    return cached


def get_stats():
    cfg = load_config()
    coin = get_coin_config(cfg)
    coin_cfg = COINS[coin]
    engine = get_engine_config(cfg)

    if engine == "cpuminer-opt":
        with scrypt_stats_lock:
            scrypt = dict(scrypt_stats)
        started_at = scrypt.get("started_at")
        uptime = max(0, int(time.time() - started_at)) if started_at and miner_running() else 0
        return {
            "running": miner_running(),
            "engine": engine,
            "coin": "ltcdoge",
            "coin_name": COINS["ltcdoge"]["name"],
            "symbol": COINS["ltcdoge"]["symbol"],
            "hashrate": scrypt.get("hashrate"),
            "accepted": scrypt.get("accepted", 0),
            "rejected": scrypt.get("rejected", 0),
            "uptime": uptime,
            "worker": cfg.get("worker", "umbrel"),
            "pool": cfg.get("pool"),
            "pool_diff": None,
            "best_diff": None,
            "network_difficulty": None,
            "network_algorithm": "Scrypt",
            "network_height": None,
            "network_updated_at": None,
            "network_live": False,
            "network_source": "unavailable",
            "block_candidate": False,
        }

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
    network_algo = network.get("algo") or coin_cfg["algorithm"]

    with network_lock:
        network_updated_at = network_cache.get("ts") or None

    block_candidate = (
        coin == "xmr"
        and isinstance(best_diff, (int, float))
        and isinstance(network_diff, (int, float))
        and network_diff > 0
        and best_diff >= network_diff
    )

    return {
        "running": miner_running(),
        "engine": engine,
        "coin": coin,
        "coin_name": coin_cfg["name"],
        "symbol": coin_cfg["symbol"],
        "hashrate": hash_value,
        "accepted": accepted,
        "rejected": rejected,
        "uptime": summary.get("uptime"),
        "worker": summary.get("worker_id") or cfg.get("worker", "umbrel"),
        "pool": connection.get("pool") or cfg.get("pool"),
        "pool_diff": pool_diff,
        "best_diff": best_diff,
        "network_difficulty": network_diff,
        "network_algorithm": network_algo,
        "network_height": network_height,
        "network_updated_at": network_updated_at if network else None,
        "network_live": bool(network.get("difficulty")),
        "network_source": (network.get("source") or ("kryptex-page" if coin == "tari" else "kryptex-zeph-chart")) if coin in ("tari", "zeph") else "xmrig-network-api",
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
            if "pool_password" in public:
                public["pool_password"] = ""
            public["engine"] = get_engine_config(cfg)
            coin = get_coin_config(cfg)
            public["coin"] = coin
            self.json_response(
                200,
                {
                    "configured": bool(cfg.get("pool") and cfg.get("wallet")),
                    "config": public,
                    "coin": COINS[coin],
                    "coins": COINS,
                    "engines": {
                        "xmrig": {"name": "XMRig", "algorithm": "RandomX"},
                        "cpuminer-opt": {"name": "CPUMiner-opt", "algorithm": "Scrypt"},
                    },
                    "running": miner_running(),
                },
            )
            return

        if self.path == "/api/stats":
            self.json_response(200, get_stats())
            return

        if self.path == "/api/logs":
            self.json_response(
                200,
                {
                    "logs": get_miner_logs(),
                    "running": miner_running(),
                },
            )
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
            append_miner_log("Miner stopped by dashboard.")
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

            engine = str(body.get("engine", "xmrig")).strip().lower()
            if engine not in ("xmrig", "cpuminer-opt"):
                raise ValueError("Unsupported mining engine")

            coin = str(body.get("coin", DEFAULT_COIN)).strip().lower()
            if engine == "cpuminer-opt":
                coin = "ltcdoge"
            elif coin == "ltcdoge":
                raise ValueError("Litecoin + Dogecoin requires the CPUMiner-opt Scrypt engine")
            if coin not in COINS:
                raise ValueError("Unsupported coin")

            pool = str(body.get("pool", "")).strip()
            wallet = str(body.get("wallet", "")).strip()
            worker = str(body.get("worker", "umbrel")).strip() or "umbrel"
            pool_password = str(body.get("pool_password", "")).strip()
            if not pool_password:
                pool_password = load_config().get("pool_password", "1") or "1"
            threads = int(body.get("threads", 0))
            donate = int(body.get("donate_level", 1))

            if not pool or not wallet:
                raise ValueError("Pool URL and wallet/username are required")
            if threads < 0 or donate < 0:
                raise ValueError("Threads and donation level cannot be negative")
            if threads > 1024:
                raise ValueError("CPU threads value is too high")
            if donate > 100:
                raise ValueError("Donation level must be between 0 and 100")

            save_config(
                {
                    "engine": engine,
                    "coin": coin,
                    "pool": pool,
                    "wallet": wallet,
                    "worker": worker,
                    "threads": threads,
                    "donate_level": donate,
                    "pool_password": pool_password,
                }
            )
            with network_lock:
                network_cache["ts"] = 0.0
                network_cache["data"] = {}

            try:
                ok, msg = start_miner()
                self.json_response(200 if ok else 500, {"ok": ok, "message": msg})
            except Exception as e:
                self.json_response(500, {"ok": False, "message": "Failed to start miner: " + str(e)})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.json_response(400, {"ok": False, "message": str(e)})

    def log_message(self, *args):
        pass


threading.Thread(target=network_refresh_loop, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
