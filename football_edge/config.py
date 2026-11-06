"""Configuration: sports, books, and signal tuning."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "odds.db"
DEMO_DB = ROOT / "data" / "demo.db"
REPORTS_DIR = ROOT / "reports"

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
}

MARKETS = ("spreads", "totals", "h2h")

# "Sharp" books: low-margin, high-limit shops that welcome winning bettors and
# move their lines on sharp action. Their prices are the best public proxy for
# where professional money is. (Pinnacle is in The Odds API's "eu" region;
# LowVig / BetOnline are in "us".)
SHARP_BOOKS = {"pinnacle", "circasports", "lowvig", "betonlineag"}

# "Recreational" (retail) books: shade lines toward public sides and tend to
# move after the sharp books.
REC_BOOKS = {
    "draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet",
    "fanatics", "betrivers", "bovada", "ballybet", "hardrockbet",
}

# Approximate win-probability change per point of line, used to compare quotes
# at different numbers (e.g. -3 vs -3.5). Rough averages; real values are larger
# around NFL key numbers (3, 7, 10) and smaller elsewhere.
POINT_SLOPE = {
    ("nfl", "spreads"): 0.030,
    ("nfl", "totals"): 0.025,
    ("cfb", "spreads"): 0.022,
    ("cfb", "totals"): 0.018,
}
MAX_LINE_ADJUST = 3.0  # don't extrapolate further than this many points

# Signal thresholds and weights (score units ~= percentage points of win prob)
DIVERGENCE_MIN_PP = 1.0     # sharp vs rec gap worth mentioning
MOVE_MIN_PP = 1.0           # sharp-book movement worth mentioning
STEAM_MIN_SHIFT = 0.015     # per-book move (prob) to count toward steam
STEAM_MIN_BOOKS = 3         # books moving together in one snapshot = steam
STEAM_POINTS = 2.0
SPLIT_GAP_MIN = 10.0        # money% - bets% gap worth flagging
RLM_PUBLIC_MAX = 40.0       # side getting <= this % of bets...
RLM_POINTS = 2.0            # ...but the line moves toward it = reverse line movement
EV_WEIGHT = 0.5             # how much +EV vs the sharp line adds to the score

DEFAULT_MIN_SCORE = 1.5
