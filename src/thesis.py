"""THESIS.template.md + metrics.json -> THESIS.md.

The template holds no digits outside {{placeholders}}: every number comes from
metrics.json, formatted here. Sentences that assert a verdict or a direction are
generated from the data, so a refreshed snapshot cannot leave a stale claim behind.
Never reads the wall clock.
"""
import re
from datetime import date
from pathlib import Path

from src import render as r

PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
PERIMETER_KEYS = {"BASE": "base", "BASE+NET": "base_net", "BASE+HOLDERS": "base_holders",
                  "BASE+GROSS": "base_gross"}


class UnknownPlaceholder(KeyError):
    """The template names a value that values() does not produce."""


def digits_outside_placeholders(template):
    """Lines of the template that still contain a digit once placeholders are removed."""
    return [line for line in template.splitlines() if re.search(r"\d", PLACEHOLDER.sub("", line))]


def fill(template, values):
    def substitute(match):
        key = match.group(1)
        if key not in values:
            raise UnknownPlaceholder(key)
        return values[key]
    return PLACEHOLDER.sub(substitute, template)


# ---------- markdown-safe formats ----------

def usd(value):
    """Dollar amounts with the sign escaped: GitHub reads a pair of bare dollars as math."""
    return r.fmt_usd(value).replace("$", "\\$")


def md(text):
    """Escape the dollar signs of a plain-text sentence for GitHub markdown."""
    return text.replace("$", "\\$")


def drop(share):
    return "not set" if share is None else f"{share * 100:.0f}%"


