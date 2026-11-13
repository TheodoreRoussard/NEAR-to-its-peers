"""Sentences shared by THESIS.md and the dashboard, generated from metrics.json.

Every sentence that asserts a verdict or a direction is built here from the data, so the
thesis and the dashboard say the same thing and a refreshed snapshot cannot leave a stale
claim. Amounts go through `money`, so the thesis can escape dollar signs for markdown.
"""
from src.fmt import (dates, days_between, drop, fmt_change, fmt_day, fmt_multiple,
                     fmt_percent, fmt_ratio, fmt_usd, listing)

PERIMETER_KEYS = {"BASE": "base", "BASE+NET": "base_net", "BASE+HOLDERS": "base_holders",
                  "BASE+GROSS": "base_gross"}

PERIMETER_NOTES = {
    "BASE": "Base-layer gas fees only. The strict holder reading.",
    "BASE+NET": "Plus the Intents revenue the NEAR ecosystem keeps. Captured revenue: "
                "the defended perimeter, assuming the treasury acts for holders.",
    "BASE+HOLDERS": "Plus the Intents revenue DefiLlama books as holders revenue: the part "
                    "that funds NEAR buybacks.",
    "BASE+GROSS": "Plus all Intents fees, most of which never reach NEAR. Upper bound only.",
}

CRITERIA = {
    "c1": ("C1", "Valuation", "NEAR BASE+NET is no more expensive than the peer median."),
    "c2": ("C2", "Durability", "Intents net revenue does not collapse from one window to the next."),
    "c3": ("C3", "Capture rate", "NEAR keeps its share of Intents fees."),
    "c4": ("C4", "Holder accrual", "Bought-back NEAR provably stays out of circulation."),
}

CONSEQUENCES = {
    "c1": "Even counting Intents, NEAR is not valued below its peers: the valuation case fails.",
    "c2": "Intents revenue is not durable: the captured-revenue reading loses its base.",
    "c3": "NEAR's cut of Intents fees is being competed away.",
    "c4": "Holders do not provably capture the revenue: the strict holder reading is BASE.",
}


def margin_short(m, key, money=fmt_usd):
    """One line on how far a criterion is from firing, for the scorecard."""
    mg = m.get("margins", {}).get(key, {})
    if key == "c1":
        share, breakeven = mg.get("intents_net_drop_to_fire"), mg.get("intents_net_breakeven")
        if share is not None:
            return f"Intents net revenue would have to fall {share * 100:.0f}%"
        if breakeven is not None and breakeven <= 0:
            return "No fall in Intents revenue could make it fire"
        return "n/a"
    if key == "c2":
        level = mg.get("last_net_fires_below")
        return "n/a" if level is None else f"Last-window net revenue below {money(level)}"
    if key == "c3":
        level = mg.get("last_share_fires_below")
        return "n/a" if level is None else f"Last-window share below {fmt_percent(level)}"
    if not mg:
        return "n/a"
    return f"Policy test {mg['policy_test']}; outflow-share test {mg['outflow_test']}"


def statistic_text(key, criterion):
    s = criterion["statistic"]
    return {"c1": fmt_ratio, "c2": fmt_change, "c3": fmt_change, "c4": fmt_percent}[key](s)


def holders_note(metrics):
    """What BASE+HOLDERS adds over BASE+NET, read from the data."""
    hv = metrics["intents"].get("holders_vs_net") or {}
    if hv.get("holders_equals_net_since_break"):
        return (f"Since the regime break ({fmt_day(metrics['intents']['regime_break'])}), Intents "
                f"holders revenue equals net revenue every day: all of it funds buybacks. "
                f"BASE+HOLDERS therefore differs from BASE+NET only by the "
                f"{fmt_usd(hv['net_before_break_in_trailing'])} of net revenue booked before the "
                f"break, which BASE+NET counts and BASE+HOLDERS does not. It is not a separate "
                f"test of the buyback assumption.")
    return ("Since the regime break, holders revenue differs from net revenue, so BASE+HOLDERS "
            "isolates the part of Intents revenue spent on buybacks.")


def rank_note(metrics):
    """Panel chains outside the rule's CoinGecko rank limit, with the effect of dropping them."""
    panel = metrics.get("panel") or {}
    limit, failures = panel.get("max_rank"), panel.get("rank_rule_failures") or []
    if limit is None:
        return "The rank limit of the panel rule is not recorded."
    if not failures:
        return (f"Every panel chain meets the rule's rank limit (top {limit} on CoinGecko) on "
                f"{fmt_day(metrics['as_of'])}.")
    variants = {v["label"]: v for v in metrics["panel_variants"]}
    notes = []
    for name in failures:
        rank = metrics["chains"][name]["market_cap_rank"]
        without = variants.get(f"- {name}")
        effect = ("" if without is None else
                  f" Without it, the NEAR BASE+NET ratio is {fmt_ratio(without['near_base_net_ratio'])}"
                  f" and C1 {without['c1_verdict']}.")
        notes.append(f"{name} ranks {rank} on CoinGecko on {fmt_day(metrics['as_of'])}, outside "
                     f"the rule's top {limit}; it stays in the panel, which was frozen with the "
                     f"thresholds.{effect}")
    return " ".join(notes)


