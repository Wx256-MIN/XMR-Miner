# CPU RandomX Miner for UmbrelOS

A CPU RandomX miner for UmbrelOS powered by XMRig, with support for Monero (XMR) and Tari (XTM).

## Supported coins

| Coin | Symbol | PoW | XMRig algorithm | Notes |
|---|---|---|---|---|
| Monero | XMR | RandomX | `rx/0` | Standard Monero RandomX |
| Tari | XTM | RandomXT | `rx/0` | Tari-native RandomX pool mining |

Tari mainnet has separate PoW lanes, including Monero merge-mined RandomX and Tari-native RandomX (RandomXT). Tari documents RandomXT as its native RandomX proof-of-work, and its current mining software supports `RandomXT`. Tari also made its RandomX PoW compatible with XMRig. citeturn6search2turn6search9

## Features
- XMRig 6.26.0
- Monero RandomX CPU mining
- Tari RandomXT CPU mining
- AMD64 and ARM64 builds
- Coin selector in the setup wizard
- Pool, wallet, worker and CPU-thread configuration
- XMRig HTTP API on port 8080
- Persistent `/data` volume
- Docker Compose support for testing outside Umbrel

## Tari network difficulty

For Tari XTM-RX on Kryptex, the dashboard reads live network difficulty from Kryptex's public API endpoint for network hashrate and difficulty. This does not require a Tari Base Node on the Umbrel host. Kryptex documents the network endpoint as `/api/v1/net/stats/{coin}`, and its Tari RandomX pool is XTM-RX on port 7038. citeturn3search0turn1search1

The dashboard therefore shows **Kryptex API** as the source when Tari network difficulty is live.


## Tari mining configuration

Select **Tari (XTM) — RandomXT** in the setup wizard.

For Tari, the miner uses:

    --algo=rx/0

and does **not** force:

    --coin=monero

This is intentional. Tari RandomXT uses the RandomX engine but the Tari pool supplies Tari-specific work through the stratum job. Do not enter a Monero wallet when mining Tari.

Example Tari RandomX pool endpoints can be obtained from current Tari RandomX pool listings. Pool availability and ports can change, so use the pool's current stratum endpoint rather than hard-coding an old address. citeturn5search1turn5search9

## Monero mining configuration

Select **Monero (XMR) — RandomX**. The miner uses:

    --algo=rx/0
    --coin=monero

## Important Tari distinction

Tari supports both **RandomX-M (Monero merge-mined)** and **RandomX-T (Tari-native)** as separate PoW lanes. This app's Tari mode is for **Tari-native RandomXT pool mining**, not Monero merge mining. Tari's merge-mining proxy is a separate setup and is not enabled by this app. citeturn6search0turn6search2

## Configuration

Copy `.env.example` to `.env` when testing with Docker Compose:

    cp .env.example .env

The Umbrel dashboard stores the selected coin, pool, wallet, worker, CPU threads and donation level in `/data/config.json`.

**Never put a seed phrase or private key in this repository.**

## Docker test

    docker compose up -d --build
    docker compose logs -f xmr-miner

The miner API is available at:

    http://YOUR_UMBREL_IP:8080/2/summary

Stop it with:

    docker compose down

## ARM64 build

The project builds XMRig from source in Docker for Linux AMD64 and ARM64 instead of relying on a prebuilt architecture-specific archive.

## Performance

RandomX is CPU-oriented. Actual performance depends on CPU architecture, RAM, memory configuration, huge pages, thermals, pool fees, network conditions and electricity cost. XMRig recommends huge pages and other RandomX optimizations for best performance. citeturn0search0turn0search3

This project does **not** guarantee profitability.

## Security

The miner needs a wallet address for payouts but does not need your seed phrase or private key.

Do not expose the XMRig HTTP API to the public internet. Keep port 8080 on your trusted LAN/Umbrel network.

## Umbrel dashboard

Install `wx256-xmr-miner` from the Wx256 Community App Store. Open the app from the Umbrel dashboard, select XMR or XTM, configure the pool and wallet, and start mining.

## License

MIT
