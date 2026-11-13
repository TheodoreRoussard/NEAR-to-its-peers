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
    return f'<span class="verdict {e(verdict)}">{e(verdict)}</span>'


def section(anchor, title, body, source, method, takeaway):
    return (f'<section class="chart" id="{e(anchor)}">\n<h3>{e(title)}</h3>\n<figure>\n'
            f'<figcaption><span class="fig-label">Figure</span> '
            f'<span class="takeaway">{takeaway}</span></figcaption>\n{body}\n</figure>\n'
            f'<p class="method"><strong>Method.</strong> {method}</p>\n'
            f'<p class="source"><strong>Source.</strong> {source}</p>\n</section>')


def table(head, rows, attrs=None, wide=False):
    attrs = attrs or [""] * len(rows)
    out = [f'<div class="table{" wide" if wide else ""}"><table><thead><tr>']
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
    label_w, plot_w, row_h, top = 172, 500, 28, 24
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
                   f'height="{row_h - 10}" rx="1"><title>{e(label)}: {fmt_multiple(value)}'
                   f'</title></rect>'
                   f'<text class="value" x="{px(label_w + w + 6)}" y="{y + 18}">'
                   f'{fmt_multiple(value)}</text>')
    median_x = label_w + log_position(metrics["peer_median_multiple"], lo, hi, plot_w)
    out.append(f'<line class="median" x1="{px(median_x)}" y1="{top - 2}" x2="{px(median_x)}" '
               f'y2="{height}"/></svg></div>')
    out.append(f'<p class="legend"><span class="key near"></span>NEAR, by perimeter'
               f'<span class="key upper"></span>NEAR BASE+GROSS, upper bound only'
               f'<span class="key peer"></span>Peer<span class="key median"></span>'
               f'Peer median, {fmt_multiple(metrics["peer_median_multiple"])}</p>')
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
    label_w, plot_w, row_h, top = 172, 500, 28, 24
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
                   f'height="{row_h - 10}" rx="1"><title>{e(v["label"])}: '
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
                   f'width="{px(w)}" height="{px(gross_h)}" rx="1"><title>Fees '
                   f'{fmt_usd(b["gross"])}</title></rect>'
                   f'<rect class="bar near" x="{px(x + w * 0.2)}" y="{px(base_y - net_h)}" '
                   f'width="{px(w * 0.6)}" height="{px(net_h)}" rx="1"><title>Net revenue '
                   f'{fmt_usd(b["net"])}</title></rect>'
                   f'<text class="value" x="{px(x + w / 2)}" y="{px(base_y - gross_h - 6)}" '
                   f'text-anchor="middle">{fmt_usd(b["net"])}</text>'
                   f'<text class="axis" x="{px(x + w / 2)}" y="{base_y + 16}" '
                   f'text-anchor="middle">{fmt_short_day(b["start"])}</text>'
                   f'<text class="axis" x="{px(x + w / 2)}" y="{base_y + 30}" '
                   f'text-anchor="middle">{fmt_short_day(b["end"])}</text>')
    out.append("</svg></div>")
    out.append('<p class="legend"><span class="key near"></span>Net revenue kept by NEAR '
               '(labelled)<span class="key gross"></span>Gross Intents fees</p>')
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
    return ('<dl class="facts">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in items)
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
        rows.append([f"<strong>{code} {e(name)}</strong><br>{e(claim)}<br>"
                     f"<code>{e(criterion['formula'])}</code>",
                     statistic_text(key, criterion), threshold_text(key, criterion),
                     verdict_badge(criterion["verdict"]), e(n.margin_short(metrics, key)),
                     e(n.CONSEQUENCES[key])])
        attrs.append(f' data-criterion="{e(key)}" data-verdict="{e(criterion["verdict"])}"')
    return table(["Criterion, claim and formula", "Statistic", "Threshold", "Verdict",
                  "Distance to firing", "If it fires"], rows, attrs, wide=True)


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

def abstract(metrics, v):
    near, median = metrics["near_perimeters"], fmt_multiple(metrics["peer_median_multiple"])
    readings = table(
        ["Reading", "NEAR multiple", "Peer median", "Ratio to the peer median"],
        [["Counting Intents revenue (BASE+NET)", fmt_multiple(near["BASE+NET"]["multiple"]),
          median, f'<strong>{fmt_ratio(near["BASE+NET"]["ratio_to_peer_median"])}</strong>'],
         ["Like for like, base-layer fees only (BASE)", fmt_multiple(near["BASE"]["multiple"]),
          median, f'<strong>{fmt_ratio(near["BASE"]["ratio_to_peer_median"])}</strong>']])
    verdicts = ", ".join(
        f'{CRITERIA[key][0]} {e(CRITERIA[key][1].lower())} {verdict_badge(c["verdict"])}'
        for key, c in metrics["falsification"].items())
    k = metrics["falsification"]["c1"]["threshold"]
    k_text = "" if k is None else f" C1 fires above k = {fmt_ratio(k)}."
    return f"""<header class="masthead" id="thesis">
<h1>NEAR Against Its Peers</h1>
<p class="subtitle">For each dollar of fees paid on-chain, does the market value NEAR more or less than its peers? And which perimeter that includes NEAR Intents can be defended?</p>
<p class="byline">Théo Roussard · NEAR Hackathon, Investment Thesis track · Data as of <time datetime="{e(metrics["as_of"])}">{fmt_day(metrics["as_of"])}</time> · Not financial advice</p>
<section class="abstract">
<p><span class="runin">Abstract.</span> <span class="bottom-line">{e(n.bottom_line(metrics, v))}</span></p>
<div class="readings">{readings}</div>
<p class="note">{e(v["like_for_like_short"])} A ratio below one means NEAR is valued below its typical peer.{k_text}</p>
<p class="verdicts"><span class="runin">Verdicts.</span> {verdicts}.</p>
</section>
</header>"""


def key_points(metrics, v):
    bodies = [
        n.like_for_like(metrics, v),
        " ".join(x for x in (v["c1_claim"], n.c1_margin(metrics, v), n.post_break(metrics)) if x),
        " ".join((v["c2_claim"], n.bucket_sentence(metrics), v["c3_claim"])),
        " ".join((v["c4_claim"], holders_note(metrics))),
        " ".join((n.variants_sentence(metrics), rank_note(metrics))),
    ]
    items = "".join(f'<li><h3>{e(title)}</h3><p>{e(body)} '
                    f'<a class="more" href="#{anchor}">See the evidence</a></p></li>'
                    for (title, anchor), body in zip(KEY_POINT_TITLES, bodies))
    return (f'<section class="explainer" id="key-points">\n<h2>Key findings</h2>\n'
            f'<p class="intro">Five questions a skeptical investor would ask, each answered from '
            f'the data and linked to its evidence.</p>\n<ol class="points">{items}</ol>\n'
            f'</section>')


def how_it_works():
    steps = "".join(f"<li><h3>{e(title)}</h3><p>{e(text)}</p></li>" for title, text in HOW_STEPS)
    terms = "".join(f"<dt>{e(term)}</dt><dd>{e(text)}</dd>" for term, text in GLOSSARY)
    return (f'<section class="explainer" id="how">\n<h2>Method</h2>\n'
            f'<ol class="steps">{steps}</ol>\n<h3>Terms</h3>\n'
            f'<dl class="glossary">{terms}</dl>\n</section>')


def toc():
    links = [("key-points", "Key findings"), ("how", "Method"), ("evidence", "Evidence"),
             ("scorecard", "Scorecard"), ("multiples", "Multiples"), ("perimeters", "Perimeters"),
             ("variants", "Panel"), ("intents", "Intents revenue"), ("buybacks", "Buybacks"),
             ("float", "Dilution")]
    return ('<nav class="contents" aria-label="Contents"><span class="runin">Contents.</span> '
            + " · ".join(f'<a href="#{a}">{e(t)}</a>' for a, t in links) + "</nav>")


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
:root{color-scheme:light;--bg:#fbfaf7;--ink:#1b1b19;--ink-2:#4f4d48;--muted:#6b6962;
--rule:#dcd8ce;--accent:#1f5fae;--peer:#8c897f;--gross:#c9c5ba;--ref:#c4501f;
--holds:#2f7d32;--fires:#b3261e;--pending:#8a6d1f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;
--bg:#161615;--ink:#ecebe6;--ink-2:#bdbbb3;--muted:#9a978f;--rule:#34332f;--accent:#4a8ad6;
--peer:#7a776f;--gross:#46443f;--ref:#d4683a;--holds:#5fae63;--fires:#e0675e;--pending:#d4b45a}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#161615;--ink:#ecebe6;--ink-2:#bdbbb3;
--muted:#9a978f;--rule:#34332f;--accent:#4a8ad6;--peer:#7a776f;--gross:#46443f;--ref:#d4683a;
--holds:#5fae63;--fires:#e0675e;--pending:#d4b45a}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:17px;line-height:1.62;
font-family:"Iowan Old Style","Charter","Bitstream Charter","Sitka Text",Cambria,Georgia,serif;
font-variant-numeric:lining-nums;counter-reset:section figure}
main{max-width:44rem;margin:0 auto;padding:64px 20px 88px}
::selection{background:var(--accent);color:var(--bg)}
a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:.18em}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
p{margin:0 0 .9em}
h1{font-size:2.7rem;line-height:1.08;font-weight:600;letter-spacing:-.015em;margin:0 0 .35em;
text-wrap:balance}
.subtitle{font-size:1.22rem;line-height:1.45;font-style:italic;color:var(--ink-2);margin:0 0 1.1em;
text-wrap:balance}
.byline,.runin,.fig-label,.method strong,.source strong,th{font-variant-caps:all-small-caps;
letter-spacing:.045em}
.byline{color:var(--muted);font-size:1.02rem;margin:0 0 2.4em}
.runin{font-weight:700;margin-right:.25em}
.abstract{border-top:1px solid var(--ink);padding-top:1.3em}
.bottom-line{font-size:1.08rem}
.note{font-size:.9rem;color:var(--ink-2);line-height:1.55}
.frame-note{color:var(--muted);border-bottom:1px solid var(--rule);padding-bottom:1.4em;
margin-bottom:1.1em}
.contents{font-size:.92rem;line-height:1.9;color:var(--muted)}
.contents a{white-space:nowrap}
h2{font-size:1.5rem;line-height:1.25;font-weight:600;margin:2.8em 0 .7em;
counter-increment:section}
h2::before{content:counter(section) ".";margin-right:.5em;color:var(--muted);font-weight:400}
h3{font-size:1.14rem;line-height:1.3;font-weight:600;margin:2.4em 0 .5em}
.intro{color:var(--ink-2)}
ol.points,ol.steps{margin:0;padding-left:1.7em}
ol.points>li,ol.steps>li{margin:0 0 1.2em;padding-left:.25em}
ol.points>li::marker,ol.steps>li::marker{color:var(--muted);font-weight:600}
li>h3{font-size:1.05rem;margin:0 0 .2em}
li>p{margin:0}
.more{white-space:nowrap;font-size:.92rem}
dl.glossary{margin:.4em 0 0}
dl.glossary dt{font-weight:600;margin-top:.7em}
dl.glossary dd{margin:0;color:var(--ink-2)}
section.chart{margin:0}
figure{margin:0;counter-increment:figure}
figcaption{margin:0 0 .7em;line-height:1.55}
.fig-label{font-weight:700}
.fig-label::after{content:" " counter(figure) "."}
.method,.source,.legend{font-size:.84rem;line-height:1.5;color:var(--muted);margin:.45em 0}
.method strong,.source strong{color:var(--ink-2);font-weight:700}
.legend{margin-top:.2em}
.plot{overflow-x:auto;margin:.3em 0}
svg{width:100%;min-width:560px;height:auto;display:block}
svg text{fill:var(--ink);font-family:inherit;font-size:12.5px;font-variant-numeric:tabular-nums}
svg .axis{fill:var(--muted);font-size:11.5px}
.bar.near{fill:var(--accent)}
.bar.upper{fill:none;stroke:var(--accent);stroke-width:1.25}
.bar.peer{fill:var(--peer)}
.bar.gross{fill:var(--gross);stroke:var(--peer);stroke-width:1}
.label.near,.label.upper{font-weight:700}
.grid{stroke:var(--rule);stroke-width:1}
.median,.threshold{stroke:var(--ref);stroke-width:1.5;stroke-dasharray:4 3}
.key{display:inline-block;width:10px;height:10px;margin:0 .4em 0 1.1em;vertical-align:-.05em}
.key:first-child{margin-left:0}
.key.near{background:var(--accent)}.key.upper{border:1.25px solid var(--accent)}
.key.peer{background:var(--peer)}.key.gross{background:var(--gross);border:1px solid var(--peer)}
.key.median{width:14px;height:0;border-top:1.5px dashed var(--ref);vertical-align:.3em}
.table{overflow-x:auto;margin:.6em 0 .8em}
table{border-collapse:collapse;width:100%;font-size:.86rem;line-height:1.45;
font-variant-numeric:tabular-nums lining-nums;border-top:1px solid var(--ink);
border-bottom:1px solid var(--ink)}
th{text-align:left;font-weight:700;color:var(--ink-2);padding:.55em .7em .4em;
border-bottom:1px solid var(--rule);vertical-align:bottom}
td{padding:.45em .7em;vertical-align:top}
th:first-child,td:first-child{padding-left:0}
th:last-child,td:last-child{padding-right:0}
.table.wide{width:min(62rem,calc(100vw - 40px));
margin-left:calc((100% - min(62rem,calc(100vw - 40px))) / 2)}
.table.wide td:first-child{min-width:17rem}
.readings th:not(:first-child),.readings td:not(:first-child){text-align:right}
code{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.76rem;
color:var(--ink-2)}
.verdict{font-variant-caps:all-small-caps;letter-spacing:.05em;font-weight:700;white-space:nowrap}
.verdict::before{content:"";display:inline-block;width:.5em;height:.5em;margin-right:.3em;
background:currentColor;vertical-align:.08em}
.verdict.holds{color:var(--holds)}.verdict.fires{color:var(--fires)}
.verdict.pending{color:var(--pending)}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:.35em 1.4em;margin:.4em 0;
padding:.7em 0;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);font-size:.95rem;
font-variant-numeric:tabular-nums}
dl.facts dt{color:var(--ink-2)}dl.facts dd{margin:0;overflow-wrap:anywhere}
.empty{color:var(--muted);font-style:italic}
footer{margin-top:4em;padding-top:1.1em;border-top:1px solid var(--rule);font-size:.84rem;
line-height:1.55;color:var(--muted)}
[id]{scroll-margin-top:16px}
@media (max-width:560px){body{font-size:16px}main{padding:36px 16px 64px}
h1{font-size:2.05rem}.subtitle{font-size:1.08rem}
dl.facts{grid-template-columns:1fr;gap:0}dl.facts dd{margin-bottom:.45em}}
@media print{body{background:#fff;color:#000}main{max-width:none;padding:0}
.plot{overflow:visible}svg{min-width:0}section.chart{break-inside:avoid}}
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
        section("intents", "NEAR Intents revenue, and the share NEAR keeps", intents_chart(metrics)
                + table(["Window", "Dates", "Net revenue", "Gross fees", "Net / gross"],
                        c2_windows),
                intents_sources(metrics),
                f"Whole windows ending on {fmt_day(as_of)}, none before "
                f"{fmt_day(metrics['intents']['regime_break'])}: revenue is booked daily only "
                f"since then, so earlier data is not comparable. C2 compares the last window's "
                f"net revenue with the prior one's; C3 compares their net / gross shares, the "
                f"part of Intents fees NEAR keeps.",
                intents_takeaway(metrics) + " " + capture_takeaway(metrics)),
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
{abstract(metrics, v)}
<p class="note frame-note">The falsification thresholds (k, x, y, z) were frozen after these numbers were visible; the rationale for each one sits next to it in {link(CONFIG_URL, 'config/panel.toml')}. Trailing window: {days} days. The full text is {link(THESIS_URL, 'THESIS.md')}; the code and data are on {link(REPO, 'GitHub')}. Data from <a href="https://defillama.com">DefiLlama</a>. Powered by <a href="https://www.coingecko.com">CoinGecko</a>.</p>
{toc()}
{key_points(metrics, v)}
{how_it_works()}
<section class="evidence" id="evidence">
<h2>Evidence</h2>
<p class="intro">Each figure states what it shows in its caption, then the chart or table, the method and the source.</p>
{chr(10).join(sections)}
</section>
<footer>
<p><span class="runin">Data and credits.</span> Fees and revenue: <a href="https://defillama.com">DefiLlama</a>. Market caps and prices: Powered by <a href="https://www.coingecko.com">CoinGecko</a>. Buyback account: nearblocks. The data belongs to its providers and is not covered by the code license (see <a href="https://github.com/TheodoreRoussard/NEAR-to-its-peers/blob/main/data/README.md">data/README.md</a>). Rebuild everything offline with <code>make judge-demo</code>. Code under the MIT license. Not financial advice.</p>
</footer>
</main>
</body>
</html>
"""


def write(metrics, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(metrics))
