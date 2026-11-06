import unittest

from football_edge.demo import generate_props
from football_edge.odds_api import normalize_props
from football_edge.props import (PropQuote, build_prop_markets, find_prop_plays,
                                 implied_projection, p_over)

KICK = "2099-01-01T18:00:00Z"

SAMPLE_EVENT = {
    "id": "e1", "commence_time": KICK, "home_team": "Home", "away_team": "Away",
    "bookmakers": [{"key": "draftkings", "markets": [
        {"key": "player_reception_yds", "outcomes": [
            {"name": "Over", "description": "Joe Receiver", "price": -115, "point": 64.5},
            {"name": "Under", "description": "Joe Receiver", "price": -105, "point": 64.5}]},
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "Joe Receiver", "price": 150}]},
    ]}],
}


def prop_rows(snapshots, market="player_reception_yds", player="Joe Receiver"):
    """snapshots: list of (ts, {book: (line, over_price, under_price)})"""
    rows = []
    for ts, books in snapshots:
        for book, (line, o, u) in books.items():
            base = dict(fetched_at=ts, sport="nfl", event_id="e1", commence_time=KICK,
                        home="Home", away="Away", book=book, market=market, player=player)
            rows.append({**base, "outcome": "Over", "price": o, "point": line})
            if u is not None:
                rows.append({**base, "outcome": "Under", "price": u, "point": line})
    return rows


class PropsTest(unittest.TestCase):
    def test_normalize_event_props(self):
        rows = normalize_props(SAMPLE_EVENT, "nfl", "2098-12-31T00:00:00+00:00")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["player"], "Joe Receiver")
        m = build_prop_markets(rows)
        self.assertIn(("nfl", "e1", "player_reception_yds", "Joe Receiver"), m)
        td = m[("nfl", "e1", "player_anytime_td", "Joe Receiver")]["books"]["draftkings"][0]
        self.assertIsNone(td.line)
        self.assertIsNone(td.price_b)

    def test_projection_round_trip(self):
        q = PropQuote("x", "t", 64.5, -150, 130)
        mu = implied_projection(q, 24.0)
        self.assertGreater(mu, 64.5)  # Over is favoured -> projection above the line
        self.assertAlmostEqual(p_over(64.5, 64.5, 24.0), 0.5)

    def test_off_market_line_is_found(self):
        books = {
            "pinnacle": (64.5, -110, -110),
            "fanduel": (64.5, -112, -108),
            "betmgm": (65.5, -105, -115),
            "draftkings": (57.5, -110, -110),   # stale, 7 yards low -> Over value
        }
        plays = find_prop_plays(prop_rows([("t1", books)]), min_ev=0.02)
        self.assertEqual(len(plays), 1)
        p = plays[0]
        self.assertEqual((p.side, p.line, p.best_book), ("Over", 57.5, "draftkings"))
        self.assertGreater(p.ev, 0.05)

    def test_efficient_market_has_no_play(self):
        books = {b: (64.5, -110, -110) for b in ("pinnacle", "fanduel", "betmgm", "draftkings")}
        self.assertEqual(find_prop_plays(prop_rows([("t1", books)])), [])

    def test_needs_minimum_books(self):
        books = {"pinnacle": (64.5, -110, -110), "draftkings": (57.5, -110, -110)}
        self.assertEqual(find_prop_plays(prop_rows([("t1", books)])), [])

    def test_anytime_td_one_sided(self):
        books = {"pinnacle": (None, 200, -250), "fanduel": (None, 160, None),
                 "draftkings": (None, 260, None)}
        rows = prop_rows([("t1", books)], market="player_anytime_td")
        p = find_prop_plays(rows)[0]
        self.assertEqual((p.side, p.best_book), ("Yes", "draftkings"))

    def test_demo_props(self):
        rows = generate_props(seed=3)
        self.assertTrue(find_prop_plays(rows))


if __name__ == "__main__":
    unittest.main()