def perimeter_dependence(metrics):
    base = metrics["near_perimeters"]["BASE"]["ratio_to_peer_median"]
    k = metrics["falsification"]["c1"]["threshold"]
    if base is None:
        return ""
    fires = "" if k is None else (f", above k, so C1 would fire on that reading" if base > k
                                  else ", still below k")
    return (f"The verdict depends on the perimeter, not on the panel: on BASE, like for like, "
            f"the ratio is {fmt_ratio(base)}{fires}.")


def verdict_summary(f):
    groups = []
    for verdict, plural in (("holds", "hold"), ("fires", "fire"), ("pending", "pending")):
        codes = [k.upper() for k, c in f.items() if c["verdict"] == verdict]
        if codes:
            groups.append(f"{listing(codes)} {verdict if len(codes) == 1 else plural}")
    return "; ".join(groups) + "."


def c1_claim(m, v):
    c1 = m["falsification"]["c1"]
    head = (f"Counting the Intents revenue its ecosystem captures (BASE+NET), NEAR trades at "
            f"{v['base_net_multiple']}, {v['c1_statistic']} times the peer median of "
            f"{v['peer_median']}")
    if c1["verdict"] == "holds":
        return f"{head}: below k = {v['k']}, so C1 holds."
    if c1["verdict"] == "fires":
        return f"{head}: above k = {v['k']}, so C1 fires and the valuation leg of the thesis fails."
    return f"{head}. k is not set, so C1 is pending."


def change_claim(m, v, key, subject, before, after, condition):
    c = m["falsification"][key]
    code = key.upper()
    if c["statistic"] is None:
        return (f"There is not enough data since the regime break to compare two windows of "
                f"{subject}: {code} is pending.")
    direction = "rose" if c["statistic"] >= 0 else "fell"
    size = f"{abs(c['statistic']) * 100:.0f}%"
    points = m.get("margins", {}).get("c3", {}).get("points_change")
    if key == "c3" and points is not None:
        size = f"by a relative {size} ({points * 100:+.2f} points)"
    head = (f"{subject[0].upper()}{subject[1:]} {direction} {size}, from "
            f"{before} over the prior {v['window_days']}-day window to {after} over the last one")
    if c["verdict"] == "fires":
        return (f"{head}: more than the {drop(c['threshold'])} drop {code} tolerates, so {code} "
                f"fires and the {condition} condition fails.")
    if c["verdict"] == "holds":
        return f"{head}. {code} fires only on a drop larger than {drop(c['threshold'])}: it holds."
    return f"{head}. Its threshold is not set, so {code} is pending."


def c4_claim(m, v):
    c4 = m["falsification"]["c4"]
    outflow = m.get("margins", {}).get("c4", {}).get("outflow_test")
    if c4["verdict"] == "fires" and c4["policy"] == "none published":
        tests = (f" C4 has two tests: the policy test fires, while the outflow-share test alone "
                 f"passes ({v['c4_statistic']} of the holdings, against z = {v['z']})."
                 if outflow == "holds" else
                 f" Both of its tests fire: no policy, and outflows of {v['c4_statistic']} of the "
                 f"holdings, above z = {v['z']}." if outflow == "fires" else "")
        return (f"No burn or lock policy is published for the buyback account, which holds "
                f"{v['holdings']}; {v['outflows']} have already left it. The bought-back NEAR can "
                f"be spent again, so it is not provably held for holders: C4 fires, and the strict "
                f"holder reading stays BASE ({v['base_multiple']}, {v['base_ratio']} times the peer "
                f"median).{tests}")
    if c4["verdict"] == "fires":
        return (f"A {c4['policy']} policy is published, but {v['c4_statistic']} of the holdings "
                f"left the account, above z = {v['z']}: C4 fires.")
    if c4["verdict"] == "holds":
        return (f"A {c4['policy']} policy is published and outflows stay at {v['c4_statistic']} "
                f"of the holdings, below z = {v['z']}: C4 holds, and BASE+HOLDERS "
                f"({v['base_holders_multiple']}) becomes a defensible holder reading.")
    return f"A {c4['policy']} policy is published but z is not set: C4 is pending."


