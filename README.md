# NEAR Against Its Peers

> Work in progress for the NEAR Hackathon, Investment Thesis track. **Not financial advice.**

For each dollar of fees paid on-chain, does the market value NEAR more or less than its peers? And which perimeter that includes NEAR Intents can be defended?

## Run it

Requirements: Python 3.11+ and `make`. There is nothing to install, and no network is needed.

```bash
make judge-demo
```

This rebuilds everything offline from the committed data snapshot in `data/raw/`, then runs the tests.

Optional: `make all` fetches fresh data (needs network), then rebuilds.

`.claude/settings.json` holds a Claude Code hook that only runs `make test` after edits to `src/` or `tests/`; it does nothing outside Claude Code.

## Data sources

DefiLlama (fees and revenue) and CoinGecko (market caps). Credits and methodology links will be added with the first data snapshot.

## License

The code is under the MIT license. The data belongs to its providers (see Data sources).
