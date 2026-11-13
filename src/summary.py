"""summary.txt: the X post, its reply and the submission-form text, from metrics.json.

The project rule is that every number in the X post and the form text comes from the
data, so these texts are generated like THESIS.md and the dashboard, and their claims
follow the verdicts. Never reads the wall clock.
"""
from pathlib import Path

from src import narrative as n
from src.fmt import fmt_day, fmt_multiple, fmt_ratio, listing

REPO_URL = "https://github.com/TheodoreRoussard/NEAR-to-its-peers"
DASHBOARD_URL = "https://theodoreroussard.github.io/NEAR-to-its-peers/"


def _readings(m):
    near = m["near_perimeters"]
    return (fmt_ratio(near["BASE+NET"]["ratio_to_peer_median"]),
            fmt_ratio(near["BASE"]["ratio_to_peer_median"]))


def _holders_line(m):
    c4 = m["falsification"]["c4"]
    if c4["verdict"] == "fires" and c4["policy"] == "none published":
        return "Holders do not provably capture it yet."
    if c4["verdict"] == "holds":
        return "Its buybacks are provably held for holders."
    return "Whether holders capture it is still open."


def x_post(m):
    with_intents, like_for_like = _readings(m)
    return "\n\n".join([
        "Is NEAR expensive vs its peers, per dollar of fees?",
        f"Counting Intents revenue: {with_intents}x the peer median. Base-layer fees only: "
        f"{like_for_like}x. {_holders_line(m)}",
        f"Built at NEAR HACKATHON @NEARProtocol #NEARHackathon\n{DASHBOARD_URL}",
        "Not financial advice.",
    ])


def x_reply(m):
    peers = [name for name in m["chains"] if name != "NEAR"]
    return (f"Code, data and THESIS.md, rebuilt offline with one command: {REPO_URL}\n\n"
            f"The peers are {listing(peers)}. Which chain or fee definition would you add "
            f"to test it?")


def form_text(m):
    v = n.basics(m)
    near = m["near_perimeters"]
    verdicts = n.verdict_summary(m["falsification"])
    return " ".join([
        "NEAR Against Its Peers is a reproducible investment thesis on NEAR.",
        f"It compares NEAR's market cap per dollar of on-chain fees with "
        f"{len(m['chains']) - 1} peer chains, decides which NEAR Intents revenue can fairly "
        f"count for NEAR, and states explicit tripwires that would prove it wrong, with "
        f"thresholds frozen in a tagged commit.",
        n.bottom_line(m, v),
        f"Multiples: {fmt_multiple(near['BASE+NET']['multiple'])} counting Intents revenue, "
        f"{fmt_multiple(near['BASE']['multiple'])} on base-layer fees, against a peer median "
        f"of {fmt_multiple(m['peer_median_multiple'])}.",
        f"Falsification verdicts: {verdicts}",
        f"A Python standard-library pipeline turns a committed DefiLlama and CoinGecko "
        f"snapshot (as of {fmt_day(m['as_of'])}) into metrics.json, THESIS.md and a static "
        f"dashboard; make judge-demo rebuilds everything offline and runs the tests, and "
        f"every number and verdict in the text is generated from the data.",
        f"Dashboard: {DASHBOARD_URL} Repository: {REPO_URL}",
        "Not financial advice.",
    ])


def render_summary(m):
    return "\n".join([
        f"Summary generated from data/processed/metrics.json (data as of {m['as_of']}).",
        "Copy these texts as they are: every number in them comes from the data.",
        "",
        "=== X post ===",
        x_post(m),
        "",
        "=== X reply (thread) ===",
        x_reply(m),
        "",
        "=== Submission form: What did you build? ===",
        form_text(m),
        "",
    ])


def write(metrics, path):
    Path(path).write_text(render_summary(metrics))
