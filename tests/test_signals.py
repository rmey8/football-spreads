import unittest

from football_edge.demo import generate
from football_edge.odds_api import normalize
from football_edge.signals import build_markets, find_sharp_plays

SAMPLE_API = [{
    "id": "e1", "sport_key": "americanfootball_nfl", "commence_time": "2099-01-01T18:00:00Z",
    "home_team": "Home", "away_team": "Away",
    "bookmakers": [{
        "key": "pinnacle", "title": "Pinnacle", "last_update": "x",
        "markets": [
            {"key": "spreads", "outcomes": [{"name": "Home", "price": -105, "point": -3.5},
                                            {"name": "Away", "price": -105, "point": 3.5}]},
            {"key": "totals", "outcomes": [{"name": "Over", "price": -108, "point": 44.5},
                                           {"name": "Under", "price": -102, "point": 44.5}]},
        ]}],
}]


def rows_for(snapshots):
    """snapshots: list of (ts, {book: (home_line, home_price, away_price)})"""
    rows = []
    for ts, books in snapshots:
        for book, (line, pa, pb) in books.items():
            base = dict(fetched_at=ts, sport="nfl", event_id="e1",
                        commence_time="2099-01-01T18:00:00Z", home="Home", away="Away",
                        book=book, market="spreads")
            rows.append({**base, "outcome": "Home", "price": pa, "point": line})
            rows.append({**base, "outcome": "Away", "price": pb, "point": -line})
    return rows


class SignalsTest(unittest.TestCase):
    def test_normalize_api_response(self):
        rows = normalize(SAMPLE_API, "nfl", "2098-12-31T00:00:00+00:00")
        self.assertEqual(len(rows), 4)
        markets = build_markets(rows)
        q = markets[("nfl", "e1", "spreads")]["books"]["pinnacle"][0]
        self.assertEqual((q.line, q.price_a, q.price_b), (-3.5, -105, -105))

    def test_sharp_move_and_divergence_point_to_home(self):
        rows = rows_for([
            ("t1", {"pinnacle": (-3, -105, -105), "draftkings": (-3, -110, -110),
                    "fanduel": (-3, -110, -110)}),
            ("t2", {"pinnacle": (-4, -105, -105), "draftkings": (-3, -110, -110),
                    "fanduel": (-3, -110, -110)}),
        ])
        plays = find_sharp_plays(rows, min_score=0.5)
        self.assertEqual(len(plays), 1)
        p = plays[0]
        self.assertEqual(p.label, "Home -3")
        self.assertIn(p.best_book, {"draftkings", "fanduel"})
        self.assertGreater(p.ev, 0)

    def test_quiet_market_has_no_play(self):
        books = {"pinnacle": (-3, -105, -105), "draftkings": (-3, -105, -105)}
        rows = rows_for([("t1", books), ("t2", books)])
        self.assertEqual(find_sharp_plays(rows, min_score=0.5), [])

    def test_splits_reverse_line_movement(self):
        rows = rows_for([
            ("t1", {"pinnacle": (-3, -105, -105), "draftkings": (-3, -110, -110)}),
            ("t2", {"pinnacle": (-2, -105, -105), "draftkings": (-2.5, -110, -110)}),
        ])
        splits = {("nfl", "home", "away", "spreads"): (75.0, 60.0)}  # public on Home
        p = find_sharp_plays(rows, splits, min_score=0.5)[0]
        self.assertTrue(p.label.startswith("Away"))
        self.assertTrue(any("Reverse line movement" in r for r in p.reasons))

    def test_demo_runs(self):
        rows, splits = generate(seed=1)
        self.assertTrue(rows and splits)


if __name__ == "__main__":
    unittest.main()
