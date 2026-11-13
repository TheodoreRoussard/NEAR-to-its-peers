# NEAR Against Its Peers

> NEAR Hackathon submission, Investment Thesis track. **Not financial advice.**

**What it is.** A reproducible investment thesis on NEAR, built as a data pipeline. It compares NEAR's market cap per dollar of on-chain fees with five peer chains (Solana, Ethereum, Avalanche, Sui, Aptos). It also tests four falsification criteria that would prove the thesis wrong.

**The problem it addresses.** NEAR's base-layer fees are small, so on fees alone NEAR looks expensive. Most of its recent revenue comes from NEAR Intents, but which part of that revenue can fairly count for NEAR token holders is unclear. This project answers both questions with four explicit perimeters (BASE, BASE+NET, BASE+HOLDERS, BASE+GROSS), and states explicit tripwires that would change the conclusion, with thresholds frozen in a tagged commit (`thresholds-frozen`) after the first numbers were seen.

**Scope versus the track brief.** The track points to on-chain usage data: the NEAR BigQuery dataset (active accounts, transactions) and the NEAR Intents Explorer API (swap volume). This project does not use them. BigQuery queries are billed to a Google Cloud account, and the Explorer API needs a partner token; either would break the keyless, offline, one-command rebuild below. The thesis relies instead on DefiLlama's NEAR Intents revenue series, which DefiLlama states reconciles with revenue.near.org and the on-chain buyback. Usage data would explain where that revenue comes from, not change the valuation measured here.

