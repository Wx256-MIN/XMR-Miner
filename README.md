# XMR-Miner

UmbrelOS Monero (XMR) CPU mining app powered by XMRig.

## Features
- XMRig CPU miner
- Configurable pool and wallet
- Worker name and CPU thread control
- XMRig HTTP API on port 8080
- Docker healthcheck
- Persistent /data volume
- AMD64 and ARM64 image support
- Umbrel-oriented packaging

## Configuration
Copy `.env.example` to `.env` and configure `XMR_POOL`, `XMR_WALLET`, `XMR_WORKER`, `XMR_THREADS`, and `XMR_DONATE_LEVEL`.

Never commit a seed phrase or private key.

## Running

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
```

Miner API: `http://YOUR_UMBREL_IP:8080/2/summary`

## Mining notes
Monero uses RandomX and is CPU-oriented. Actual performance depends on CPU, RAM, huge pages, thermals, pool fees, network conditions and electricity cost.

This software does not guarantee profitability.

## License
MIT
