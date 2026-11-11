"""Fetch a fresh data snapshot: APIs -> data/staging/ -> atomic swap into data/raw/.

The only module allowed to read the clock (for `fetched_at`). The snapshot's
`as_of` date comes from the data: the last date present in every series.
"""
import json
import shutil
import sys
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFILLAMA = "https://api.llama.fi/summary/fees/{slug}?dataType={data_type}"
COINGECKO = "https://api.coingecko.com/api/v3"
INTENTS_DATA_TYPES = ("dailyFees", "dailyRevenue", "dailyHoldersRevenue")
DEFILLAMA_KEEP = ("name", "methodology", "methodologyURL", "parentProtocol", "totalDataChart")


def planned_requests(config):
    """Return (filename, url, source) for every request the snapshot needs."""
    requests = []
    for chain in config["chains"]:
        slug = chain["defillama_slug"]
        requests.append((f"defillama_{slug}_dailyFees.json",
                         DEFILLAMA.format(slug=slug, data_type="dailyFees"), "defillama"))
    slug = config["intents"]["defillama_slug"]
    for data_type in INTENTS_DATA_TYPES:
        requests.append((f"defillama_{slug}_{data_type}.json",
                         DEFILLAMA.format(slug=slug, data_type=data_type), "defillama"))
    ids = ",".join(c["coingecko_id"] for c in config["chains"])
    requests.append(("coingecko_markets.json",
                     f"{COINGECKO}/coins/markets?vs_currency=usd&ids={ids}", "coingecko"))
    # Keyless CoinGecko serves at most 365 days of history (401 beyond that).
    for chain in config["chains"]:
        cg = chain["coingecko_id"]
        requests.append((f"coingecko_{cg}_market_chart.json",
                         f"{COINGECKO}/coins/{cg}/market_chart?vs_currency=usd&days=365&interval=daily",
                         "coingecko"))
    return requests


def last_common_date(series):
    """ISO date of the last day present in every series of [timestamp, value] rows."""
    last = min(rows[-1][0] for rows in series.values())
    return datetime.fromtimestamp(last, tz=timezone.utc).date().isoformat()


def fetch_and_swap(config, get_json, staging_dir, raw_dir, fetched_at, pause=2.5):
    """Write a complete snapshot to staging_dir, then swap it into raw_dir.

    If any request fails, raw_dir is left untouched.
    """
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    sources, series = {}, {}
    for filename, url, source in planned_requests(config):
        payload = get_json(url)
        if source == "defillama":
            payload = {k: payload.get(k) for k in DEFILLAMA_KEEP}
            series[filename] = payload["totalDataChart"]
        elif pause:
            time.sleep(pause)  # keyless CoinGecko is rate-limited
        (staging_dir / filename).write_text(json.dumps(payload, indent=1) + "\n")
        sources[filename] = url

    manifest = {"as_of": last_common_date(series), "fetched_at": fetched_at, "sources": sources}
    (staging_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

    old = raw_dir.with_name(raw_dir.name + ".old")
    if raw_dir.exists():
        raw_dir.rename(old)
    staging_dir.rename(raw_dir)
    if old.exists():
        shutil.rmtree(old)
    return manifest


class RateLimited(Exception):
    """The API answered 429 Too Many Requests."""


def with_retries(get_json, sleep=time.sleep, attempts=5, backoff=30):
    """Retry on RateLimited, waiting backoff, 2*backoff, 3*backoff... seconds."""
    def wrapped(url):
        for attempt in range(1, attempts + 1):
            try:
                return get_json(url)
            except RateLimited:
                if attempt == attempts:
                    raise
                sleep(backoff * attempt)
    return wrapped


def http_get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "near-peer-multiples/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(url) from e
        raise


def main():
    with (ROOT / "config" / "panel.toml").open("rb") as f:
        config = tomllib.load(f)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = fetch_and_swap(config, with_retries(http_get_json), ROOT / "data" / "staging",
                              ROOT / "data" / "raw", fetched_at, pause=6)
    print(f"snapshot as_of {manifest['as_of']}: {len(manifest['sources'])} files in data/raw/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
