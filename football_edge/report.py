"""Render sharp plays to the terminal, Markdown and CSV."""
import csv
from datetime import datetime
from pathlib import Path

from .signals import Play

SPORT_NAME = {"nfl": "NFL", "cfb": "CFB"}
MARKET_NAME = {"spreads": "Spread", "totals": "Total", "h2h": "Moneyline"}


def _kick(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%a %m/%d %H:%MZ")
    except ValueError:
        return ts


def _price(play: Play) -> str:
    return f"{play.best_price:+.0f} @ {play.best_book}" if play.best_price is not None else "-"


def to_text(plays: list[Play], title: str) -> str:
    out = [title, "=" * len(title)]
    if not plays:
        out.append("No sharp signals above the threshold.")
    for i, p in enumerate(plays, 1):
        out.append(f"\n#{i} [{p.tier} {p.score:.1f}] {SPORT_NAME[p.sport]} {MARKET_NAME[p.market]}: "
                   f"{p.label}   ({p.matchup}, {_kick(p.commence_time)})")
        out.append(f"    Best price: {_price(p)}   fair win prob {p.fair_prob:.1%}   EV {p.ev * 100:+.1f}%")
        out.extend(f"    - {r}" for r in p.reasons)
    return "\n".join(out)


def to_markdown(plays: list[Play], title: str) -> str:
    lines = [f"# {title}", "",
             "| # | Tier | Score | League | Market | Play | Matchup | Kickoff | Best price | EV | Why |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(plays, 1):
        why = "<br>".join(r.replace("|", "/") for r in p.reasons)
        lines.append(f"| {i} | {p.tier} | {p.score:.1f} | {SPORT_NAME[p.sport]} | {MARKET_NAME[p.market]} "
                     f"| **{p.label}** | {p.matchup} | {_kick(p.commence_time)} | {_price(p)} "
                     f"| {p.ev * 100:+.1f}% | {why} |")
    return "\n".join(lines) + "\n"


def write_csv(plays: list[Play], path: Path) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "tier", "score", "sport", "market", "play", "home", "away",
                    "kickoff", "best_book", "best_price", "best_line", "fair_prob", "ev", "reasons"])
        for i, p in enumerate(plays, 1):
            w.writerow([i, p.tier, round(p.score, 2), p.sport, p.market, p.label, p.home, p.away,
                        p.commence_time, p.best_book, p.best_price, p.best_line,
                        round(p.fair_prob, 4), round(p.ev, 4), " | ".join(p.reasons)])


# --------------------------------------------------------------------------- #
# Player props
# --------------------------------------------------------------------------- #
def props_to_text(plays, title: str) -> str:
    out = [title, "=" * len(title)]
    if not plays:
        out.append("No props above the EV threshold.")
    for i, p in enumerate(plays, 1):
        out.append(f"\n#{i} [{p.score:.1f}] {SPORT_NAME[p.sport]} {p.label}   "
                   f"({p.matchup}, {_kick(p.commence_time)})")
        out.append(f"    Bet: {p.best_price:+.0f} @ {p.best_book}   win prob {p.fair_prob:.1%}   "
                   f"EV {p.ev * 100:+.1f}%   ({p.n_books} books)")
        out.extend(f"    - {r}" for r in p.reasons)
    return "\n".join(out)


def props_to_markdown(plays, title: str) -> str:
    lines = [f"# {title}", "",
             "| # | Score | League | Prop | Matchup | Kickoff | Bet at | Win prob | EV | Why |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(plays, 1):
        why = "<br>".join(r.replace("|", "/") for r in p.reasons)
        lines.append(f"| {i} | {p.score:.1f} | {SPORT_NAME[p.sport]} | **{p.label}** | {p.matchup} "
                     f"| {_kick(p.commence_time)} | {p.best_price:+.0f} @ {p.best_book} "
                     f"| {p.fair_prob:.1%} | {p.ev * 100:+.1f}% | {why} |")
    return "\n".join(lines) + "\n"


def write_props_csv(plays, path: Path) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "score", "sport", "market", "player", "side", "line", "home", "away",
                    "kickoff", "best_book", "best_price", "fair_prob", "ev", "projection",
                    "n_books", "reasons"])
        for i, p in enumerate(plays, 1):
            w.writerow([i, round(p.score, 2), p.sport, p.market, p.player, p.side, p.line,
                        p.home, p.away, p.commence_time, p.best_book, p.best_price,
                        round(p.fair_prob, 4), round(p.ev, 4),
                        None if p.projection is None else round(p.projection, 1),
                        p.n_books, " | ".join(p.reasons)])
