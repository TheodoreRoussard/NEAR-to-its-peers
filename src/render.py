"""Static dashboard: metrics.json -> docs/index.html.

Pure formatting. Every number on the page comes from metrics.json: this module only
formats, orders and places them. No scripts and no external assets, so the page works
offline and over file://. Never reads the wall clock.
"""
import html
import math
from pathlib import Path

from src.fmt import (fmt_change, fmt_day, fmt_multiple, fmt_percent, fmt_ratio,  # noqa: F401
                     fmt_short_day, fmt_usd)
from src import narrative as n
from src.narrative import (CRITERIA, PERIMETER_NOTES, holders_note,  # noqa: F401
                           perimeter_dependence, rank_note, statistic_text)

REPO = "https://github.com/TheodoreRoussard/NEAR-to-its-peers"
CONFIG_URL = f"{REPO}/blob/main/config/panel.toml"
THESIS_URL = f"{REPO}/blob/main/THESIS.md"


# ---------- explanatory copy (no numbers: every number on the page comes from metrics.json) ----------

KEY_POINT_TITLES = [
    ("Like for like, how is NEAR valued?", "multiples"),
    ("Counting the revenue Intents brings, how is NEAR valued?", "perimeters"),
    ("Is the Intents revenue durable?", "intents"),
    ("Do NEAR holders capture that revenue?", "buybacks"),
    ("How robust is the comparison?", "variants"),
]

HOW_STEPS = [
    ("Collect the data",
     "Daily fees and revenue come from DefiLlama, daily market caps and prices from CoinGecko. "
     "One snapshot is committed with the code and dated by the last day every series covers, "
     "so anyone can rebuild every figure offline."),
    ("Compute a multiple for each chain",
     "Market cap divided by the fees paid over the trailing year. It reads like a "
     "price-to-sales ratio: how many dollars of market value the market assigns to each dollar "
     "of yearly fees. A lower multiple means the market pays less per dollar of activity."),
    ("Compare NEAR with its peers",
     "The peers are chosen by a written rule, not by hand: smart-contract base chains with a "
     "DefiLlama fee series and a top CoinGecko rank. NEAR's multiple is divided by the median "
     "of the peers' multiples. Below one, NEAR is valued below its typical peer."),
    ("Decide which NEAR fees count",
     "Most of NEAR's recent revenue comes from NEAR Intents, an application, not from "
     "base-layer gas. NEAR is therefore measured under four perimeters, from base-layer fees "
     "only to all Intents fees, and the thesis states which one it defends and why."),
    ("Set tripwires in advance",
     "Four falsification criteria (C1 to C4) say what result would prove the thesis wrong. "
     "Their thresholds were frozen in a tagged commit, and every verdict on this page is "
     "computed from the data, never typed."),
    ("Rebuild it yourself",
     "Run make judge-demo in the repository. It rebuilds the numbers, this page and THESIS.md "
     "from the snapshot and runs the tests, with nothing to install and no network."),
]

GLOSSARY = [
    ("Multiple", "Market cap divided by the fees of the trailing year."),
    ("Peer median", "The middle value of the peers' multiples. NEAR and the candidate chains "
                    "are left out of it."),
    ("Ratio to the peer median", "NEAR's multiple divided by the peer median. Below one, NEAR "
                                 "is valued below its typical peer; above one, above it."),
    ("Perimeter", "A definition of which fees count as NEAR's. BASE counts base-layer fees "
                  "only, like for like with the peers. BASE+NET adds the Intents revenue "
                  "NEAR's ecosystem keeps: the defended reading. BASE+HOLDERS adds the Intents "
                  "revenue booked as holders revenue. BASE+GROSS adds all Intents fees: an "
                  "upper bound only."),
    ("NEAR Intents", "A cross-chain swap service built on NEAR. Users pay fees, and part of "
                     "them stays with NEAR's ecosystem."),
    ("Regime break", "The day from which DefiLlama books Intents revenue daily. Earlier data "
                     "is not comparable, so the window-to-window tests start there."),
    ("Buyback", "Intents revenue used to buy NEAR on the market. It reaches holders only if "
                "the NEAR bought is burned or locked."),
    ("Tripwire", "A falsification criterion fixed in advance. If it fires, that part of the "
                 "thesis is wrong."),
]


def e(text):
    return html.escape(str(text), quote=True)


# ---------- chart geometry ----------