def base_position(m):
    peers = [c["multiple"] for n, c in m["chains"].items()
             if n != "NEAR" and c["multiple"] is not None]
    base = m["near_perimeters"]["BASE"]["multiple"]
    if base is None or not peers:
        return "not comparable for lack of data"
    if base > max(peers):
        return "higher than every peer"
    return f"higher than {sum(p < base for p in peers)} of the {len(peers)} peers"


def bottom_line(m, v):
    f = {k: c["verdict"] for k, c in m["falsification"].items()}
    counted = (f"Counting the Intents revenue its ecosystem captures, NEAR is valued at "
               f"{v['c1_statistic']} times the peer median")
    valuation = {"holds": f"{counted}, below its typical peer",
                 "fires": f"Even {counted[0].lower()}{counted[1:]}, above its typical peer",
                 "pending": f"{counted}; the valuation test is pending"}[f["c1"]]
    valuation += (f"; like for like, on base-layer fees alone, it is valued at {v['base_ratio']} "
                  f"times, {base_position(m)}. On the captured-revenue reading")
    tripped = [k.upper() for k in ("c2", "c3") if f[k] == "fires"]
    if tripped:
        revenue = (f"the Intents revenue behind it weakened enough to trip "
                   f"{listing(tripped)}")
    elif f["c2"] == f["c3"] == "holds":
        revenue = "the Intents revenue behind it held up over the last window"
    else:
        revenue = "the durability of the Intents revenue behind it is still pending"
    if f["c4"] == "fires":
        holders = ("but holders do not yet provably capture that revenue. The investment case "
                   "rests on the treasury burning or locking what it buys back; until then the "
                   "strict holder reading is BASE.")
    elif f["c4"] == "holds":
        holders = "and the bought-back NEAR is provably held for holders."
    else:
        holders = "and whether holders capture it is still pending."
    return f"{valuation}, {revenue}, {holders}"


def c1_margin(m, v, money=fmt_usd):
    c1, margin = m["falsification"]["c1"], m.get("margins", {}).get("c1", {})
    breakeven, share = margin.get("intents_net_breakeven"), margin.get("intents_net_drop_to_fire")
    if c1["verdict"] != "holds" or breakeven is None:
        return ""
    if share is None:
        return ("Base-layer fees alone keep the ratio below k, so no fall in Intents revenue "
                "could make C1 fire.")
    return (f"Holding NEAR's market cap and the peer median fixed, C1 would fire only if "
            f"trailing-year Intents net revenue fell below {money(breakeven)}, a drop of "
            f"{share * 100:.0f}%.")


def post_break(m):
    pb, c1 = m.get("post_break_reading"), m["falsification"]["c1"]
    if not pb or pb["ratio_to_peer_median"] is None:
        return ""
    tail = ("too" if pb["c1_verdict"] == c1["verdict"]
            else f"too, while it {c1['verdict']} on the trailing year")
    return (f"Counting only Intents revenue booked since the regime break, annualized, the ratio "
            f"is {fmt_ratio(pb['ratio_to_peer_median'])} ({fmt_multiple(pb['multiple'])}): "
            f"C1 {pb['c1_verdict']} on that reading {tail}.")


def like_for_like(m, v):
    position = base_position(m)
    return (f"Peers are measured on base-layer fees only, while BASE+NET adds the application "
            f"revenue NEAR captures through Intents; no peer gets the same credit for its own "
            f"applications. Like for like, on base-layer fees alone, NEAR trades at "
            f"{v['base_multiple']}, {v['base_ratio']} times the peer median: {position}.")


def variants_sentence(m):
    variants = [x for x in m["panel_variants"] if x["near_base_net_ratio"] is not None]
    if not variants:
        return "There is not enough data to vary the panel."
    ratios = [x["near_base_net_ratio"] for x in variants]
    span = f"from {fmt_ratio(min(ratios))} to {fmt_ratio(max(ratios))}"
    if m["c1_verdict_same_in_all_variants"]:
        return (f"Across the panel itself and {len(variants) - 1} variants (adding either "
                f"candidate chain or dropping any one peer), the NEAR BASE+NET ratio moves {span}, "
                f"and the C1 verdict stays the same in every one. {perimeter_dependence(m)}")
    firing = listing([x["label"] for x in variants if x["c1_verdict"] == "fires"])
    return (f"The C1 verdict depends on the panel: the NEAR BASE+NET ratio ranges {span}, and "
            f"C1 fires in these panels: {firing}. {perimeter_dependence(m)}")


