# Learning log

Manual interventions and surprises. After submission, each one becomes a rule, a test or a hook.

## 2026-11-11: first data fetch

- **The series end on different days.** NEAR, Solana and NEAR Intents stop on 10 Nov; Ethereum, Avalanche, Sui and Aptos have a partial 11 Nov.
  - `as_of` = the last date common to every series (2026-11-10), taken from the data, not the clock. Tested.
  - **To do in `metrics.py`:** cut every series at `as_of` before summing.
- **CoinGecko keyless rate limit:** it answered 429. Added `with_retries` (30 s, 60 s, … backoff) and a 6 s pause between calls. Tested. Nothing was written, because the atomic swap held.
- **CoinGecko keyless history is capped at 365 days:** `days=400` answered 401. The history starts on 2025-11-12, which is short of `as_of − 365`. So float growth uses the window actually available, annualized and labeled with its exact dates.
