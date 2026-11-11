# Rules for agents working in this repository

Project: "NEAR Against Its Peers", for the NEAR Hackathon (Investment Thesis track). The full plan is in `planning/PLAN.md` (git-ignored).

## Hard rules
- **No hand-typed numbers.** Every number in `THESIS.md`, the dashboard, the X post and the form text comes from `data/processed/metrics.json` or `summary.txt`. `THESIS.template.md` contains no digits outside `{{…}}` placeholders.
- **Every fee definition cites its source** (DefiLlama methodology URL, CoinGecko endpoint).
- **No keys or secrets** in the repository. The APIs used are keyless.
- **Never read the wall clock** in `src/build.py`, `src/metrics.py`, `src/render.py` or the tests. Time comes from `data/raw/MANIFEST.json` → `as_of`. Only `src/fetch.py` may read the clock.
- **Standard library only.** Use Python 3.11+, `tomllib` and `unittest`. Do not add dependencies.
- **Perimeter names:** BASE, BASE+NET (captured revenue, the defended one), BASE+HOLDERS (sensitivity), BASE+GROSS (upper bound only). Never write "cheapest", and never write "returned to the token".
- `HACKATHON.md` and the hackathon site are authoritative over this file.

## Commands
- `make judge-demo`: offline build plus tests. This is the screening command and must always pass.
- `make build`: offline build from `data/raw/`.
- `make test`: `python3 -m unittest`.
- `make all`: fetches fresh data (needs network), then builds. It is optional.
