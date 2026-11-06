"""Optional public betting splits (% of bets vs % of money).

No free API provides these, but several sites publish them (e.g. DraftKings'
public betting-splits page, Action Network, VSIN). Copy them into a CSV:

    sport,home,away,market,side,bets_pct,money_pct
    nfl,Kansas City Chiefs,Buffalo Bills,spreads,home,38,61
    nfl,Kansas City Chiefs,Buffalo Bills,totals,over,72,55

`side` is home/away for spreads and h2h, over/under for totals. One side per
market is enough; the other side is inferred as 100 - x.
"""
import csv
from pathlib import Path

SIDE_A = {"home": True, "over": True, "away": False, "under": False}


def _key(sport, home, away, market):
    return (sport.strip().lower(), home.strip().lower(), away.strip().lower(),
            market.strip().lower())


def load_splits(path: Path) -> dict:
    """Return {(sport, home, away, market): (bets_pct_a, money_pct_a)}."""
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            side = row["side"].strip().lower()
            if side not in SIDE_A:
                raise ValueError(f"unknown side {side!r} in {path}")
            bets, money = float(row["bets_pct"]), float(row["money_pct"])
            if not SIDE_A[side]:
                bets, money = 100 - bets, 100 - money
            out[_key(row["sport"], row["home"], row["away"], row["market"])] = (bets, money)
    return out


def lookup(splits: dict | None, sport, home, away, market):
    if not splits:
        return None
    return splits.get(_key(sport, home, away, market))
