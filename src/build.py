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


def _falsification(config, near_perimeters, last, prior):
    """Statistic and verdict of each criterion; a verdict needs its threshold in the config."""
    formulas = config["falsification"]
    thresholds = formulas.get("thresholds", {})
    intents = config["intents"]

    def entry(key, statistic, threshold_key, fires_if):
        result = m.criterion(statistic, thresholds.get(threshold_key), fires_if)
        return {"formula": formulas[key], **result}

    c4_statistic = m.outflow_share(intents["buyback_outflows_near"],
                                   intents["buyback_holdings_near"])
    c4 = m.buyback_criterion(c4_statistic, thresholds.get("z"), intents["buyback_policy"])
    return {
        "c1": entry("c1", near_perimeters["BASE+NET"]["ratio_to_peer_median"], "k", m.ABOVE),
        "c2": entry("c2", m.change(last["net"], prior["net"]), "x", m.DROP),
        "c3": entry("c3", m.change(last["net_over_gross"], prior["net_over_gross"]), "y", m.DROP),
        "c4": {"formula": formulas["c4"], **c4,
               "policy": intents["buyback_policy"], "source": intents["buyback_source"]},
    }


def _chain_entry(raw_dir, chain, as_of, days, gaps):
    """Market cap, trailing fees and multiple of one chain (a panel chain or a candidate)."""
    rows = _series(raw_dir, f"defillama_{chain['defillama_slug']}_dailyFees.json")
    fees = m.trailing_sum(rows, as_of, days, max_missing=gaps)
    chart = json.loads((raw_dir / f"coingecko_{chain['coingecko_id']}_market_chart.json").read_text())
    caps = chart["market_caps"]
    cap = m.market_cap_on(caps, as_of)
    return {"market_cap": cap, "fees_trailing": fees, "multiple": m.multiple(cap, fees),
            "missing_days": m.missing_days(rows, as_of, days),
            "float_growth": m.float_growth(chart["prices"], caps, as_of)}


def _add_one(raw_dir, config, as_of, peers, near_base_net_multiple):
    """One row per candidate: its own multiple and NEAR BASE+NET against the median of the
    peers plus that candidate. Candidates are never part of the panel."""
    days = config["windows"]["trailing_days"]
    gaps = config["windows"]["max_missing_days"]
    rows = []
    for candidate in config.get("candidates", []):
        entry = _chain_entry(raw_dir, candidate, as_of, days, gaps)
        with_candidate = peers + ([entry["multiple"]] if entry["multiple"] is not None else [])
        ratio = None
        if near_base_net_multiple is not None:
            ratio = near_base_net_multiple / median(with_candidate)
        rows.append({"name": candidate["name"], "market_cap": entry["market_cap"],
                     "fees_trailing": entry["fees_trailing"], "multiple": entry["multiple"],
                     "missing_days": entry["missing_days"],
                     "near_base_net_ratio_to_median_with_candidate": ratio})
    return rows


def compute(raw_dir, config, as_of):
    days = config["windows"]["trailing_days"]
    gaps = config["windows"]["max_missing_days"]
    chains = {chain["name"]: _chain_entry(raw_dir, chain, as_of, days, gaps)
              for chain in config["chains"]}

    peers = [c["multiple"] for name, c in chains.items()
             if name != "NEAR" and c["multiple"] is not None]
    peer_median = median(peers)

    intents = config["intents"]
    slug = intents["defillama_slug"]
    break_day = intents["regime_break"]
    series = {"net": _series(raw_dir, f"defillama_{slug}_dailyRevenue.json"),
              "gross": _series(raw_dir, f"defillama_{slug}_dailyFees.json"),
              "holders": _series(raw_dir, f"defillama_{slug}_dailyHoldersRevenue.json")}

    # Every perimeter is a trailing-`days` sum ending at as_of (the holders series is the full one:
    # zeros before the regime break count). The run-rate since the break is informational only.
    near = chains["NEAR"]
    denominators = m.perimeters(
        base=near["fees_trailing"],
        intents_net=m.trailing_sum(series["net"], as_of, days, max_missing=gaps),
        intents_holders=m.trailing_sum(series["holders"], as_of, days, max_missing=gaps),
        intents_gross=m.trailing_sum(series["gross"], as_of, days, max_missing=gaps),
    )
    near_perimeters = {}
    for name, denominator in denominators.items():
        multiple = m.multiple(near["market_cap"], denominator)
        near_perimeters[name] = {
            "basis": f"trailing_{days}",
            "denominator": denominator,
            "multiple": multiple,
            "ratio_to_peer_median": None if multiple is None else multiple / peer_median,
        }
    holders_since_break = _since(series["holders"], break_day)
    near_perimeters["BASE+HOLDERS"]["holders_annualized_since_regime_break"] = m.annualized(
        holders_since_break, as_of, days, max_missing=gaps)
    near_perimeters["BASE+HOLDERS"]["holders_days"] = m.window_days(
        holders_since_break, as_of, days, allow_late_start=True)

    last = _intents_window(series, as_of, break_day, gaps)
    prior = _intents_window(series, m.shift_date(as_of, -RUN_RATE_DAYS), break_day, gaps)
    run_rate = {key: None if last[key] is None else last[key] * 365 / RUN_RATE_DAYS
                for key in ("net", "gross", "holders")}

    falsification = _falsification(config, near_perimeters, last, prior)
    add_one = _add_one(raw_dir, config, as_of, peers, near_perimeters["BASE+NET"]["multiple"])

    return {"as_of": as_of, "trailing_days": days, "chains": chains,
            "peer_median_multiple": peer_median, "add_one": add_one,
            "near_perimeters": near_perimeters,
            "intents": {"regime_break": break_day,
                        "windows": {"last_90d": last, "prior_90d": prior},
                        "run_rate_90d": run_rate},
            "falsification": falsification}


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
