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

## Git workflow
- **One branch and one pull request per topic. Never commit directly on `main`.**
  - Name the branch after its topic: `feat/…`, `fix/…`, `ci/…`, `docs/…`, `chore/…`, `data/…`.
  - Branch from `main`.
  - If a topic depends on another that is not merged yet, branch from that topic's branch and open the PR **against it** (a stacked PR).
- **CI runs on every pull request**, whatever its base: `make judge-demo` on Python 3.11 and 3.13, plus a check that the committed outputs match a rebuild. Merge only when CI is green.
- **Merge with "Create a merge commit", never squash.** That gives one merge commit per topic on `main`. Squashing breaks stacked PRs: the next PR would show the commits again. Merge stacks in order; once a base branch is merged and deleted, GitHub retargets the next PR to `main`.
- A push to `main` deploys `docs/` to GitHub Pages (CD).
- Inside a topic, keep commits small and separate (code, data snapshot, rebuilt `metrics.json`, docs), each with a clear message.

## Commands
- `make judge-demo`: offline build plus tests. This is the screening command and must always pass.
- `make build`: offline build from `data/raw/`.
- `make test`: `python3 -m unittest`.
- `make all`: fetches fresh data (needs network), then builds. It is optional.
