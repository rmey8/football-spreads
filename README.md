# football-edge

Odds ingestion and **sharp-money detection** for the NFL and college football.
It's pure Python 3.10+ standard library, with nothing to `pip install`.

## Quick start

```bash
cd football-edge

# 1. Try it now on SIMULATED data (no key needed)
python3 -m football_edge demo

# 2. Get a free key at https://the-odds-api.com (500 credits/month), then:
export ODDS_API_KEY=your_key_here
python3 -m football_edge ingest --sport all      # store a snapshot of every line
python3 -m football_edge sharp  --sport all      # rank where the sharp money is
python3 -m football_edge sharp  --only-value     # only plays a book still underprices
python3 -m football_edge sharp  --splits my_splits.csv   # add public bet%/money% splits
```

Reports print to the terminal and are saved to `reports/` as Markdown and CSV.

## Run `ingest` on a schedule

Line movement is the core sharp signal, so you need **several snapshots over
time**. Each ingest stores a full timestamped snapshot in `data/odds.db`
(SQLite). A sensible cadence:

| When | Why |
|---|---|
| Sunday or Monday night, when lines open | Opening lines are the baseline |
| Once a day during the week | Catch early sharp moves |
| Several times on game day | Steam, injury news and closing lines |

**Credits:** each pull costs markets × regions. The default
(`spreads,totals,h2h` × `us,eu`) is 6 credits per sport, or 12 for `--sport all`.
The free 500 credits cover about 40 full pulls a month. To stretch them, use
`--regions us`, which drops Pinnacle (LowVig and BetOnline remain as sharp
books), or `--markets spreads,totals`.

An example cron entry for 10am, 4pm and 10pm daily:
```
0 10,16,22 * * * cd /path/to/football-edge && ODDS_API_KEY=... python3 -m football_edge ingest
```

## How "sharp money" is detected

The tool treats books as two groups. **Sharp books** (Pinnacle, Circa, LowVig,
BetOnline) take big bets from professionals and move on them. **Rec books**
(DraftKings, FanDuel, BetMGM, Caesars, ESPN Bet, and others) cater to the
public and tend to lag. Every quote is converted to a no-vig probability and
adjusted to a common line, so prices like -3 -110 and -3.5 +100 can be compared.

| Signal | Meaning |
|---|---|
| **Sharp vs rec divergence** | Sharp books rate one side higher than rec books do, e.g. Pinnacle -4 while DraftKings is still -3 |
| **Sharp-book movement** | How far the sharp books have moved from opening to now |
| **Steam** | 3 or more books jumped the same direction in the latest snapshot |
| **Money vs bets** (needs splits) | A side has a small share of tickets but a large share of the money, which means big bettors |
| **Reverse line movement** (needs splits) | Most bets are on one side, but the line moves the other way |
| **+EV vs the sharp line** | Some book still offers a price better than the sharp no-vig fair line. This is the actually bettable edge. |

These signals combine into a score, measured in rough percentage points of
edge: **STRONG** is 5 or more, **MODERATE** is 3 to 5, and **LEAN** is below 3.
Plays where the market has already caught up are labeled "Value is gone".
Following sharp money after the move only pays if you can still beat the
number.

Tune books, thresholds and weights in `football_edge/config.py`.

### Public betting splits (optional)

No free API offers splits, but DraftKings, Action Network and VSIN publish
them. Copy the numbers into a CSV:

```
sport,home,away,market,side,bets_pct,money_pct
nfl,Kansas City Chiefs,Buffalo Bills,spreads,home,38,61
nfl,Kansas City Chiefs,Buffalo Bills,totals,over,72,55
```

Team names must match the odds feed. Use `side` = home/away for spreads and
moneyline, and over/under for totals.

## Layout

```
football_edge/
  odds_api.py   The Odds API v4 client and response flattening
  storage.py    SQLite snapshot store
  odds_math.py  American/decimal odds, no-vig, hold, EV
  signals.py    sharp-money signals and play ranking
  splits.py     optional bets%/money% CSV loader
  report.py     terminal / Markdown / CSV output
  demo.py       simulated data generator (not real odds)
  cli.py        `ingest`, `sharp`, `demo` commands
tests/          python3 -m unittest discover -s tests -t .
```

## Caveats

- The points-to-probability conversion uses flat averages (see `POINT_SLOPE`).
  Real values are larger around NFL key numbers like 3 and 7, so treat EV on
  half-point differences near those numbers as approximate.
- Sharp-money signals show where the market is heading. They don't guarantee
  winners. Track closing line value on your plays to judge whether the tool
  helps.
- Check that sports betting is legal where you are, and bet responsibly.

## Roadmap

Planned additions: player props (The Odds API supports per-event prop
markets), your own power-rating model, a closing line value tracker, and a
weekly dashboard.