def days_between(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def dates(start, end):
    return f"{r.fmt_day(start)} to {r.fmt_day(end)}"


def listing(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ---------- sentences that follow the data ----------

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


def c1_margin(m, v):
    c1, margin = m["falsification"]["c1"], m.get("margins", {}).get("c1", {})
    breakeven, share = margin.get("intents_net_breakeven"), margin.get("intents_net_drop_to_fire")
    if c1["verdict"] != "holds" or breakeven is None:
        return ""
    if share is None:
        return ("Base-layer fees alone keep the ratio below k, so no fall in Intents revenue "
                "could make C1 fire.")
    return (f"Holding NEAR's market cap and the peer median fixed, C1 would fire only if "
            f"trailing-year Intents net revenue fell below {usd(breakeven)}, a drop of "
            f"{share * 100:.0f}%.")


def post_break(m):
    pb, c1 = m.get("post_break_reading"), m["falsification"]["c1"]
    if not pb or pb["ratio_to_peer_median"] is None:
        return ""
    tail = ("too" if pb["c1_verdict"] == c1["verdict"]
            else f"too, while it {c1['verdict']} on the trailing year")
    return (f"Counting only Intents revenue booked since the regime break, annualized, the ratio "
            f"is {r.fmt_ratio(pb['ratio_to_peer_median'])} ({r.fmt_multiple(pb['multiple'])}): "
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
    span = f"from {r.fmt_ratio(min(ratios))} to {r.fmt_ratio(max(ratios))}"
    if m["c1_verdict_same_in_all_variants"]:
        return (f"Across the panel itself and {len(variants) - 1} variants (adding either "
                f"candidate chain or dropping any one peer), the NEAR BASE+NET ratio moves {span}, "
                f"and the C1 verdict stays the same in every one. {r.perimeter_dependence(m)}")
    firing = listing([x["label"] for x in variants if x["c1_verdict"] == "fires"])
    return (f"The C1 verdict depends on the panel: the NEAR BASE+NET ratio ranges {span}, and "
            f"C1 fires in these panels: {firing}. {r.perimeter_dependence(m)}")


def bucket_sentence(m):
    buckets = m["intents"]["buckets_30d"]
    if not buckets:
        return "No full block of data since the regime break yet."
    first, last = buckets[0], buckets[-1]
    peak = max(buckets, key=lambda b: b["net"])
    tail = ("the latest block is the highest" if last is peak
            else f"the latest block, {usd(last['net'])}, is below that peak")
    return (f"Over {days_between(first['start'], first['end'])}-day blocks, Intents net revenue "
            f"went from {usd(first['net'])} ({dates(first['start'], first['end'])}) to a peak of "
            f"{usd(peak['net'])} ({dates(peak['start'], peak['end'])}); {tail}.")


def float_sentence(m):
    growth = {n: c["float_growth"] for n, c in m["chains"].items() if c["float_growth"]}
    if "NEAR" not in growth or len(growth) < 2:
        return None, "There is not enough market data to compare supply growth."
    near = growth["NEAR"]["annualized"]
    peers = sorted(g["annualized"] for n, g in growth.items() if n != "NEAR")
    faster = sum(p > near for p in peers)
    text = (f"NEAR's circulating supply grew {r.fmt_change(near, 1)} a year, measured from "
            f"{r.fmt_day(growth['NEAR']['start'])} to {r.fmt_day(growth['NEAR']['end'])}, against "
            f"{r.fmt_change(peers[0], 1)} to {r.fmt_change(peers[-1], 1)} for its peers; "
            f"{faster} of the {len(peers)} peers diluted their holders faster.")
    return faster >= len(peers) / 2, text


def evidence(m, v):
    """Bullets for and against, each placed by what the data currently says."""
    f = m["falsification"]
    pro, con = [], []
    c1_text = " ".join(x for x in (v["c1_claim"], v["c1_margin"], md(post_break(m))) if x)
    (pro if f["c1"]["verdict"] == "holds" else con).append(c1_text)
    if m["c1_verdict_same_in_all_variants"] and f["c1"]["verdict"] == "holds":
        pro.append(md(variants_sentence(m)))
    else:
        con.append(md(variants_sentence(m)))
    for key in ("c2", "c3"):
        c = f[key]
        good = c["verdict"] == "holds" and c["statistic"] is not None and c["statistic"] >= 0
        (pro if good else con).append(v[f"{key}_claim"])
    buckets = m["intents"]["buckets_30d"]
    peak_is_last = bool(buckets) and buckets[-1] is max(buckets, key=lambda b: b["net"])
    (pro if peak_is_last else con).append(bucket_sentence(m))
    favourable, text = float_sentence(m)
    (pro if favourable else con).append(text)
    con.insert(0, like_for_like(m, v))
    if (m.get("panel") or {}).get("rank_rule_failures"):
        con.append(md(r.rank_note(m)))
    (pro if f["c4"]["verdict"] == "holds" else con).append(v["c4_claim"])
    return ("\n".join(f"- {line}" for line in pro) or "- None yet.",
            "\n".join(f"- {line}" for line in con))


def margins_list(m, v):
    """How far each criterion is from firing, one bullet each."""
    f, mg = m["falsification"], m.get("margins", {})
    items = []
    items.append(f"**C1:** {v['c1_margin'] or 'no margin to report while C1 ' + f['c1']['verdict'] + '.'}")
    level = mg.get("c2", {}).get("last_net_fires_below")
    if level is not None:
        items.append(f"**C2:** it would fire if Intents net revenue over the last "
                     f"{v['window_days']} days fell below {usd(level)}.")
    share = mg.get("c3", {}).get("last_share_fires_below")
    if share is not None:
        items.append(f"**C3:** it would fire if NEAR's share of Intents fees over the last "
                     f"{v['window_days']} days fell below {r.fmt_percent(share)}.")
    c4 = mg.get("c4", {})
    if c4:
        items.append(f"**C4:** policy test {c4['policy_test']}; outflow-share test "
                     f"{c4['outflow_test']}. Publishing a burn or lock policy would leave only the "
                     f"outflow test.")
    return "\n".join(f"- {line}" for line in items)


# ---------- tables and lists ----------

def bucket_table(m):
    rows = ["| Block | Net revenue | Gross fees |", "|---|---|---|"]
    rows += [f"| {dates(b['start'], b['end'])} | {usd(b['net'])} | {usd(b['gross'])} |"
             for b in m["intents"]["buckets_30d"]]
    return "\n".join(rows) if len(rows) > 2 else "No full block since the regime break yet."


def perimeters_table(m):
    rows = ["| Perimeter | Fees counted | Multiple | Ratio to peer median | Meaning |",
            "|---|---|---|---|---|"]
    rows += [f"| **{name}** | {usd(p['denominator'])} | {r.fmt_multiple(p['multiple'])} | "
             f"{r.fmt_ratio(p['ratio_to_peer_median'])} | {r.PERIMETER_NOTES.get(name, '')} |"
             for name, p in m["near_perimeters"].items()]
    return "\n".join(rows)


def chains_table(m):
    reasons = m.get("panel", {}).get("reasons", {})
    rows = ["| Chain | Market cap | Trailing fees | Multiple | Why it is in the panel |",
            "|---|---|---|---|---|"]
    rows += [f"| {name} | {usd(c['market_cap'])} | {usd(c['fees_trailing'])} | "
             f"{r.fmt_multiple(c['multiple'])} | {reasons.get(name) or ''} |"
             for name, c in m["chains"].items()]
    return "\n".join(rows)


def candidates_list(m):
    reasons = m.get("panel", {}).get("candidate_reasons", {})
    return "\n".join(f"- **{row['name']}** ({r.fmt_multiple(row['multiple'])}): "
                     f"{reasons.get(row['name']) or ''}" for row in m["add_one"]) or "- None."


def sources_list(m):
    lines = []
    for name, c in m["chains"].items():
        s = c.get("sources") or {}
        lines.append(f"- {name}: [fees API]({s.get('fees')}), "
                     f"[methodology]({s.get('fees_methodology')}), "
                     f"[market cap]({s.get('market_cap')})")
    s = m["intents"].get("sources") or {}
    lines.append(f"- NEAR Intents: [revenue]({s.get('net')}), [fees]({s.get('gross')}), "
                 f"[holders revenue]({s.get('holders')}), [methodology]({s.get('methodology')})")
    return "\n".join(lines)


def missing_days(m):
    gaps = [f"{name} ({', '.join(c['missing_days'])})" for name, c in m["chains"].items()
            if c["missing_days"]]
    gaps += [f"NEAR Intents {key} ({', '.join(days)})"
             for key, days in m["intents"]["missing_days"].items() if days]
    return listing(gaps) if gaps else "none"


# ---------- all values ----------

def values(m):
    f = m["falsification"]
    v = {"as_of": r.fmt_day(m["as_of"]), "as_of_iso": m["as_of"],
         "trailing_days": str(m["trailing_days"]),
         "peer_median": r.fmt_multiple(m["peer_median_multiple"]),
         "near_market_cap": usd(m["chains"]["NEAR"]["market_cap"]),
         "panel_rule": m.get("panel", {}).get("rule") or "not recorded",
         "fee_definition": m.get("panel", {}).get("fee_definition") or "not recorded",
         "regime_break": r.fmt_day(m["intents"]["regime_break"]),
         "regime_days": str(days_between(m["intents"]["regime_break"], m["as_of"]))}
    for key in ("c1", "c2", "c3", "c4"):
        v[key] = key.upper()
        v[f"{key}_formula"] = f[key]["formula"]
        v[f"{key}_verdict"] = f[key]["verdict"]
        v[f"{key}_statistic"] = r.statistic_text(key, f[key])
    t = {k: f[c]["threshold"] for k, c in (("k", "c1"), ("x", "c2"), ("y", "c3"), ("z", "c4"))}
    v.update(k=r.fmt_ratio(t["k"]) if t["k"] is not None else "not set",
             x=drop(t["x"]), y=drop(t["y"]),
             z="not set" if t["z"] is None else f"{t['z']}%")
    for name, p in m["near_perimeters"].items():
        key = PERIMETER_KEYS[name]
        v[f"{key}_multiple"] = r.fmt_multiple(p["multiple"])
        v[f"{key}_fees"] = usd(p["denominator"])
    v["base_ratio"] = r.fmt_ratio(m["near_perimeters"]["BASE"]["ratio_to_peer_median"])

    windows = m["intents"]["windows"]
    last, prior = windows["last_90d"], windows["prior_90d"]
    v["window_days"] = str(days_between(last["start"], last["end"]))
    v["last_window"], v["prior_window"] = (dates(last["start"], last["end"]),
                                           dates(prior["start"], prior["end"]))

    c4 = f["c4"]
    v.update(holdings=f"{c4['holdings_near']:,} NEAR", outflows=f"{c4['outflows_near']:,} NEAR",
             buyback_policy=c4["policy"], buyback_checked_on=r.fmt_day(c4["checked_on"]),
             buyback_source=c4["source"],
             buyback_account=c4["source"].rsplit("/", 1)[-1])

    v["c1_claim"] = c1_claim(m, v)
    v["c2_claim"] = change_claim(m, v, "c2", "Intents net revenue", usd(prior["net"]),
                                 usd(last["net"]), "durability")
    v["c3_claim"] = change_claim(m, v, "c3", "the share of Intents fees NEAR keeps",
                                 r.fmt_percent(prior["net_over_gross"]),
                                 r.fmt_percent(last["net_over_gross"]), "capture")
    v["c4_claim"] = c4_claim(m, v)
    v["like_for_like"] = like_for_like(m, v)
    v["like_for_like_short"] = (
        f"Peers are measured on base-layer fees only. The first number (BASE+NET, "
        f"{v['base_net_multiple']}) also counts the application revenue NEAR captures through "
        f"Intents, which no peer gets for its own applications; the second (BASE, "
        f"{v['base_multiple']}) is the like-for-like comparison.")
    v["bottom_line"] = bottom_line(m, v)
    v["c1_margin"] = c1_margin(m, v)
    v["post_break"] = md(post_break(m))
    v["holders_note"] = md(r.holders_note(m))
    v["rank_note"] = md(r.rank_note(m))
    v["variants"] = md(variants_sentence(m))
    v["margins"] = margins_list(m, v)
    v["verdict_summary"] = verdict_summary(f)
    v["evidence_for"], v["evidence_against"] = evidence(m, v)
    v.update(bucket_table=bucket_table(m), perimeters_table=perimeters_table(m),
             chains_table=chains_table(m), candidates=candidates_list(m),
             sources=sources_list(m), missing_days=missing_days(m))
    fg = m["chains"]["NEAR"]["float_growth"]
    v["float_period"] = dates(fg["start"], fg["end"]) if fg else "not available"
    return v


def generate(metrics, template):
    return fill(template, values(metrics))


def write(metrics, template, path):
    path = Path(path)
    path.write_text(generate(metrics, template))
