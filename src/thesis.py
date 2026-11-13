"""THESIS.template.md + metrics.json -> THESIS.md.

The template holds no digits outside {{placeholders}}: every number comes from
metrics.json. The sentences come from src/narrative.py, shared with the dashboard;
this module only adds the markdown tables and lists. Never reads the wall clock.
"""
import re
from pathlib import Path

from src import narrative as n
from src.fmt import dates, fmt_multiple, fmt_percent, fmt_ratio, fmt_usd, listing

PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


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


def usd(value):
    """Dollar amounts with the sign escaped: GitHub reads a pair of bare dollars as math."""
    return fmt_usd(value).replace("$", "\\$")


def md(text):
    """Escape the dollar signs of a plain-text sentence for GitHub markdown."""
    return text.replace("$", "\\$")


def evidence(m, v):
    """Bullets for and against, each placed by what the data currently says."""
    f = m["falsification"]
    pro, con = [], []
    c1_text = " ".join(x for x in (v["c1_claim"], v["c1_margin"], md(n.post_break(m))) if x)
    (pro if f["c1"]["verdict"] == "holds" else con).append(c1_text)
    if m["c1_verdict_same_in_all_variants"] and f["c1"]["verdict"] == "holds":
        pro.append(md(n.variants_sentence(m)))
    else:
        con.append(md(n.variants_sentence(m)))
    for key in ("c2", "c3"):
        c = f[key]
        good = c["verdict"] == "holds" and c["statistic"] is not None and c["statistic"] >= 0
        (pro if good else con).append(v[f"{key}_claim"])
    buckets = m["intents"]["buckets_30d"]
    peak_is_last = bool(buckets) and buckets[-1] is max(buckets, key=lambda b: b["net"])
    (pro if peak_is_last else con).append(n.bucket_sentence(m, money=usd))
    favourable, text = n.float_sentence(m)
    (pro if favourable else con).append(text)
    con.insert(0, n.like_for_like(m, v))
    if (m.get("panel") or {}).get("rank_rule_failures"):
        con.append(md(n.rank_note(m)))
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
                     f"{v['window_days']} days fell below {fmt_percent(share)}.")
    c4 = mg.get("c4", {})
    if c4:
        items.append(f"**C4:** policy test {c4['policy_test']}; outflow-share test "
                     f"{c4['outflow_test']}. Publishing a burn or lock policy would leave only the "
                     f"outflow test.")
    return "\n".join(f"- {line}" for line in items)


def bucket_table(m):
    rows = ["| Block | Net revenue | Gross fees |", "|---|---|---|"]
    rows += [f"| {dates(b['start'], b['end'])} | {usd(b['net'])} | {usd(b['gross'])} |"
             for b in m["intents"]["buckets_30d"]]
    return "\n".join(rows) if len(rows) > 2 else "No full block since the regime break yet."


def perimeters_table(m):
    rows = ["| Perimeter | Fees counted | Multiple | Ratio to peer median | Meaning |",
            "|---|---|---|---|---|"]
    rows += [f"| **{name}** | {usd(p['denominator'])} | {fmt_multiple(p['multiple'])} | "
             f"{fmt_ratio(p['ratio_to_peer_median'])} | {n.PERIMETER_NOTES.get(name, '')} |"
             for name, p in m["near_perimeters"].items()]
    return "\n".join(rows)


def chains_table(m):
    reasons = m.get("panel", {}).get("reasons", {})
    rows = ["| Chain | Market cap | Trailing fees | Multiple | Why it is in the panel |",
            "|---|---|---|---|---|"]
    rows += [f"| {name} | {usd(c['market_cap'])} | {usd(c['fees_trailing'])} | "
             f"{fmt_multiple(c['multiple'])} | {reasons.get(name) or ''} |"
             for name, c in m["chains"].items()]
    return "\n".join(rows)


def candidates_list(m):
    reasons = m.get("panel", {}).get("candidate_reasons", {})
    return "\n".join(f"- **{row['name']}** ({fmt_multiple(row['multiple'])}): "
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
    v = n.basics(m, money=usd)
    v["like_for_like"] = n.like_for_like(m, v)
    v["like_for_like_short"] = (
        f"Peers are measured on base-layer fees only. The first number (BASE+NET, "
        f"{v['base_net_multiple']}) also counts the application revenue NEAR captures through "
        f"Intents, which no peer gets for its own applications; the second (BASE, "
        f"{v['base_multiple']}) is the like-for-like comparison.")
    v["bottom_line"] = n.bottom_line(m, v)
    v["c1_margin"] = n.c1_margin(m, v, money=usd)
    v["post_break"] = md(n.post_break(m))
    v["holders_note"] = md(n.holders_note(m))
    v["rank_note"] = md(n.rank_note(m))
    v["variants"] = md(n.variants_sentence(m))
    v["margins"] = margins_list(m, v)
    v["verdict_summary"] = n.verdict_summary(m["falsification"])
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
