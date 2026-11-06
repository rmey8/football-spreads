"""Player-prop value finder.

Every book's over/under price on a player implies a *projection*: if a book
hangs 64.5 receiving yards with the Over at -130 (no-vig 55%), the stat is
modelled as Normal(mu, sd) and solved for the mu that gives a 55% chance of
going over 64.5. That puts all books on one scale (projected yards), even
when they post different lines.

    fair projection = median of the sharp books (Pinnacle) when they post the prop,
                      otherwise the median of all books (the market consensus)
    edge            = P(win at a book's line | fair projection) vs that book's price

A typical prop edge is a book that is slow to move or hangs an off-market line,
e.g. 58.5 while everyone else is at 64.5.

Yes/No props (anytime TD) are compared directly on no-vig probability. When a
book only offers "Yes", an assumed margin (ONE_SIDED_VIG) is removed instead.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import NormalDist, median

from . import config as C
from .odds_math import expected_value, implied_prob, no_vig

STD = NormalDist()
SIDE_A = {"Over", "Yes"}
SIDE_B = {"Under", "No"}


@dataclass
class PropQuote:
    book: str
    fetched_at: str
    line: float | None
    price_a: float              # Over / Yes
    price_b: float | None       # Under / No (None if the book only offers one side)


@dataclass
class PropPlay:
    sport: str
    event_id: str
    commence_time: str
    home: str
    away: str
    market: str
    player: str
    side: str                   # Over / Under / Yes / No
    line: float | None
    best_book: str
    best_price: float
    fair_prob: float
    ev: float
    projection: float | None    # fair projected stat (None for yes/no markets)
    n_books: int
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def matchup(self) -> str:
        return f"{self.away} @ {self.home}"

    @property
    def label(self) -> str:
        name = C.PROP_MARKETS.get(self.market, self.market)
        if self.line is None:
            return f"{self.player} {name}: {self.side}"
        return f"{self.player} {self.side} {self.line:g} {name}"


# --------------------------------------------------------------------------- #
def build_prop_markets(rows: list[dict]) -> dict:
    """{(sport, event, market, player): {"meta": ..., "books": {book: [PropQuote]}}}"""
    partial = defaultdict(dict)
    meta = {}
    for r in rows:
        key = (r["sport"], r["event_id"], r["market"], r["player"])
        meta[key] = {k: r[k] for k in ("sport", "event_id", "commence_time", "home", "away")}
        side = "a" if r["outcome"] in SIDE_A else "b" if r["outcome"] in SIDE_B else None
        if side:
            # some books list several lines (alts); keep the one closest to even money
            slot = partial[key + (r["book"], r["fetched_at"])]
            slot.setdefault(side, []).append((r["price"], r["point"]))

    out = {}
    for (sport, ev, mkt, player, book, ts), sides in partial.items():
        if "a" not in sides:
            continue
        quote = _main_line(mkt, sides)
        if quote is None:
            continue
        line, pa, pb = quote
        key = (sport, ev, mkt, player)
        entry = out.setdefault(key, {"meta": meta[key], "books": defaultdict(list)})
        entry["books"][book].append(PropQuote(book, ts, line, pa, pb))
    for entry in out.values():
        for qs in entry["books"].values():
            qs.sort(key=lambda q: q.fetched_at)
    return out


def _main_line(market, sides):
    yes_no = market in C.YES_NO_MARKETS
    unders = {pt: p for p, pt in sides.get("b", [])}
    best = None
    for pa, pt in sides["a"]:
        if not yes_no and pt is None:
            continue
        pb = unders.get(pt)
        if not yes_no and pb is None and unders:
            continue
        balance = abs(implied_prob(pa) - 0.5)
        if best is None or balance < best[0]:
            best = (balance, (None if yes_no else pt, pa, pb))
    return best[1] if best else None


# --------------------------------------------------------------------------- #
def _p_a(q: PropQuote) -> float:
    """No-vig probability of Over/Yes at this book."""
    if q.price_b is not None:
        return no_vig(q.price_a, q.price_b)[0]
    return min(0.98, implied_prob(q.price_a) / (1 + C.ONE_SIDED_VIG))


def prop_sd(sport: str, market: str) -> float:
    sd = C.PROP_SD[market]
    return sd * C.CFB_SD_MULTIPLIER if sport == "cfb" else sd


def implied_projection(q: PropQuote, sd: float) -> float:
    p = min(0.98, max(0.02, _p_a(q)))
    return q.line + sd * STD.inv_cdf(p)


def p_over(line: float, mu: float, sd: float) -> float:
    return 1 - STD.cdf((line - mu) / sd)


def analyze_prop(meta: dict, market: str, player: str,
                 books: dict[str, list[PropQuote]]) -> PropPlay | None:
    sport = meta["sport"]
    yes_no = market in C.YES_NO_MARKETS
    if not yes_no and market not in C.PROP_SD:
        return None
    sd = None if yes_no else prop_sd(sport, market)
    current = {b: qs[-1] for b, qs in books.items()}
    if len(current) < C.PROP_MIN_BOOKS:
        return None

    # A "view" is a projection (line markets) or a Yes probability (yes/no markets)
    def view(q):
        return _p_a(q) if yes_no else implied_projection(q, sd)

    def prob_a(v, line):  # P(Over/Yes) at `line` given view v
        return v if yes_no else p_over(line, v, sd)

    sharp = [b for b in current if b in C.SHARP_PROP_BOOKS]
    others = [b for b in current if b not in C.SHARP_PROP_BOOKS]
    fair_src = sharp or list(current)
    fair = median(view(current[b]) for b in fair_src)

    # Best +EV price on either side
    best = None
    for b, q in current.items():
        pa = prob_a(fair, q.line)
        for side, p, price in (("a", pa, q.price_a), ("b", 1 - pa, q.price_b)):
            if price is None:
                continue
            ev = expected_value(p, price)
            if best is None or ev > best[0]:
                best = (ev, side, b, q, p)
    ev, side, best_book, bq, p_win = best
    sign = 1 if side == "a" else -1
    side_name = ("Yes" if side == "a" else "No") if yes_no else ("Over" if side == "a" else "Under")

    reasons, score = [], ev * 100
    unit = "" if yes_no else f" {C.PROP_MARKETS[market].split()[-1].lower()}"
    src = "Sharp (Pinnacle)" if sharp else f"{len(current)}-book consensus"
    if yes_no:
        reasons.append(f"{src} fair Yes probability {fair:.1%}; {best_book} "
                       f"{bq.price_a if side == 'a' else bq.price_b:+.0f} is {ev * 100:+.1f}% EV")
    else:
        reasons.append(f"{src} projection {fair:.1f}{unit} vs {best_book} line {bq.line:g} "
                       f"({side_name} {p_win:.1%}, {ev * 100:+.1f}% EV)")
        lines = sorted({q.line for q in current.values()})
        if len(lines) > 1:
            reasons.append(f"Line shopping: books range {lines[0]:g} to {lines[-1]:g}")

    # Movement of the fair source since the first snapshot
    opens = [view(books[b][0]) for b in fair_src if len(books[b]) >= 2]
    if opens:
        prev = median(opens)
        mv_pp = (prob_a(fair, bq.line) - prob_a(prev, bq.line)) * 100 * sign
        if abs(mv_pp) >= 1:
            delta = (f"{(fair - prev) * 100:+.1f}pp" if yes_no else f"{fair - prev:+.1f}{unit}")
            reasons.append(f"Market moved {delta} since first snapshot "
                           f"({'toward' if mv_pp > 0 else 'against'} {side_name})")
        score += C.PROP_MOVE_WEIGHT * mv_pp

    # Sharp vs rec disagreement
    if sharp and others:
        rec_view = median(view(current[b]) for b in others)
        div_pp = (prob_a(fair, bq.line) - prob_a(rec_view, bq.line)) * 100 * sign
        if abs(div_pp) >= 1:
            what = (f"{rec_view:.1%}" if yes_no else f"{rec_view:.1f}{unit}")
            reasons.append(f"Rec books have it at {what}; Pinnacle "
                           f"{'agrees with' if div_pp > 0 else 'leans against'} {side_name}")
        score += C.PROP_DIVERGENCE_WEIGHT * div_pp

    return PropPlay(
        sport=sport, event_id=meta["event_id"], commence_time=meta["commence_time"],
        home=meta["home"], away=meta["away"], market=market, player=player,
        side=side_name, line=bq.line, best_book=best_book,
        best_price=bq.price_a if side == "a" else bq.price_b,
        fair_prob=p_win, ev=ev, projection=None if yes_no else fair,
        n_books=len(current), score=score, reasons=reasons,
    )


def find_prop_plays(rows: list[dict], min_ev: float = C.PROP_MIN_EV,
                    top: int | None = None) -> list[PropPlay]:
    plays = []
    for (_, _, market, player), entry in build_prop_markets(rows).items():
        play = analyze_prop(entry["meta"], market, player, entry["books"])
        if play and play.ev >= min_ev:
            plays.append(play)
    plays.sort(key=lambda p: p.score, reverse=True)
    return plays[:top] if top else plays