def bucket_sentence(m, money=fmt_usd):
    buckets = m["intents"]["buckets_30d"]
    if not buckets:
        return "No full block of data since the regime break yet."
    first, last = buckets[0], buckets[-1]
    peak = max(buckets, key=lambda b: b["net"])
    tail = ("the latest block is the highest" if last is peak
            else f"the latest block, {money(last['net'])}, is below that peak")
    return (f"Over {days_between(first['start'], first['end'])}-day blocks, Intents net revenue "
            f"went from {money(first['net'])} ({dates(first['start'], first['end'])}) to a peak of "
            f"{money(peak['net'])} ({dates(peak['start'], peak['end'])}); {tail}.")


def float_sentence(m):
    growth = {n: c["float_growth"] for n, c in m["chains"].items() if c["float_growth"]}
    if "NEAR" not in growth or len(growth) < 2:
        return None, "There is not enough market data to compare supply growth."
    near = growth["NEAR"]["annualized"]
    peers = sorted(g["annualized"] for n, g in growth.items() if n != "NEAR")
    faster = sum(p > near for p in peers)
    text = (f"NEAR's circulating supply grew {fmt_change(near, 1)} a year, measured from "
            f"{fmt_day(growth['NEAR']['start'])} to {fmt_day(growth['NEAR']['end'])}, against "
            f"{fmt_change(peers[0], 1)} to {fmt_change(peers[-1], 1)} for its peers; "
            f"{faster} of the {len(peers)} peers diluted their holders faster.")
    return faster >= len(peers) / 2, text


def basics(m, money=fmt_usd):
    """Formatted values and the per-criterion claims, as one dict."""
    f = m["falsification"]
    v = {"as_of": fmt_day(m["as_of"]), "as_of_iso": m["as_of"],
         "trailing_days": str(m["trailing_days"]),
         "peer_median": fmt_multiple(m["peer_median_multiple"]),
         "near_market_cap": money(m["chains"]["NEAR"]["market_cap"]),
         "panel_rule": m.get("panel", {}).get("rule") or "not recorded",
         "fee_definition": m.get("panel", {}).get("fee_definition") or "not recorded",
         "regime_break": fmt_day(m["intents"]["regime_break"]),
         "regime_days": str(days_between(m["intents"]["regime_break"], m["as_of"]))}
    for key in ("c1", "c2", "c3", "c4"):
        v[key] = key.upper()
        v[f"{key}_formula"] = f[key]["formula"]
        v[f"{key}_verdict"] = f[key]["verdict"]
        v[f"{key}_statistic"] = statistic_text(key, f[key])
    t = {k: f[c]["threshold"] for k, c in (("k", "c1"), ("x", "c2"), ("y", "c3"), ("z", "c4"))}
    v.update(k=fmt_ratio(t["k"]) if t["k"] is not None else "not set",
             x=drop(t["x"]), y=drop(t["y"]),
             z="not set" if t["z"] is None else f"{t['z']}%")
    for name, p in m["near_perimeters"].items():
        key = PERIMETER_KEYS[name]
        v[f"{key}_multiple"] = fmt_multiple(p["multiple"])
        v[f"{key}_fees"] = money(p["denominator"])
    v["base_ratio"] = fmt_ratio(m["near_perimeters"]["BASE"]["ratio_to_peer_median"])

    windows = m["intents"]["windows"]
    last, prior = windows["last_90d"], windows["prior_90d"]
    v["window_days"] = str(days_between(last["start"], last["end"]))
    v["last_window"], v["prior_window"] = (dates(last["start"], last["end"]),
                                           dates(prior["start"], prior["end"]))

    c4 = f["c4"]
    v.update(holdings=f"{c4['holdings_near']:,} NEAR", outflows=f"{c4['outflows_near']:,} NEAR",
             buyback_policy=c4["policy"], buyback_checked_on=fmt_day(c4["checked_on"]),
             buyback_source=c4["source"],
             buyback_account=c4["source"].rsplit("/", 1)[-1])

    v["c1_claim"] = c1_claim(m, v)
    v["c2_claim"] = change_claim(m, v, "c2", "Intents net revenue", money(prior["net"]),
                                 money(last["net"]), "durability")
    v["c3_claim"] = change_claim(m, v, "c3", "the share of Intents fees NEAR keeps",
                                 fmt_percent(prior["net_over_gross"]),
                                 fmt_percent(last["net_over_gross"]), "capture")
    v["c4_claim"] = c4_claim(m, v)
    v["like_for_like_short"] = (
        f"Peers are measured on base-layer fees only. The first number (BASE+NET, "
        f"{v['base_net_multiple']}) also counts the application revenue NEAR captures through "
        f"Intents, which no peer gets for its own applications; the second (BASE, "
        f"{v['base_multiple']}) is the like-for-like comparison.")
    return v