def log_position(value, lo, hi, width):
    """Pixel position of `value` on a log axis from lo to hi, clamped to [0, width]."""
    if value is None or value <= lo:
        return 0
    if value >= hi:
        return width
    return (math.log10(value) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * width


def px(value):
    return f"{value:.1f}"


# ---------- building blocks ----------

def link(url, text):
    return f'<a href="{e(url)}">{e(text)}</a>' if url else e(text)


def verdict_badge(verdict):
    return f'<span class="badge {e(verdict)}">{e(verdict)}</span>'


def section(anchor, title, body, source, method, takeaway):
    return (f'<section class="chart" id="{e(anchor)}">\n<h2>{e(title)}</h2>\n'
            f'<p class="takeaway">{takeaway}</p>\n{body}\n'
            f'<p class="method"><strong>Method.</strong> {method}</p>\n'
            f'<p class="source"><strong>Source.</strong> {source}</p>\n</section>')


def table(head, rows, attrs=None):
    attrs = attrs or [""] * len(rows)
    out = ["<div class=\"table\"><table><thead><tr>"]
    out += [f"<th>{h}</th>" for h in head]
    out.append("</tr></thead><tbody>")
    for row, attr in zip(rows, attrs):
        out.append(f"<tr{attr}>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def fee_sources(metrics):
    """Fees API and methodology link of every chain, plus the market-cap endpoint."""
    items = []
    for name, chain in metrics["chains"].items():
        s = chain.get("sources") or {}
        items.append(f"{e(name)}: {link(s.get('fees'), 'fees API')}, "
                     f"{link(s.get('fees_methodology'), 'methodology')}, "
                     f"{link(s.get('market_cap'), 'market cap')}")
    return "DefiLlama and CoinGecko. " + "; ".join(items) + "."


def intents_sources(metrics):
    s = metrics["intents"].get("sources") or {}
    return (f"DefiLlama, NEAR Intents: {link(s.get('net'), 'revenue')}, "
            f"{link(s.get('gross'), 'fees')}, {link(s.get('holders'), 'holders revenue')}, "
            f"{link(s.get('methodology'), 'methodology')}.")


# ---------- charts ----------

def multiples_chart(metrics):
    rows = [(name, c["multiple"], "peer") for name, c in metrics["chains"].items()
            if name != "NEAR"]
    rows += [(f"NEAR {name}", p["multiple"], "upper" if name == "BASE+GROSS" else "near")
             for name, p in metrics["near_perimeters"].items()]
    rows = sorted((r for r in rows if r[1] is not None), key=lambda r: r[1])
    if not rows:
        return '<p class="empty">not enough data</p>'
    lo = 10 ** math.floor(math.log10(min(r[1] for r in rows)))
    hi = 10 ** math.ceil(math.log10(max(r[1] for r in rows)))
    label_w, plot_w, row_h, top = 150, 520, 28, 24
    height = top + row_h * len(rows) + 8
    out = [f'<div class="plot"><svg viewBox="0 0 {label_w + plot_w + 70} {height}" role="img" '
           f'aria-label="Multiples by chain, log scale">']
    decade = lo
    while decade <= hi:
        x = label_w + log_position(decade, lo, hi, plot_w)
        out.append(f'<line class="grid" x1="{px(x)}" y1="{top - 6}" x2="{px(x)}" y2="{height}"/>'
                   f'<text class="axis" x="{px(x)}" y="{top - 10}" text-anchor="middle">'
                   f'{fmt_multiple(decade)}</text>')
        decade *= 10
    for i, (label, value, kind) in enumerate(rows):
        y = top + i * row_h
        w = max(log_position(value, lo, hi, plot_w), 1)
        out.append(f'<text class="label {kind}" x="{label_w - 8}" y="{y + 18}" '
                   f'text-anchor="end">{e(label)}</text>'
                   f'<rect class="bar {kind}" x="{label_w}" y="{y + 5}" width="{px(w)}" '
                   f'height="{row_h - 10}" rx="2"><title>{e(label)}: {fmt_multiple(value)}'
                   f'</title></rect>'
                   f'<text class="value" x="{px(label_w + w + 6)}" y="{y + 18}">'
                   f'{fmt_multiple(value)}</text>')
    median_x = label_w + log_position(metrics["peer_median_multiple"], lo, hi, plot_w)
    out.append(f'<line class="median" x1="{px(median_x)}" y1="{top - 2}" x2="{px(median_x)}" '
               f'y2="{height}"/></svg></div>')
    out.append(f'<p class="legend"><span class="key near"></span>NEAR perimeter '
               f'<span class="key upper"></span>NEAR BASE+GROSS (upper bound only) '
               f'<span class="key peer"></span>Peer <span class="key median"></span>'
               f'Peer median {fmt_multiple(metrics["peer_median_multiple"])}</p>')
    return "".join(out)


def multiples_takeaway(metrics):
    peers = [c["multiple"] for n, c in metrics["chains"].items()
             if n != "NEAR" and c["multiple"] is not None]
    near = metrics["near_perimeters"]
    base, net = near["BASE"]["multiple"], near["BASE+NET"]["multiple"]
    if base is None or net is None or not peers:
        return "Not enough data to compare NEAR with its peers."
    base_text = ("higher than every peer" if base > max(peers)
                 else f"higher than {sum(p < base for p in peers)} of the {len(peers)} peers")
    return (f"On base-layer fees alone, NEAR's multiple ({fmt_multiple(base)}) is {base_text}. "
            f"Counting the Intents revenue the ecosystem captures (BASE+NET), it falls to "
            f"{fmt_multiple(net)}, {fmt_ratio(near['BASE+NET']['ratio_to_peer_median'])} times "
            f"the peer median: lower than {sum(p > net for p in peers)} of the "
            f"{len(peers)} peers.")


def variants_chart(metrics):
    variants = [v for v in metrics["panel_variants"] if v["near_base_net_ratio"] is not None]
    if not variants:
        return '<p class="empty">not enough data</p>'
    k = metrics["falsification"]["c1"]["threshold"]
    top_value = max([v["near_base_net_ratio"] for v in variants] + ([k] if k else []))
    label_w, plot_w, row_h, top = 150, 520, 28, 24
    scale = plot_w / (top_value * 1.15)
    height = top + row_h * len(variants) + 8
    out = [f'<div class="plot"><svg viewBox="0 0 {label_w + plot_w + 70} {height}" role="img" '
           f'aria-label="NEAR BASE+NET ratio to the peer median in each panel variant">']
    for i, v in enumerate(variants):
        y = top + i * row_h
        w = max(v["near_base_net_ratio"] * scale, 1)
        kind = "near" if v["label"] == "Panel" else "peer"
        out.append(f'<text class="label" x="{label_w - 8}" y="{y + 18}" text-anchor="end">'
                   f'{e(v["label"])}</text>'
                   f'<rect class="bar {kind}" x="{label_w}" y="{y + 5}" width="{px(w)}" '
                   f'height="{row_h - 10}" rx="2"><title>{e(v["label"])}: '
                   f'{fmt_ratio(v["near_base_net_ratio"])}</title></rect>'
                   f'<text class="value" x="{px(label_w + w + 6)}" y="{y + 18}">'
                   f'{fmt_ratio(v["near_base_net_ratio"])}</text>')
    if k:
        x = label_w + k * scale
        out.append(f'<line class="threshold" x1="{px(x)}" y1="{top - 6}" x2="{px(x)}" '
                   f'y2="{height}"/><text class="axis" x="{px(x)}" y="{top - 10}" '
                   f'text-anchor="middle">k = {fmt_ratio(k)}</text>')
    out.append("</svg></div>")
    return "".join(out)


def variants_takeaway(metrics):
    variants = [v for v in metrics["panel_variants"] if v["near_base_net_ratio"] is not None]
    c1 = metrics["falsification"]["c1"]
    if not variants:
        return "Not enough data."
    ratios = [v["near_base_net_ratio"] for v in variants]
    span = f"from {fmt_ratio(min(ratios))} to {fmt_ratio(max(ratios))}"
    if c1["threshold"] is None:
        return f"The NEAR BASE+NET ratio to the peer median ranges {span}; k is not set yet."
    if metrics["c1_verdict_same_in_all_variants"]:
        return (f"C1 {e(c1['verdict'])} in every panel variant: the NEAR BASE+NET ratio to the "
                f"peer median ranges {span}, against k = {fmt_ratio(c1['threshold'])}. "
                f"The verdict does not depend on which peer is in the panel. "
                f"{perimeter_dependence(metrics)} {rank_note(metrics)}")
    firing = ", ".join(e(v["label"]) for v in variants if v["c1_verdict"] == "fires")
    return (f"The C1 verdict depends on the panel: it fires in {firing}. The ratio ranges "
            f"{span}, against k = {fmt_ratio(c1['threshold'])}.")


def intents_chart(metrics):
    buckets = metrics["intents"]["buckets_30d"]
    if not buckets:
        return '<p class="empty">not enough data since the regime break</p>'
    left, plot_h, top, bar_gap = 10, 220, 24, 10
    width = 700
    slot = (width - left) / len(buckets)
    peak = max(b["gross"] for b in buckets) * 1.12
    height = top + plot_h + 40
    out = [f'<div class="plot"><svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="NEAR Intents net revenue and fees per window">']
    base_y = top + plot_h
    out.append(f'<line class="grid" x1="{left}" y1="{base_y}" x2="{width}" y2="{base_y}"/>')
    for i, b in enumerate(buckets):
        x = left + i * slot + bar_gap / 2
        w = slot - bar_gap
        gross_h = b["gross"] / peak * plot_h
        net_h = b["net"] / peak * plot_h
        out.append(f'<rect class="bar gross" x="{px(x)}" y="{px(base_y - gross_h)}" '
                   f'width="{px(w)}" height="{px(gross_h)}" rx="2"><title>Fees '
                   f'{fmt_usd(b["gross"])}</title></rect>'
                   f'<rect class="bar near" x="{px(x + w * 0.2)}" y="{px(base_y - net_h)}" '
                   f'width="{px(w * 0.6)}" height="{px(net_h)}" rx="2"><title>Net revenue '
                   f'{fmt_usd(b["net"])}</title></rect>'
                   f'<text class="value" x="{px(x + w / 2)}" y="{px(base_y - gross_h - 6)}" '
                   f'text-anchor="middle">{fmt_usd(b["net"])}</text>'
                   f'<text class="axis" x="{px(x + w / 2)}" y="{base_y + 16}" '
                   f'text-anchor="middle">{fmt_short_day(b["start"])}</text>'
                   f'<text class="axis" x="{px(x + w / 2)}" y="{base_y + 30}" '
                   f'text-anchor="middle">{fmt_short_day(b["end"])}</text>')
    out.append("</svg></div>")
    out.append('<p class="legend"><span class="key near"></span>Net revenue kept by NEAR '
               '(label) <span class="key gross"></span>Gross Intents fees</p>')
    return "".join(out)


def window_rows(metrics):
    windows = metrics["intents"]["windows"]
    rows = []
    for name, label in (("prior_90d", "Prior window"), ("last_90d", "Last window")):
        w = windows[name]
        rows.append([label, f"{fmt_day(w['start'])} to {fmt_day(w['end'])}",
                     fmt_usd(w["net"]), fmt_usd(w["gross"]), fmt_percent(w["net_over_gross"])])
    return rows


def intents_takeaway(metrics):
    c2 = metrics["falsification"]["c2"]
    if c2["statistic"] is None:
        return ("Not enough data since the regime break to compare two windows yet: "
                "C2 is pending.")
    threshold = ("not set" if c2["threshold"] is None
                 else f"a drop larger than {fmt_change(c2['threshold'])[1:]}")
    return (f"Intents net revenue in the last window is {fmt_change(c2['statistic'])} against "
            f"the prior one. C2 fires on {threshold}: it {verdict_badge(c2['verdict'])}.")


def capture_takeaway(metrics):
    c3 = metrics["falsification"]["c3"]
    windows = metrics["intents"]["windows"]
    if c3["statistic"] is None:
        return "Not enough data since the regime break to compare two windows yet: C3 is pending."
    threshold = ("not set" if c3["threshold"] is None
                 else f"a drop larger than {fmt_change(c3['threshold'])[1:]}")
    return (f"NEAR kept {fmt_percent(windows['last_90d']['net_over_gross'])} of Intents fees in "
            f"the last window, against {fmt_percent(windows['prior_90d']['net_over_gross'])} "
            f"before ({fmt_change(c3['statistic'])}). C3 fires on {threshold}: it "
            f"{verdict_badge(c3['verdict'])}.")


def buyback_card(metrics):
    c4 = metrics["falsification"]["c4"]
    items = [("Account", link(c4["source"], c4["source"].rsplit("/", 1)[-1])),
             ("Holdings", f"{c4['holdings_near']:,} NEAR"),
             ("Outflows", f"{c4['outflows_near']:,} NEAR ("
                          f"{e(c4['outflows_period'].replace('buyback_checked_on', fmt_day(c4['checked_on'])))})"),
             ("Outflow share", fmt_percent(c4["statistic"])),
             ("Burn or lock policy", e(c4["policy"])),
             ("Checked on", fmt_day(c4["checked_on"]))]
    return ('<dl class="card">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in items)
            + "</dl>")


def buyback_takeaway(metrics):
    c4 = metrics["falsification"]["c4"]
    base = metrics["near_perimeters"]["BASE"]["multiple"]
    if c4["policy"] == "none published":
        return (f"C4 {verdict_badge(c4['verdict'])}: no burn or lock policy is published, so "
                f"the bought-back NEAR can be spent again. Until that changes, the strict holder "
                f"reading stays BASE ({fmt_multiple(base)}).")
    return (f"C4 {verdict_badge(c4['verdict'])}: {fmt_percent(c4['statistic'])} of the "
            f"holdings have left the account, against z = {e(c4['threshold'])}%.")


def threshold_text(key, criterion):
    t = criterion["threshold"]
    if t is None:
        return "not set"
    return {"c1": f"k = {fmt_ratio(t)}", "c2": f"x = {fmt_ratio(t)}",
            "c3": f"y = {fmt_ratio(t)}", "c4": f"z = {e(t)}%"}[key]


def scorecard(metrics):
    rows, attrs = [], []
    for key, criterion in metrics["falsification"].items():
        code, name, claim = CRITERIA[key]
        rows.append([f"<strong>{code}</strong> {e(name)}",
                     f"{e(claim)}<br><code>{e(criterion['formula'])}</code>",
                     statistic_text(key, criterion), threshold_text(key, criterion),
                     verdict_badge(criterion["verdict"]), e(n.margin_short(metrics, key)),
                     e(n.CONSEQUENCES[key])])
        attrs.append(f' data-criterion="{e(key)}" data-verdict="{e(criterion["verdict"])}"')
    return table(["Criterion", "Claim and formula", "Statistic", "Threshold", "Verdict",
                  "Distance to firing", "If it fires"], rows, attrs)


def scorecard_takeaway(metrics):
    verdicts = {key: c["verdict"] for key, c in metrics["falsification"].items()}
    groups = []
    for verdict in ("holds", "fires", "pending"):
        codes = [CRITERIA[k][0] for k, v in verdicts.items() if v == verdict]
        if codes:
            plural = {"holds": "hold", "fires": "fire", "pending": "pending"}[verdict]
            groups.append(f"{', '.join(codes)} {verdict if len(codes) == 1 else plural}")
    text = "; ".join(groups) + "."
    if verdicts.get("c4") == "fires":
        text += (" A C4 that fires means the bought-back NEAR is not provably held for holders, "
                 "so the strict holder reading stays BASE.")
    return text


# ---------- the thesis, the key points and the method, before the evidence ----------

def tile(label, ratio, detail):
    return (f'<div class="tile"><p class="tile-label">{e(label)}</p>'
            f'<p class="tile-value">{fmt_ratio(ratio)}&times;</p>'
            f'<p class="tile-detail">{detail}</p></div>')


def hero(metrics, v):
    near, median = metrics["near_perimeters"], fmt_multiple(metrics["peer_median_multiple"])
    chips = "".join(
        f'<li><a class="chip {e(c["verdict"])}" href="#scorecard">'
        f'<strong>{CRITERIA[key][0]}</strong> {e(CRITERIA[key][1])} · {e(c["verdict"])}</a></li>'
        for key, c in metrics["falsification"].items())
    k = metrics["falsification"]["c1"]["threshold"]
    k_text = "" if k is None else f" C1 fires above k = {fmt_ratio(k)}."
    return f"""<section class="hero" id="thesis">
<p class="kicker">NEAR Hackathon · Investment Thesis track</p>
<h1>NEAR Against Its Peers</h1>
<p class="lede">For each dollar of fees paid on-chain, does the market value NEAR more or less than its peers? And which perimeter that includes NEAR Intents can be defended?</p>
<div class="answer">
<h2>The thesis</h2>
<p class="bottom-line">{e(n.bottom_line(metrics, v))}</p>
<div class="tiles">
{tile("Counting Intents revenue (BASE+NET)", near["BASE+NET"]["ratio_to_peer_median"],
      f"times the peer median: {fmt_multiple(near['BASE+NET']['multiple'])} against {median}")}
{tile("Like for like, base-layer fees only (BASE)", near["BASE"]["ratio_to_peer_median"],
      f"times the peer median: {fmt_multiple(near['BASE']['multiple'])} against {median}")}
</div>
<p class="why">{e(v["like_for_like_short"])} Below one, NEAR is valued below its typical peer.{k_text}</p>
<ul class="chips">{chips}</ul>
</div>
</section>"""


def key_points(metrics, v):
    bodies = [
        n.like_for_like(metrics, v),
        " ".join(x for x in (v["c1_claim"], n.c1_margin(metrics, v), n.post_break(metrics)) if x),
        " ".join((v["c2_claim"], n.bucket_sentence(metrics), v["c3_claim"])),
        " ".join((v["c4_claim"], holders_note(metrics))),
        " ".join((n.variants_sentence(metrics), rank_note(metrics))),
    ]
    items = "".join(f'<li><h3>{e(title)}</h3><p>{e(body)}</p>'
                    f'<p class="more"><a href="#{anchor}">See the evidence</a></p></li>'
                    for (title, anchor), body in zip(KEY_POINT_TITLES, bodies))
    return (f'<section class="explainer" id="key-points">\n<h2>Key points to look at</h2>\n'
            f'<p class="intro">Five questions a skeptical investor would ask, each answered from '
            f'the data and linked to its evidence below.</p>\n<ol class="points">{items}</ol>\n'
            f'</section>')


def how_it_works():
    steps = "".join(f"<li><h3>{e(title)}</h3><p>{e(text)}</p></li>" for title, text in HOW_STEPS)
    terms = "".join(f"<dt>{e(term)}</dt><dd>{e(text)}</dd>" for term, text in GLOSSARY)
    return (f'<section class="explainer" id="how">\n<h2>How the thesis is built</h2>\n'
            f'<ol class="steps">{steps}</ol>\n<h3>Terms used on this page</h3>\n'
            f'<dl class="glossary">{terms}</dl>\n</section>')


def toc():
    links = [("thesis", "The thesis"), ("key-points", "Key points"), ("how", "How it works"),
             ("scorecard", "Scorecard"), ("multiples", "Multiples"), ("perimeters", "Perimeters"),
             ("variants", "Panel"), ("intents", "Intents revenue"), ("capture", "Capture rate"),
             ("buybacks", "Buybacks"), ("float", "Dilution")]
    return ('<nav class="toc" aria-label="On this page">'
            + "".join(f'<a href="#{a}">{e(t)}</a>' for a, t in links) + "</nav>")


def perimeters_table(metrics):
    rows = [[f"<strong>{e(name)}</strong>", fmt_usd(p["denominator"]), fmt_multiple(p["multiple"]),
             fmt_ratio(p["ratio_to_peer_median"]), e(PERIMETER_NOTES.get(name, ""))]
            for name, p in metrics["near_perimeters"].items()]
    return table(["Perimeter", "Fees counted", "Multiple", "Ratio to peer median", "Meaning"], rows)


def float_table(metrics):
    rows = []
    for name, chain in metrics["chains"].items():
        fg = chain["float_growth"]
        if fg is None:
            rows.append([e(name), "n/a", "n/a", "n/a"])
            continue
        rows.append([e(name), f"{fmt_day(fg['start'])} to {fmt_day(fg['end'])}",
                     fmt_change(fg["growth"], 1), fmt_change(fg["annualized"], 1)])
    return table(["Chain", "Period", "Circulating supply change", "Annualized"], rows)


def float_takeaway(metrics):
    growth = {n: c["float_growth"]["annualized"] for n, c in metrics["chains"].items()
              if c["float_growth"] is not None}
    if "NEAR" not in growth:
        return "Not enough data."
    peers = [v for n, v in growth.items() if n != "NEAR"]
    return (f"NEAR's circulating supply grew {fmt_change(growth['NEAR'], 1)} a year, against "
            f"{fmt_change(min(peers), 1)} to {fmt_change(max(peers), 1)} for its peers. A chain that "
            f"issues tokens faster dilutes holders faster, whatever its multiple.")


# ---------- page ----------

STYLE = """
:root{--bg:#fbfaf7;--panel:#ffffff;--text:#1d1d1b;--muted:#6b6a65;--line:#e4e1d8;
--near:#0f7b6c;--near-soft:#9fd3c7;--peer:#b8b4a8;--gross:#e6e1d3;--median:#b5452b;
--holds:#0f7b6c;--fires:#b5452b;--pending:#8a6d1f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141413;--panel:#1d1d1b;
--text:#ecebe6;--muted:#a19f97;--line:#34332f;--near:#3fbfa8;--near-soft:#1f5d53;--peer:#5d5b55;
--gross:#3a3833;--median:#e07a5f;--holds:#3fbfa8;--fires:#e07a5f;--pending:#d4b45a}}
:root[data-theme="dark"]{--bg:#141413;--panel:#1d1d1b;--text:#ecebe6;--muted:#a19f97;
--line:#34332f;--near:#3fbfa8;--near-soft:#1f5d53;--peer:#5d5b55;--gross:#3a3833;
--median:#e07a5f;--holds:#3fbfa8;--fires:#e07a5f;--pending:#d4b45a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:960px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:2rem;margin:0 0 8px}h2{font-size:1.2rem;margin:0 0 8px}
.lede{font-size:1.1rem;color:var(--muted);margin:0 0 12px}
.meta,.method,.source,.legend{color:var(--muted);font-size:.9rem}
.notice{border-left:3px solid var(--pending);padding:8px 12px;background:var(--panel);margin:16px 0}
section.chart{background:var(--panel);border:1px solid var(--line);border-radius:8px;
padding:20px;margin:20px 0}
.takeaway{font-size:1.02rem}
.plot{overflow-x:auto;margin:8px 0}svg{width:100%;min-width:560px;height:auto;display:block}
svg text{fill:var(--text);font-size:12px}svg .axis{fill:var(--muted);font-size:11px}
.bar.near{fill:var(--near)}.bar.upper{fill:var(--near-soft)}.bar.peer{fill:var(--peer)}
.bar.gross{fill:var(--gross)}
.label.near,.label.upper{font-weight:600}
.grid{stroke:var(--line)}.median,.threshold{stroke:var(--median);stroke-width:2;stroke-dasharray:5 4}
.key{display:inline-block;width:12px;height:12px;border-radius:2px;margin:0 4px 0 12px;
vertical-align:-1px}.key.near{background:var(--near)}.key.upper{background:var(--near-soft)}
.key.peer{background:var(--peer)}.key.gross{background:var(--gross)}
.key.median{background:var(--median);height:3px;vertical-align:3px}
.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}code{font-size:.8rem;color:var(--muted)}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.8rem;font-weight:600;
color:var(--panel)}.badge.holds{background:var(--holds)}.badge.fires{background:var(--fires)}
.badge.pending{background:var(--pending)}
dl.card{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:8px 0}
dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
a{color:var(--near)}footer{color:var(--muted);font-size:.9rem;margin-top:32px}
.empty{color:var(--muted);font-style:italic}
.toc{position:sticky;top:0;z-index:2;display:flex;gap:6px 14px;flex-wrap:wrap;padding:10px 0;
background:var(--bg);border-bottom:1px solid var(--line);font-size:.85rem}
.toc a{color:var(--muted);text-decoration:none}.toc a:hover{color:var(--near)}
.hero{padding:28px 0 8px}.kicker{color:var(--near);font-weight:600;font-size:.85rem;
letter-spacing:.04em;text-transform:uppercase;margin:0 0 6px}
.answer{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--near);
border-radius:8px;padding:20px;margin:16px 0}
.bottom-line{font-size:1.12rem;line-height:1.6;margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:0 0 12px}
.tile{border:1px solid var(--line);border-radius:8px;padding:14px;background:var(--bg)}
.tile-label{margin:0;color:var(--muted);font-size:.85rem;font-weight:600}
.tile-value{margin:4px 0;font-size:2.2rem;font-weight:700;line-height:1.1}
.tile-detail{margin:0;color:var(--muted);font-size:.85rem}
.why{color:var(--muted);font-size:.92rem}
.chips{list-style:none;padding:0;margin:12px 0 0;display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-block;padding:4px 12px;border-radius:14px;font-size:.85rem;
text-decoration:none;color:var(--panel)}.chip.holds{background:var(--holds)}
.chip.fires{background:var(--fires)}.chip.pending{background:var(--pending)}
.meta-block{margin:0 0 8px}
section.explainer{margin:28px 0}.intro{color:var(--muted)}
ol.points,ol.steps{padding-left:0;list-style:none;counter-reset:item}
ol.points>li,ol.steps>li{counter-increment:item;background:var(--panel);border:1px solid var(--line);
border-radius:8px;padding:16px 16px 16px 56px;margin:12px 0;position:relative}
ol.points>li::before,ol.steps>li::before{content:counter(item);position:absolute;left:16px;top:16px;
width:28px;height:28px;border-radius:50%;background:var(--near);color:var(--panel);
font-weight:700;display:flex;align-items:center;justify-content:center;font-size:.9rem}
ol.points h3,ol.steps h3{margin:2px 0 6px;font-size:1.02rem}ol.points p,ol.steps p{margin:0 0 6px}
.more{font-size:.88rem}
dl.glossary{display:grid;grid-template-columns:minmax(120px,max-content) 1fr;gap:8px 16px}
dl.glossary dt{font-weight:600;color:var(--text)}
@media (max-width:560px){dl.glossary{grid-template-columns:1fr}dl.glossary dd{margin-bottom:8px}}
h2.part{font-size:1.5rem;margin:40px 0 4px}
[id]{scroll-margin-top:52px}
@media (max-width:560px){.toc{flex-wrap:nowrap;overflow-x:auto;white-space:nowrap}}
"""


def render(metrics):
    as_of, days = metrics["as_of"], metrics["trailing_days"]
    v = n.basics(metrics)
    c2_windows = window_rows(metrics)
    candidates = ", ".join(f"{e(row['name'])} {fmt_multiple(row['multiple'])}"
                           for row in metrics["add_one"])
    sections = [
        section("scorecard", "Falsification scorecard", scorecard(metrics),
                f"Formulas and thresholds in {link(CONFIG_URL, 'config/panel.toml')}.",
                "Each criterion is a tripwire: if it fires, that part of the thesis is wrong. "
                "The thresholds were frozen in one tagged commit (thresholds-frozen) after these "
                "numbers were visible and before "
                "the thesis was written.",
                scorecard_takeaway(metrics)),
        section("multiples", "Market cap per dollar of yearly fees", multiples_chart(metrics),
                fee_sources(metrics),
                f"Multiple = market cap on {fmt_day(as_of)} / fees summed over the trailing "
                f"{days} days. Log scale. NEAR appears under its four perimeters; the peer "
                f"median uses the peers only, never NEAR or the candidate chains. Peers are "
                f"measured on base-layer fees only: only NEAR BASE is like for like, while "
                f"BASE+NET also counts NEAR's application revenue from Intents.",
                multiples_takeaway(metrics)),
        section("perimeters", "Which NEAR fees count", perimeters_table(metrics),
                intents_sources(metrics),
                f"Every perimeter is a trailing {days}-day sum ending on {fmt_day(as_of)}, "
                f"divided into NEAR's market cap on that day.",
                "The multiple depends on which fees count as NEAR's. BASE+NET is the defended "
                "reading; BASE+GROSS is an upper bound only. " + e(holders_note(metrics))),
        section("variants", "Does the result depend on the panel?", variants_chart(metrics),
                f"Panel rule and candidates in {link(CONFIG_URL, 'config/panel.toml')}; "
                f"fees and market caps as above.",
                f"Ratio = NEAR BASE+NET multiple / median of the peer multiples. "
                f"'+ X' adds a candidate chain to the peers ({candidates}); '- X' drops one "
                f"peer. C1 fires to the right of k.",
                variants_takeaway(metrics)),
        section("intents", "NEAR Intents revenue since the regime break", intents_chart(metrics)
                + table(["Window", "Dates", "Net revenue", "Gross fees", "Net / gross"],
                        c2_windows),
                intents_sources(metrics),
                f"Whole windows ending on {fmt_day(as_of)}, none before "
                f"{fmt_day(metrics['intents']['regime_break'])}: revenue is booked daily only "
                f"since then, so earlier data is not comparable. C2 compares the last window "
                f"with the prior one.",
                intents_takeaway(metrics)),
        section("capture", "How much of Intents fees NEAR keeps", table(
                ["Window", "Dates", "Net / gross"], [[r[0], r[1], r[4]] for r in c2_windows]),
                intents_sources(metrics),
                "Net / gross = Intents revenue kept by NEAR divided by all Intents fees, per "
                "window. C3 compares the last window with the prior one.",
                capture_takeaway(metrics)),
        section("buybacks", "Do the buybacks reach holders?", buyback_card(metrics),
                f"On-chain account: {link(metrics['falsification']['c4']['source'], 'nearblocks')}.",
                "Outflows are transfers out of the buyback account since the first buyback. "
                "A burn or lock policy would make the bought-back NEAR provably unspendable.",
                buyback_takeaway(metrics)),
        section("float", "Dilution: circulating supply growth", float_table(metrics),
                fee_sources(metrics),
                "Circulating supply = market cap / price, compared at the start and the end of "
                "the period, then annualized.",
                float_takeaway(metrics)),
    ]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEAR Against Its Peers</title>
<meta name="description" content="An investment thesis on NEAR: its market cap per dollar of fees against five peer chains, which NEAR Intents revenue can count, and four tripwires that would prove it wrong. Not financial advice.">
<style>{STYLE}</style>
</head>
<body>
<main>
{toc()}
{hero(metrics, v)}
<header class="meta-block">
<p class="meta">Data as of <time datetime="{e(as_of)}">{fmt_day(as_of)}</time> · trailing {days} days · {link(THESIS_URL, 'the thesis')} · {link(REPO, 'code and data')} · Data from <a href="https://defillama.com">DefiLlama</a> · Powered by <a href="https://www.coingecko.com">CoinGecko</a> · Not financial advice.</p>
<p class="notice">The falsification thresholds (k, x, y, z) were frozen after these numbers were visible. The rationale for each one sits next to it in {link(CONFIG_URL, 'config/panel.toml')}.</p>
</header>
{key_points(metrics, v)}
{how_it_works()}
<h2 class="part" id="evidence">The evidence</h2>
<p class="intro">Each section shows one piece of evidence: a sentence on what it says, the chart or table, the method and the source.</p>
{chr(10).join(sections)}
<footer>
<p>Fees and revenue: <a href="https://defillama.com">DefiLlama</a>. Market caps and prices: Powered by <a href="https://www.coingecko.com">CoinGecko</a>. Buyback account: nearblocks. The data belongs to its providers and is not covered by the code license (see <a href="https://github.com/TheodoreRoussard/NEAR-to-its-peers/blob/main/data/README.md">data/README.md</a>). Rebuild everything offline with <code>make judge-demo</code>. Code under the MIT license. Not financial advice.</p>
</footer>
</main>
</body>
</html>
"""


def write(metrics, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(metrics))
