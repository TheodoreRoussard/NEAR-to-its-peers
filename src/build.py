"""Offline build: data/raw/ -> data/processed/metrics.json.

Never reads the wall clock: the date comes from data/raw/MANIFEST.json ("as_of").
"""
import json
import sys
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median

from src import metrics as m

RUN_RATE_DAYS = 90

ROOT = Path(__file__).resolve().parent.parent


class MissingSnapshot(Exception):
    """Raised when data/raw/ has no snapshot to build from."""


def _series(raw_dir, filename):
    return json.loads((raw_dir / filename).read_text())["totalDataChart"]


def _since(rows, iso_day):
    start = date.fromisoformat(iso_day)
    return [r for r in rows if datetime.fromtimestamp(r[0], tz=timezone.utc).date() >= start]


def _intents_window(series, end, regime_break, gaps):
    """Sums over the RUN_RATE_DAYS days ending on `end`; all null if the window
    starts before the regime break (the data is not comparable there)."""
    start = m.shift_date(end, -(RUN_RATE_DAYS - 1))
    window = {"start": start, "end": end}
    if start < regime_break:
        window.update(net=None, gross=None, holders=None, net_over_gross=None)
        return window
    for key, rows in series.items():
        window[key] = m.trailing_sum(rows, end, RUN_RATE_DAYS, max_missing=gaps)
    window["net_over_gross"] = None if window["gross"] == 0 else window["net"] / window["gross"]
    return window


def compute(raw_dir, config, as_of):
    days = config["windows"]["trailing_days"]
    gaps = config["windows"]["max_missing_days"]
    chains = {}
    for chain in config["chains"]:
        rows = _series(raw_dir, f"defillama_{chain['defillama_slug']}_dailyFees.json")
        fees = m.trailing_sum(rows, as_of, days, max_missing=gaps)
        caps = json.loads((raw_dir / f"coingecko_{chain['coingecko_id']}_market_chart.json")
                          .read_text())["market_caps"]
        cap = m.market_cap_on(caps, as_of)
        chains[chain["name"]] = {"market_cap": cap, "fees_trailing": fees,
                                 "multiple": m.multiple(cap, fees),
                                 "missing_days": m.missing_days(rows, as_of, days)}

    peers = [c["multiple"] for name, c in chains.items() if name != "NEAR"]
    peer_median = median(p for p in peers if p is not None)

    intents = config["intents"]
    slug = intents["defillama_slug"]
    holders_rows = _since(_series(raw_dir, f"defillama_{slug}_dailyHoldersRevenue.json"),
                          intents["regime_break"])
    holders_window = m.trailing_sum(holders_rows, as_of, days, allow_late_start=True,
                                    max_missing=gaps)
    holders_days = (date.fromisoformat(as_of) - date.fromisoformat(intents["regime_break"])).days + 1
    holders_days = min(holders_days, days)

    near = chains["NEAR"]
    denominators = m.perimeters(
        base=near["fees_trailing"],
        intents_net=m.trailing_sum(_series(raw_dir, f"defillama_{slug}_dailyRevenue.json"), as_of, days,
                                   max_missing=gaps),
        intents_holders=m.annualized(holders_rows, as_of, days, max_missing=gaps),
        intents_gross=m.trailing_sum(_series(raw_dir, f"defillama_{slug}_dailyFees.json"), as_of, days,
                                     max_missing=gaps),
    )
    near_perimeters = {}
    for name, denominator in denominators.items():
        multiple = m.multiple(near["market_cap"], denominator)
        near_perimeters[name] = {
            "denominator": denominator,
            "multiple": multiple,
            "ratio_to_peer_median": None if multiple is None else multiple / peer_median,
        }
    near_perimeters["BASE+HOLDERS"]["holders_days"] = holders_days
    near_perimeters["BASE+HOLDERS"]["holders_sum"] = holders_window

    break_day = intents["regime_break"]
    series = {"net": _series(raw_dir, f"defillama_{slug}_dailyRevenue.json"),
              "gross": _series(raw_dir, f"defillama_{slug}_dailyFees.json"),
              "holders": _series(raw_dir, f"defillama_{slug}_dailyHoldersRevenue.json")}
    last = _intents_window(series, as_of, break_day, gaps)
    prior = _intents_window(series, m.shift_date(as_of, -RUN_RATE_DAYS), break_day, gaps)
    run_rate = {key: None if last[key] is None else last[key] * 365 / RUN_RATE_DAYS
                for key in ("net", "gross", "holders")}

    return {"as_of": as_of, "trailing_days": days, "chains": chains,
            "peer_median_multiple": peer_median, "near_perimeters": near_perimeters,
            "intents": {"regime_break": break_day,
                        "windows": {"last_90d": last, "prior_90d": prior},
                        "run_rate_90d": run_rate}}


def build(raw_dir: Path, out_dir: Path, config: dict) -> dict:
    manifest_path = raw_dir / "MANIFEST.json"
    if not manifest_path.exists():
        raise MissingSnapshot(
            f"No data snapshot at {manifest_path}. Run `make all` (needs network) to fetch one."
        )
    as_of = json.loads(manifest_path.read_text())["as_of"]
    result = compute(raw_dir, config, as_of)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main() -> int:
    with (ROOT / "config" / "panel.toml").open("rb") as f:
        config = tomllib.load(f)
    try:
        build(ROOT / "data" / "raw", ROOT / "data" / "processed", config)
    except MissingSnapshot as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
