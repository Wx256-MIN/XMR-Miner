# RandomX CPU Miner for UmbrelOS

A focused XMRig-based CPU mining dashboard for **Monero (XMR), Tari (XTM), and Zephyr (ZEPH)**. This project ships only the RandomX-family XMRig engine.

## Features

- XMRig 6.26.0 built from source for Linux AMD64 and ARM64.
- Monero RandomX, Tari-native RandomXT pool mining, and Zephyr RandomX.
- Live hashrate, accepted/rejected shares, uptime, pool connection, and rolling miner logs.
- Best share difficulty, current pool difficulty, live network difficulty, and best/network ratio.
- Block-candidate indicator based on best share versus network difficulty; final confirmation remains with the pool or node.
- Automatic dashboard refresh and persistent `/data` configuration.
- MSR compatibility handling for hosts where MSR writes are already enabled.

## Setup

Install the app from the Wx256 Community App Store, open **RandomX CPU Miner**, select the coin, and enter the pool URL, wallet address, worker name, CPU thread count, and donation level.

- **Monero:** XMRig uses `--algo=rx/0` and `--coin=monero`.
- **Tari:** uses `--algo=rx/0` without forcing the Monero coin argument, for Tari-native RandomXT pool work.
- **Zephyr:** uses XMRig RandomX with the Zephyr coin setting.

The dashboard stores configuration in `/data/config.json`. Legacy Scrypt engine selections from older builds fall back to Monero/XMRig and can be reconfigured in the setup page.

## Performance and profitability

RandomX is CPU-oriented. Performance depends on CPU architecture, memory, huge pages, thermals, pool fees, and electricity cost. CPU mining is not guaranteed to be profitable. Use a pool endpoint and wallet format documented by your selected pool.

## Security

Never enter a seed phrase or private key. Only a payout wallet address is needed. Do not expose XMRig's HTTP API on port 8080 to the public internet. MSR access is granted for performance optimization and should only be enabled on hardware you own or administer.

## Development

The Docker build compiles XMRig from the pinned upstream release. GitHub Actions builds and publishes the image for `linux/amd64` and `linux/arm64`.

- [Docker build workflow](.github/workflows/build.yml)
- [Third-party notices](wx256-xmr-miner/THIRD_PARTY_NOTICES.md)
- [App source](wx256-xmr-miner/)

## License

The dashboard and integration code is provided under the repository's MIT license. XMRig remains subject to its upstream GPL-3.0 license.
