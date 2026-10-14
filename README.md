# CPU Coin Miner for UmbrelOS

An UmbrelOS mining dashboard with two selectable CPU mining engines:

- **XMRig 6.26.0** for Monero (XMR), Tari (XTM), and Zephyr (ZEPH) RandomX-family mining.
- **CPUMiner-opt 26.1** for Scrypt mining through compatible Litecoin/Dogecoin pools, including merged-mining pools that pay both coins.

## Features

- Choose XMRig (RandomX) or CPUMiner-opt (Scrypt) from the dashboard.
- Configure pool, wallet/account username, worker name, password (Scrypt), and CPU thread count.
- View miner logs, hashrate, accepted/rejected shares, and uptime.
- Persistent `/data` configuration.
- AMD64 and ARM64 Docker builds, subject to upstream CPUMiner-opt support/performance on each architecture.
- MSR access for RandomX optimization on supported Linux hosts.

## Litecoin + Dogecoin (Scrypt)

In the dashboard choose **CPUMiner-opt — Scrypt (Litecoin + Dogecoin)**. Supply a Scrypt pool endpoint and the account username or wallet format required by that pool. The worker name is appended to the username when it has no dot already; the pool password defaults to `1` if one has not been saved.

For example, LitecoinPool documents this Stratum endpoint:

```text
stratum+tcp://eu.litecoinpool.org:3333
```

Use that example only with a LitecoinPool account; enter your account username, choose a worker name, and use the password required by your pool. LitecoinPool says it automatically merged-mines Litecoin and Dogecoin and pays DOGE separately. Other pools may have different payout rules, so confirm that your pool actually supports LTC/DOGE merged mining before configuring it.

**CPU Scrypt mining is not competitive with dedicated Scrypt ASICs and is unlikely to be profitable on a desktop CPU.** Use the Scrypt engine for compatibility/testing, not as a profitability guarantee.

## RandomX coins

Choose **XMRig — RandomX** to use the existing Monero, Tari, or Zephyr options. These remain handled by XMRig; choosing CPUMiner-opt switches to the separate Scrypt engine.

## Configuration and security

Configuration is saved locally under the app's persistent `/data` directory. Never put a seed phrase or private key in this repository. A mining wallet/account address or pool username is sufficient.

The app grants the miner access to host MSR device files and uses the `SYS_RAWIO` capability plus an unconfined AppArmor profile for MSR optimization. Run it only on hardware you own or are authorized to administer. Do not expose the miner's local API to the public internet.

## Build

The Docker build compiles XMRig and CPUMiner-opt from pinned upstream releases. The image build includes a Python syntax check for the dashboard backend. GitHub Actions publishes the application image for `linux/amd64` and `linux/arm64`.

See [Third-party notices](wx256-xmr-miner/THIRD_PARTY_NOTICES.md) for bundled miner projects and their licenses.

## License

This repository's dashboard and integration code is provided under the license in [LICENSE](LICENSE). XMRig and CPUMiner-opt remain subject to their respective upstream licenses; see the third-party notices.
