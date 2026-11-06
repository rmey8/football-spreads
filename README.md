# football-edge

Odds ingestion, **sharp-money detection** and a **player-prop value finder**
for the NFL and college football, combined into a weekly best-plays report.
It's pure Python 3.10+ standard library, with nothing to `pip install`.

## Quick start

```bash
cd football-edge

# 1. Try it now on SIMULATED data (no key needed)
python3 -m football_edge demo

# 2. Get a free key at https://the-odds-api.com (500 credits/month), then:
export ODDS_API_KEY=your_key_here
python3 -m football_edge ingest --sport all      # store a snapshot of every game line
python3 -m football_edge ingest-props            # store NFL player props (budgeted, see below)
python3 -m football_edge weekly                  # best plays of the week: sides, totals, props

# Or run the pieces on their own
python3 -m football_edge sharp  --only-value     # where the sharp money is (games)
python3 -m football_edge sharp  --splits my_splits.csv   # add public bet%/money% splits
python3 -m football_edge props  --min-ev 0.03    # props at least 3% +EV
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

## Player props

### How a prop is judged

Every book's over/under price implies a **projection**. For example, 64.5
receiving yards with the Over at -130 means the book expects a bit more than
64.5. The tool solves for that projection at every book, using a normal
distribution with a typical spread for each stat (`PROP_SD` in `config.py`).
That puts every book on the same scale even when their lines differ.

- **Fair projection** is Pinnacle's when it posts the prop. Otherwise it's the
  median of all books (the consensus). At least 3 books are required.
- **Edge** is the win probability at a book's line under the fair projection,
  compared against that book's price. The usual edge comes from a book that
  is slow to move or hangs an off-market number, such as 58.5 while everyone
  else is at 64.5.
- **Also reported:** how far the lines spread across books, how the market
  moved since your first snapshot, and whether Pinnacle disagrees with the
  rec books.
- **Anytime TD** and other yes/no props are compared on no-vig probability.
  When a book only offers "Yes", the tool removes an assumed 7% margin.

### Credit budgeting (important on the free tier)

Props are priced **per game**. Each game costs one credit per market, and up
to 10 bookmakers count as one region. The defaults are 5 markets and
10 books, so a full NFL Sunday slate of about 14 games costs about 70 credits.
`ingest-props` stops once `--budget` credits are spent (default 100), and the
events list it reads first is free.

```bash
python3 -m football_edge ingest-props --teams "chiefs,bills" --budget 20   # specific games
python3 -m football_edge ingest-props --markets player_reception_yds,player_receptions
python3 -m football_edge ingest-props --sport cfb --max-events 6 --days 3
```

Available markets: `player_pass_yds`, `player_pass_tds`,
`player_pass_completions`, `player_pass_attempts`,
`player_pass_interceptions`, `player_rush_yds`, `player_rush_attempts`,
`player_receptions`, `player_reception_yds`, `player_rush_reception_yds`, and
`player_anytime_td`. College prop coverage is much thinner than NFL coverage.

**Timing:** prop lines usually post 2 to 4 days before kickoff and move most
on injury and inactive news. With 500 credits, one midweek pull and one on
game morning for the NFL slate is a realistic cadence.

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
  odds_api.py   The Odds API v4 client: game odds, events, per-game player props
  storage.py    SQLite snapshot store
  odds_math.py  American/decimal odds, no-vig, hold, EV
  signals.py    sharp-money signals for spreads/totals/moneylines
  props.py      player-prop projections and +EV finder
  splits.py     optional bets%/money% CSV loader
  report.py     terminal / Markdown / CSV output
  demo.py       simulated data generator (not real odds)
  cli.py        ingest, ingest-props, sharp, props, weekly, demo
tests/          python3 -m unittest discover -s tests -t .
```

## Caveats

- The points-to-probability conversion uses flat averages (see `POINT_SLOPE`).
  Real values are larger around NFL key numbers like 3 and 7, so treat EV on
  half-point differences near those numbers as approximate.
- The prop model uses one fixed spread per stat. Real spreads scale with the
  player, so a backup's 12.5 receiving yards is more lopsided than a WR1's
  72.5. Receptions and touchdowns are whole numbers, so treat EV on those as
  approximate, and treat a very large EV (above about 10%) as a sign of stale
  data or a line you misread before trusting it.
- Sharp-money signals show where the market is heading. They don't guarantee
  winners. Track closing line value on your plays to judge whether the tool
  helps.
- Check that sports betting is legal where you are, and bet responsibly.

## Roadmap

Planned additions: a closing line value tracker that logs plays and grades
them against the closing number, your own power-rating and player-projection
models, and a weekly dashboard.
