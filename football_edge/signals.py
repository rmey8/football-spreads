"""Sharp-money detection.

Every market is viewed from "side A" (home for spreads/moneyline, Over for
totals). For each book quote we compute the *strength* of side A: its no-vig
win probability, adjusted to a common reference line so that -3 -110 and
-3.5 +100 can be compared. Signals are then differences in strength:

1. Sharp vs rec divergence  - sharp books rate a side higher than retail books.
2. Sharp-book movement      - opening -> current move at the sharp books.
3. Steam                    - several books jump the same way in one snapshot.
4. Money vs bets split      - % of money well above % of tickets (needs splits CSV).
5. Reverse line movement    - line moves toward the side the public is NOT on.
6. +EV vs the sharp line    - a book still offering a price better than fair.

The combined score is roughly "percentage points of edge the sharp market sees".
"""
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

from . import config as C
from .odds_math import expected_value, no_vig
from .splits import lookup


@dataclass
class Quote:
    book: str
    fetched_at: str
    line: float | None
    price_a: float
    price_b: float


@dataclass
class Play:
    sport: str
    event_id: str
    commence_time: str
    home: str
    away: str
    market: str
    side: str            # "a" or "b"
    label: str           # e.g. "Buffalo Bills +3.5", "Over 47.5"
    score: float
    fair_prob: float     # sharp-market no-vig probability at the best line
    best_book: str | None
    best_price: float | None
    best_line: float | None
    ev: float | None
    reasons: list[str] = field(default_factory=list)

    @property
    def matchup(self) -> str:
        return f"{self.away} @ {self.home}"

    @property
    def tier(self) -> str:
        if self.score >= 5:
            return "STRONG"
        if self.score >= 3:
            return "MODERATE"
        return "LEAN"


# --------------------------------------------------------------------------- #
# Building quotes from snapshot rows
# --------------------------------------------------------------------------- #
def build_markets(rows: list[dict]) -> dict:
    """Group rows into {(sport, event_id, market): {"meta": ..., "books": {book: [Quote]}}}."""
    partial = defaultdict(dict)  # (sport, event, market, book, fetched_at) -> {"a":(p,pt), "b":...}
    meta = {}
    for r in rows:
        key = (r["sport"], r["event_id"], r["market"])
        meta[key] = {k: r[k] for k in ("sport", "event_id", "commence_time", "home", "away")}
        side = _side_of(r)
        if side:
            partial[key + (r["book"], r["fetched_at"])][side] = (r["price"], r["point"])

    markets = {}
    for (sport, ev, mkt, book, ts), sides in partial.items():
        if "a" not in sides or "b" not in sides:
            continue
        (pa, pt_a), (pb, _) = sides["a"], sides["b"]
        line = None if mkt == "h2h" else pt_a
        if mkt != "h2h" and line is None:
            continue
        key = (sport, ev, mkt)
        entry = markets.setdefault(key, {"meta": meta[key], "books": defaultdict(list)})
        entry["books"][book].append(Quote(book, ts, line, pa, pb))
    for entry in markets.values():
        for quotes in entry["books"].values():
            quotes.sort(key=lambda q: q.fetched_at)
    return markets


def _side_of(row) -> str | None:
    o = row["outcome"]
    if row["market"] == "totals":
        return {"Over": "a", "Under": "b"}.get(o)
    if o == row["home"]:
        return "a"
    if o == row["away"]:
        return "b"
    return None


# --------------------------------------------------------------------------- #
# Strength math
# --------------------------------------------------------------------------- #
def hardness(market: str, line: float | None, ref: float | None) -> float:
    """How many points harder side A's line is than the reference line."""
    if market == "h2h" or line is None or ref is None:
        return 0.0
    # spreads: home -4 is harder than ref -3; totals: Over 48 is harder than ref 47
    h = (ref - line) if market == "spreads" else (line - ref)
    return max(-C.MAX_LINE_ADJUST, min(C.MAX_LINE_ADJUST, h))


