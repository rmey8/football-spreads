"""Generate SIMULATED odds snapshots so the pipeline can be tried without an API key.

Nothing here is real market data. Some games have a planted sharp move (sharp
books move first, rec books lag), one has a steam move, the rest are noise.
"""
import random
from datetime import datetime, timedelta, timezone
from statistics import NormalDist

from . import config as C
from .odds_math import prob_to_american

NFL_GAMES = [
    ("Kansas City Chiefs", "Buffalo Bills", -2.5, 47.5),
    ("Philadelphia Eagles", "Dallas Cowboys", -6.5, 45.5),
    ("Detroit Lions", "Green Bay Packers", -3.0, 49.5),
    ("San Francisco 49ers", "Seattle Seahawks", -4.5, 44.0),
    ("Baltimore Ravens", "Cincinnati Bengals", -3.5, 50.5),
    ("Houston Texans", "Jacksonville Jaguars", -5.5, 42.5),
]
CFB_GAMES = [
    ("Georgia Bulldogs", "Tennessee Volunteers", -9.5, 52.5),
    ("Ohio State Buckeyes", "Penn State Nittany Lions", -6.0, 46.5),
    ("Texas Longhorns", "Oklahoma Sooners", -7.5, 55.5),
    ("Oregon Ducks", "USC Trojans", -10.5, 61.5),
    ("Notre Dame Fighting Irish", "Navy Midshipmen", -17.5, 44.5),
    ("Utah Utes", "Kansas State Wildcats", 1.5, 48.0),
]

SHARP = ["pinnacle", "circasports", "lowvig"]
REC = ["draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet"]
SNAPSHOT_HOURS_AGO = [36, 24, 12, 2]


def _price_pair(p_a: float, vig: float) -> tuple[int, int]:
    p_a = min(max(p_a, 0.03), 0.97)
    return prob_to_american(p_a * (1 + vig)), prob_to_american((1 - p_a) * (1 + vig))


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def generate(seed: int = 7) -> tuple[list[dict], list[dict]]:
    """Return (snapshot rows, splits rows)."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    rows, splits = [], []
    for sport, games, sd in (("nfl", NFL_GAMES, 13.5), ("cfb", CFB_GAMES, 15.5)):
        for gi, (home, away, spread, total) in enumerate(games):
            event_id = f"demo-{sport}-{gi}"
            kickoff = (now + timedelta(days=1 + gi % 3, hours=17)).isoformat()
            # planted scenarios: (spread shift toward home in pts, total shift toward over, steam?)
            scenario = rng.choice(["sharp_home", "sharp_away", "sharp_over", "sharp_under",
                                   "steam", "quiet", "quiet"])
            d_spread = {"sharp_home": -1.5, "sharp_away": 1.5, "steam": -1.0}.get(scenario, 0.0)
            d_total = {"sharp_over": 2.0, "sharp_under": -2.0}.get(scenario, 0.0)
            noise = {b: (rng.uniform(-0.25, 0.25), rng.uniform(-0.3, 0.3)) for b in SHARP + REC}
            lagging = set(rng.sample(REC, 3))

            for k, hrs in enumerate(SNAPSHOT_HOURS_AGO):
                ts = (now - timedelta(hours=hrs)).isoformat()
                for book in SHARP + REC:
                    is_sharp = book in SHARP
                    if scenario == "steam":
                        f = 1.0 if k == 3 else 0.0
                    elif is_sharp:
                        f = min(1.0, k / 2)
                    else:
                        f = max(0.0, (k - 1) / 2) * (0.3 if book in lagging else 1.0)
                    vig = 0.025 if is_sharp else 0.045
                    view_spread = spread + d_spread * f + noise[book][0]
                    view_total = total + d_total * f + noise[book][1]
                    # rec books shade toward the public favourite / Over a little
                    if not is_sharp:
                        view_spread -= 0.2
                        view_total += 0.2
                    slope_s = C.POINT_SLOPE[(sport, "spreads")]
                    slope_t = C.POINT_SLOPE[(sport, "totals")]

                    line = _round_half(view_spread)
                    pa, pb = _price_pair(0.5 + slope_s * (line - view_spread), vig)
                    tline = _round_half(view_total)
                    oa, ob = _price_pair(0.5 + slope_t * (view_total - tline), vig)
                    ha, hb = _price_pair(NormalDist(0, sd).cdf(-view_spread), vig)

                    base = dict(fetched_at=ts, sport=sport, event_id=event_id,
                                commence_time=kickoff, home=home, away=away, book=book)
                    rows += [
                        {**base, "market": "spreads", "outcome": home, "price": pa, "point": line},
                        {**base, "market": "spreads", "outcome": away, "price": pb, "point": -line},
                        {**base, "market": "totals", "outcome": "Over", "price": oa, "point": tline},
                        {**base, "market": "totals", "outcome": "Under", "price": ob, "point": tline},
                        {**base, "market": "h2h", "outcome": home, "price": ha, "point": None},
                        {**base, "market": "h2h", "outcome": away, "price": hb, "point": None},
                    ]

            # simulated public splits
            def split(sharp_on_a: bool | None):
                if sharp_on_a is None:
                    b = rng.uniform(40, 65)
                    return b, b + rng.uniform(-6, 6)
                b = rng.uniform(28, 40)
                return (b, rng.uniform(55, 68)) if sharp_on_a else (100 - b, 100 - rng.uniform(55, 68))

            sp_side = {"sharp_home": True, "sharp_away": False}.get(scenario)
            tot_side = {"sharp_over": True, "sharp_under": False}.get(scenario)
            for market, s in (("spreads", sp_side), ("totals", tot_side)):
                bets, money = split(s)
                splits.append(dict(sport=sport, home=home, away=away, market=market,
                                   side="home" if market == "spreads" else "over",
                                   bets_pct=round(bets), money_pct=round(money)))
    return rows, splits
