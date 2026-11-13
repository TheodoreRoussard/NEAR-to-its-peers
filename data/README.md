# Data notice

`data/raw/` is a snapshot of public API responses, committed so that `make judge-demo` rebuilds every figure offline and anyone can check the result. `data/processed/metrics.json` is computed from it by `src/build.py`.

**This data belongs to its providers. It is not covered by the repository's MIT license**, which applies to the code only.

| Provider | What | Credit |
|---|---|---|
| [DefiLlama](https://defillama.com) | Daily fees, revenue and holders revenue (`defillama_*.json`) | Data from DefiLlama. Each fee definition links to its DefiLlama methodology in `THESIS.md`. |
| [CoinGecko](https://www.coingecko.com) | Daily market caps and prices (`coingecko_*.json`) | Powered by CoinGecko. |
| [nearblocks](https://nearblocks.io) | Buyback account balance and outflows, read by hand on the date in `config/panel.toml` | Recorded as sourced constants, not as raw files. |

## How it is used

- The snapshot was fetched once with the keyless public APIs (`make all`, `src/fetch.py`). `MANIFEST.json` lists the exact URL of every file and the fetch time.
- Files are stored as returned, except that DefiLlama's per-protocol breakdown is dropped to keep the snapshot small.
- It serves a non-commercial research submission (NEAR Hackathon, Investment Thesis track). Nothing here is sold or offered as a data feed.
- Both providers' terms restrict storing and republishing their data. If either provider asks, the snapshot will be removed. `make all` then rebuilds everything from the live APIs.

Terms: [DefiLlama](https://defillama.com/terms), [CoinGecko API](https://www.coingecko.com/en/api_terms).