def strength(q: Quote, market: str, ref: float | None, slope: float) -> float:
    """Implied no-vig probability of side A, translated to the reference line."""
    p_a, _ = no_vig(q.price_a, q.price_b)
    return p_a + slope * hardness(market, q.line, ref)


# --------------------------------------------------------------------------- #
# Market analysis
# --------------------------------------------------------------------------- #
def analyze_market(meta: dict, market: str, books: dict[str, list[Quote]],
                   splits: dict | None = None) -> Play | None:
    sport, home, away = meta["sport"], meta["home"], meta["away"]
    slope = C.POINT_SLOPE.get((sport, market), 0.0)
    side_name = {
        "spreads": (home, away), "h2h": (home, away), "totals": ("Over", "Under"),
    }[market]

    def toward(x):  # name of the side a positive/negative number favours
        return side_name[0] if x > 0 else side_name[1]

    current = {b: qs[-1] for b, qs in books.items()}
    sharp = [b for b in current if b in C.SHARP_BOOKS]
    rec = [b for b in current if b in C.REC_BOOKS]
    lines_src = sharp or list(current)
    ref = None if market == "h2h" else median(current[b].line for b in lines_src)

    s_cur = {b: strength(q, market, ref, slope) for b, q in current.items()}
    fair_a = median(s_cur[b] for b in lines_src)

    score = 0.0
    reasons: list[str] = []
    if not sharp:
        reasons.append("No sharp book in feed - using all-book consensus as fair line")

    # 1. Sharp vs rec divergence
    if sharp and rec:
        div = (median(s_cur[b] for b in sharp) - median(s_cur[b] for b in rec)) * 100
        score += div
        if abs(div) >= C.DIVERGENCE_MIN_PP:
            reasons.append(
                f"Sharp books rate {toward(div)} {abs(div):.1f}pp higher than rec books"
                + _line_note(market, current, sharp, rec))

    # 2. Sharp-book movement since open
    moves = []
    for b in sharp:
        qs = books[b]
        if len(qs) >= 2:
            moves.append((strength(qs[-1], market, ref, slope)
                          - strength(qs[0], market, ref, slope)) * 100)
    if moves:
        mv = median(moves)
        score += mv
        if abs(mv) >= C.MOVE_MIN_PP:
            reasons.append(f"Sharp books moved {abs(mv):.1f}pp toward {toward(mv)} since open"
                           + _move_note(market, books, sharp))

    # 3. Steam: many books jumping together in their latest update
    latest_ts = max(q.fetched_at for q in current.values())
    jumps = []
    for b, qs in books.items():
        if len(qs) >= 2 and qs[-1].fetched_at == latest_ts:
            d = strength(qs[-1], market, ref, slope) - strength(qs[-2], market, ref, slope)
            if abs(d) >= C.STEAM_MIN_SHIFT:
                jumps.append(d)
    for sign in (1, -1):
        same = [d for d in jumps if d * sign > 0]
        if len(same) >= C.STEAM_MIN_BOOKS:
            score += sign * C.STEAM_POINTS
            reasons.append(f"Steam: {len(same)} books moved toward "
                           f"{side_name[0] if sign > 0 else side_name[1]} in the last update")

    # 4/5. Public splits & reverse line movement
    sp = lookup(splits, sport, home, away, market)
    if sp:
        bets_a, money_a = sp
        gap = money_a - bets_a
        if abs(gap) >= C.SPLIT_GAP_MIN:
            score += gap / 10
            side = side_name[0] if gap > 0 else side_name[1]
            b_pct, m_pct = (bets_a, money_a) if gap > 0 else (100 - bets_a, 100 - money_a)
            reasons.append(f"Big-bet money: {side} has {b_pct:.0f}% of bets but {m_pct:.0f}% of money")
        all_moves = [(strength(qs[-1], market, ref, slope) - strength(qs[0], market, ref, slope)) * 100
                     for qs in books.values() if len(qs) >= 2]
        if all_moves:
            cons = median(all_moves)
            if bets_a <= C.RLM_PUBLIC_MAX and cons >= C.MOVE_MIN_PP:
                score += C.RLM_POINTS
                reasons.append(f"Reverse line movement: only {bets_a:.0f}% of bets on "
                               f"{side_name[0]} but the line moved toward it")
            elif 100 - bets_a <= C.RLM_PUBLIC_MAX and cons <= -C.MOVE_MIN_PP:
                score -= C.RLM_POINTS
                reasons.append(f"Reverse line movement: only {100 - bets_a:.0f}% of bets on "
                               f"{side_name[1]} but the line moved toward it")

    if score == 0:
        return None
    side = "a" if score > 0 else "b"

    # 6. Best available price for that side, judged against the sharp fair line
    best = None
    for b, q in current.items():
        p_a = fair_a - slope * hardness(market, q.line, ref)
        p = p_a if side == "a" else 1 - p_a
        price = q.price_a if side == "a" else q.price_b
        ev = expected_value(p, price)
        if best is None or ev > best[0]:
            best = (ev, b, q, p)
    ev, best_book, bq, p_side = best
    if ev > 0:
        score += (1 if side == "a" else -1) * ev * 100 * C.EV_WEIGHT
        reasons.append(f"Best price {_fmt_price(bq.price_a if side == 'a' else bq.price_b)} "
                       f"at {best_book} is {ev * 100:+.1f}% EV vs the sharp no-vig line")
    else:
        reasons.append(f"Value is gone: the market has caught up, best price is {ev * 100:+.1f}% EV "
                       f"vs the sharp line (follow only if you can beat it)")

    return Play(
        sport=sport, event_id=meta["event_id"], commence_time=meta["commence_time"],
        home=home, away=away, market=market, side=side,
        label=_label(market, side, home, away, bq.line),
        score=abs(score), fair_prob=p_side, best_book=best_book,
        best_price=bq.price_a if side == "a" else bq.price_b,
        best_line=bq.line, ev=ev, reasons=reasons,
    )