**Outputs:**
- [`THESIS.md`](THESIS.md): the thesis. It covers the claim, the evidence for and against, what would change the conclusion, the method and the limitations.
- [Dashboard](https://theodoreroussard.github.io/NEAR-to-its-peers/) (`docs/index.html`): each chart with its method and one plain sentence on what it shows, and every source in one block at the end.
- [`data/processed/metrics.json`](data/processed/metrics.json): every number used by the two above.

## Try it

To read the thesis, you need nothing: open the [dashboard](https://theodoreroussard.github.io/NEAR-to-its-peers/) or [`THESIS.md`](THESIS.md). To rebuild it or change a parameter, you need your own copy of the repository, because every command below runs on local files.

Requirements: `git`, Python 3.11 or newer, and `make`. There is nothing to install, and no API key is needed. Only step 0 (and the optional step 5) uses the network.

**0. Get a copy of the repository.**

```bash
git clone https://github.com/TheodoreRoussard/NEAR-to-its-peers.git
cd NEAR-to-its-peers
```

Run every command below from this folder. To review exactly the submitted version, also run `git checkout hackathon-submission`.

**1. Rebuild everything and run the tests.**

```bash
make judge-demo
```

You should see:
- the test run end with `OK`;
- `metrics.json`, `THESIS.md` and `docs/index.html` rebuilt offline from the committed snapshot in `data/raw/`.

`git status` then shows no change, because the committed outputs are exactly what the code produces.

**2. Read the result.** Open `THESIS.md`. The verdicts of the four criteria (C1 to C4) are stated under "The claim" and detailed under "What would change my mind".

**3. See the charts.** Open `docs/index.html` from your copy in a browser, or the [published copy](https://theodoreroussard.github.io/NEAR-to-its-peers/). The page has no scripts and loads nothing from the network, so it also works offline.

**4. Check that the verdicts are computed, not written.**
- Edit a threshold in `config/panel.toml`: under `[falsification.thresholds]`, change `k = 1.0` to `k = 0.3`.
- Run `make build`. C1 now fires, and both `THESIS.md` and your local `docs/index.html` say so (reload it in the browser).
- These changes stay on your machine: the published page does not change.
- Run `git checkout .` to restore.

**5. Optional: refresh the data.** `make all` fetches fresh data from the public APIs, then rebuilds.
- It needs network access, and takes a few minutes because of the pauses that respect CoinGecko's rate limit.
- If a request fails, the existing snapshot is left untouched.

## How it works

```
src/fetch.py   public APIs ──► data/raw/ (+ MANIFEST.json: URLs, as_of date)      [make all only]
src/build.py   data/raw/ + config/panel.toml ──► data/processed/metrics.json
src/render.py  metrics.json ──► docs/index.html
src/thesis.py  metrics.json + THESIS.template.md ──► THESIS.md
```

| Path | What it holds |
|---|---|
| `config/panel.toml` | The panel rule and its chains, the Intents settings, the falsification formulas and thresholds (with the rationale for each) |
| `src/metrics.py` | Pure functions: trailing sums, multiples, perimeters, windows, criteria |
| `src/build.py` | The offline build. The date comes from the snapshot (`as_of`), never from the clock |
| `src/render.py`, `src/thesis.py` | The dashboard and the thesis, generated from `metrics.json` |
| `THESIS.template.md` | The thesis prose. It holds no digits outside `{{…}}` placeholders, and a test enforces this |
| `tests/` | `unittest` suites on hand-computed fixtures and on the committed snapshot |
| `data/` | The snapshot and the computed metrics; see [`data/README.md`](data/README.md) |

**Method in brief.**
- **Multiple:** market cap divided by fees summed over a trailing year, for each chain. NEAR is shown under four perimeters, and the result is compared with the median of the peers.
- **Robustness:** the panel is varied by adding two candidate chains (Tron, Cardano) or dropping one peer at a time.
- **Falsification:** four criteria, C1 to C4, cover valuation, durability of Intents revenue, capture rate, and whether bought-back NEAR is held for holders. Their thresholds were frozen in the tagged commit `thresholds-frozen`.
- **Details and limitations:** in [`THESIS.md`](THESIS.md).

## Quality checks

- **CI:** GitHub Actions runs `make judge-demo` on Python 3.11 and 3.13 for every pull request and every push to `main`. It fails if the committed outputs differ from a rebuild. A push to `main` publishes `docs/` to GitHub Pages.
- **Code rules:** standard library only, no keys or secrets, and no reading of the clock outside `src/fetch.py` (tested).
- **No hand-typed numbers:** every number in `THESIS.md` and on the dashboard comes from `metrics.json`. Sentences that state a verdict or a direction are generated from the data, and tests flip each verdict to check that the prose follows.

## Hackathon disclosures

- **Built during the hackathon.** The first commit is dated 2026-11-11, after the 2026-10-19 announcement. There is no pre-hackathon code, so there is no baseline to separate.
- **Other chains.** Data from Solana, Ethereum, Avalanche, Sui, Aptos, Tron and Cardano is used only as a comparison. There is no existing product on another chain.
- **Libraries, templates, boilerplate.** None in the code: only the Python standard library is used. The dashboard design was reviewed with [Impeccable](https://impeccable.style), an AI design-review tool used during development; it adds no runtime code (its context files are `PRODUCT.md`, `DESIGN.md` and `.impeccable/`). CI uses the standard GitHub Actions `actions/checkout`, `actions/setup-python`, `actions/upload-pages-artifact` and `actions/deploy-pages`.
- **AI-written code.** The code, tests and documents were written with [Claude Code](https://claude.com/claude-code) (Anthropic) as a coding assistant, under the author's direction. The author made and approved the decisions on method, the peer panel and the falsification thresholds. `CLAUDE.md` holds the rules the assistant follows in this repository.
- **Other projects.** None.

## Data and credits

- Fees and revenue: data from [DefiLlama](https://defillama.com). Each fee definition links to its DefiLlama methodology in `THESIS.md`.
- Market caps and prices: Powered by [CoinGecko](https://www.coingecko.com).
- Buyback account: read on [nearblocks](https://nearblocks.io).

The committed snapshot belongs to its providers and is **not** covered by the MIT license. See [`data/README.md`](data/README.md) for how it is used.

## License

The code is under the [MIT license](LICENSE). The data belongs to its providers.

## Development notes

`.claude/settings.json` holds a Claude Code hook that only runs `make test` after edits to `src/` or `tests/`. It does nothing outside Claude Code.
