# XMR Miner for UmbrelOS

A Monero (XMR) CPU miner for UmbrelOS powered by XMRig.

## Features
- XMRig 6.26.0
- Monero RandomX CPU mining
- AMD64 and ARM64 builds
- Pool, wallet, worker and CPU-thread configuration
- XMRig HTTP API on port 8080
- Docker healthcheck and graceful shutdown
- Persistent `/data` volume
- Docker Compose support for testing outside Umbrel

XMRig 6.26.0 is the current upstream release and includes RandomX v2 support and ARM64 fixes. citeturn0search0turn0search3

## Configuration
Copy `.env.example` to `.env` when testing with Docker Compose:

    cp .env.example .env

Set `XMR_POOL`, `XMR_WALLET`, `XMR_WORKER`, `XMR_THREADS` and `XMR_DONATE_LEVEL`.

**Never put a seed phrase or private key in this repository.**

## Docker test
    docker compose up -d --build
    docker compose logs -f xmr-miner

The miner API is available at `http://YOUR_UMBREL_IP:8080/2/summary`. Stop it with:

    docker compose down

## UmbrelOS
Umbrel Community App Stores use an app directory containing `umbrel-app.yml` and `docker-compose.yml`; this repository follows that application structure. citeturn0search4

This repository is the **application repository**, not a complete Community App Store. A Community App Store repository also needs an `umbrel-app-store.yml` and an app directory matching the store's app ID. citeturn0search4

## ARM64 build
The current upstream XMRig release exposes a Linux static x64 archive but no Linux static ARM64 archive. This project therefore builds XMRig from source in Docker for the target architecture instead of referencing a nonexistent ARM64 release asset. citeturn0search0

XMRig's Ubuntu build documentation lists Git/build tools, CMake, libuv, OpenSSL and hwloc dependencies; those are installed in the builder image. citeturn2search0turn2search3

## Mining performance
Monero uses RandomX and is CPU-oriented. Actual performance depends on CPU architecture, RAM, memory configuration, huge pages, thermals, pool fees, network conditions and electricity cost.

This project does **not** guarantee profitability.

## Security
The miner needs a wallet address for payouts but does not need your seed phrase or private key.

Do not expose the XMRig HTTP API to the public internet. Keep port 8080 on your trusted LAN/Umbrel network.

## License
MIT


## Umbrel dashboard
Install `wx256-xmr-miner` from the Wx256 Community App Store. Opening the app from the Umbrel dashboard shows the live mining dashboard; XMRig's API remains internal to the container.