def find_sharp_plays(rows: list[dict], splits: dict | None = None,
                     min_score: float = C.DEFAULT_MIN_SCORE,
                     only_value: bool = False) -> list[Play]:
    plays = []
    for (_, _, market), entry in build_markets(rows).items():
        play = analyze_market(entry["meta"], market, entry["books"], splits)
        if play and play.score >= min_score and (not only_value or play.ev > 0):
            plays.append(play)
    return sorted(plays, key=lambda p: p.score, reverse=True)


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _fmt_price(p: float) -> str:
    return f"{p:+.0f}"


def _fmt_line(market, line):
    return f"{line:+g}" if market == "spreads" else f"{line:g}"


def _label(market, side, home, away, line):
    if market == "totals":
        return f"{'Over' if side == 'a' else 'Under'} {line:g}"
    team = home if side == "a" else away
    if market == "h2h":
        return f"{team} ML"
    return f"{team} {(line if side == 'a' else -line):+g}"


def _line_note(market, current, sharp, rec):
    if market == "h2h":
        return ""
    s = median(current[b].line for b in sharp)
    r = median(current[b].line for b in rec)
    return f" (sharp {_fmt_line(market, s)} vs rec {_fmt_line(market, r)})" if s != r else ""


def _move_note(market, books, sharp):
    if market == "h2h":
        b = sharp[0]
        return f" ({b} home ML: {_fmt_price(books[b][0].price_a)} -> {_fmt_price(books[b][-1].price_a)})"
    for b in sharp:
        o, c = books[b][0], books[b][-1]
        if o.line != c.line:
            return f" ({b}: {_fmt_line(market, o.line)} -> {_fmt_line(market, c.line)})"
    b = sharp[0]
    o, c = books[b][0], books[b][-1]
    return f" ({b}: juice {_fmt_price(o.price_a)} -> {_fmt_price(c.price_a)})"
