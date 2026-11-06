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

# --------------------------------------------------------------------------- #
# Player props
# --------------------------------------------------------------------------- #
# The Odds API prop market keys -> display names
PROP_MARKETS = {
    "player_pass_yds": "Pass Yds",
    "player_pass_tds": "Pass TDs",
    "player_pass_completions": "Completions",
    "player_pass_attempts": "Pass Att",
    "player_pass_interceptions": "INTs",
    "player_rush_yds": "Rush Yds",
    "player_rush_attempts": "Rush Att",
    "player_receptions": "Receptions",
    "player_reception_yds": "Rec Yds",
    "player_rush_reception_yds": "Rush+Rec Yds",
    "player_anytime_td": "Anytime TD",
}
DEFAULT_PROP_MARKETS = ("player_pass_yds", "player_rush_yds", "player_reception_yds",
                        "player_receptions", "player_anytime_td")
YES_NO_MARKETS = {"player_anytime_td"}

# Up to 10 bookmakers cost the same as one region. Pinnacle is the sharp anchor;
# the rest form the consensus and are where you'd actually place the bet.
DEFAULT_PROP_BOOKS = ("pinnacle,draftkings,fanduel,betmgm,williamhill_us,espnbet,"
                      "fanatics,betrivers,betonlineag,bovada")
SHARP_PROP_BOOKS = {"pinnacle", "circasports"}

# Typical standard deviation of each stat around its projection (NFL). Used to
# turn an over/under price into an implied projection and to price other lines.
# College stats are more volatile, so they get CFB_SD_MULTIPLIER.
PROP_SD = {
    "player_pass_yds": 58.0,
    "player_pass_tds": 0.95,
    "player_pass_completions": 4.5,
    "player_pass_attempts": 5.5,
    "player_pass_interceptions": 0.8,
    "player_rush_yds": 22.0,
    "player_rush_attempts": 4.0,
    "player_receptions": 1.7,
    "player_reception_yds": 24.0,
    "player_rush_reception_yds": 27.0,
}
CFB_SD_MULTIPLIER = 1.15

ONE_SIDED_VIG = 0.07     # assumed margin when a book only offers one side (e.g. TD "Yes")
PROP_MIN_BOOKS = 3       # need at least this many books for a consensus fair line
PROP_MIN_EV = 0.02       # only list props at least this +EV
PROP_MOVE_WEIGHT = 0.5
PROP_DIVERGENCE_WEIGHT = 0.5
PROP_BUDGET = 100        # default max API credits spent per props ingest
