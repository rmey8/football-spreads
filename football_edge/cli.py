"""Command-line entry point.

    python -m football_edge ingest        --sport all     # store spreads/totals/ML snapshot
    python -m football_edge ingest-props  --sport nfl     # store player-prop snapshot
    python -m football_edge sharp                         # where the sharp money is (games)
    python -m football_edge props                         # best +EV player props
    python -m football_edge weekly                        # both, as one "best plays" report
    python -m football_edge demo                          # all of the above on simulated data
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config as C
from .odds_api import (OddsAPIError, fetch_event_props, fetch_events, fetch_odds,
                       normalize, normalize_props)
from .props import find_prop_plays
from .report import (props_to_markdown, props_to_text, to_markdown, to_text, write_csv,
                     write_props_csv)
from .signals import find_sharp_plays
from .splits import load_splits
from .storage import connect, insert_prop_rows, insert_rows, load_prop_rows, load_rows


def _sports(arg: str) -> list[str]:
    return list(C.SPORT_KEYS) if arg == "all" else [arg]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _api_key(args) -> str | None:
    key = args.api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        print("Set ODDS_API_KEY (free key at https://the-odds-api.com) or pass --api-key.",
              file=sys.stderr)
    return key


def _save(prefix: str, markdown: str, csv_writer=None, plays=None) -> None:
    C.REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    md = C.REPORTS_DIR / f"{prefix}-{stamp}.md"
    md.write_text(markdown)
    saved = [str(md)]
    if csv_writer:
        cs = C.REPORTS_DIR / f"{prefix}-{stamp}.csv"
        csv_writer(plays, cs)
        saved.append(str(cs))
    print(f"\nSaved {' and '.join(saved)}")


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #
def cmd_ingest(args) -> int:
    key = _api_key(args)
    if not key:
        return 2
    conn = connect(args.db)
    fetched_at = _now()
    for sport in _sports(args.sport):
        try:
            events, quota = fetch_odds(key, sport, regions=args.regions,
                                       markets=args.markets, bookmakers=args.bookmakers)
        except OddsAPIError as exc:
            print(f"[{sport}] {exc}", file=sys.stderr)
            return 1
        n = insert_rows(conn, normalize(events, sport, fetched_at))
        print(f"[{sport}] {len(events)} games, {n} prices stored "
              f"(credits used this call: {quota['x-requests-last']}, "
              f"remaining: {quota['x-requests-remaining']})")
    return 0


def cmd_ingest_props(args) -> int:
    key = _api_key(args)
    if not key:
        return 2
    markets = args.markets.split(",")
    unknown = [m for m in markets if m not in C.PROP_MARKETS]
    if unknown:
        print(f"Unknown prop market(s): {', '.join(unknown)}. Options: {', '.join(C.PROP_MARKETS)}",
              file=sys.stderr)
        return 2
    conn = connect(args.db)
    fetched_at = _now()
    now = datetime.now(timezone.utc)
    spent, remaining = 0, None
    for sport in _sports(args.sport):
        try:
            events, _ = fetch_events(key, sport, now, now + timedelta(days=args.days))
        except OddsAPIError as exc:
            print(f"[{sport}] {exc}", file=sys.stderr)
            return 1
        events.sort(key=lambda e: e["commence_time"])
        if args.teams:
            wanted = [t.strip().lower() for t in args.teams.split(",")]
            events = [e for e in events if any(w in e["home_team"].lower()
                                               or w in e["away_team"].lower() for w in wanted)]
        events = events[:args.max_events] if args.max_events else events
        est = len(events) * len(markets)
        print(f"[{sport}] {len(events)} games in the next {args.days} days; "
              f"up to ~{est} credits for {len(markets)} markets (budget {args.budget - spent})")
        stored = games = 0
        for ev in events:
            if spent + len(markets) > args.budget:
                print(f"[{sport}] stopping: credit budget of {args.budget} reached "
                      f"(raise with --budget)")
                break
            try:
                data, quota = fetch_event_props(key, sport, ev["id"], args.markets,
                                                bookmakers=args.bookmakers)
            except OddsAPIError as exc:
                print(f"[{sport}] {ev['away_team']} @ {ev['home_team']}: {exc}", file=sys.stderr)
                if "429" in str(exc) or "401" in str(exc):
                    return 1
                continue
            spent += int(quota.get("x-requests-last") or 0)
            remaining = quota.get("x-requests-remaining")
            rows = normalize_props(data, sport, fetched_at)
            if rows:
                games += 1
                stored += insert_prop_rows(conn, rows)
        print(f"[{sport}] {stored} prop prices stored from {games} games")
    print(f"Credits spent: {spent}" + (f", remaining: {remaining}" if remaining else ""))
    return 0


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
def _game_rows(db, sport_arg):
    conn = connect(db)
    return [r for s in _sports(sport_arg) for r in load_rows(conn, s, starts_after=_now())]


def _prop_rows(db, sport_arg):
    conn = connect(db)
    return [r for s in _sports(sport_arg) for r in load_prop_rows(conn, s, starts_after=_now())]


def _snapshot_note(rows, what):
    if rows and len({r["fetched_at"] for r in rows}) < 2:
        print(f"\nNote: only one {what} snapshot stored - movement signals need at least "
              "two ingests over time.")


def cmd_sharp(args) -> int:
    rows = _game_rows(args.db, args.sport)
    if not rows:
        print("No upcoming games in the database. Run `ingest` first (or `demo`).")
        return 1
    splits = load_splits(Path(args.splits)) if args.splits else None
    plays = find_sharp_plays(rows, splits, args.min_score, args.only_value)
    title = "Where the sharp money is"
    print(to_text(plays, title))
    _snapshot_note(rows, "odds")
    _save("sharp", to_markdown(plays, title), write_csv, plays)
    return 0


def cmd_props(args) -> int:
    rows = _prop_rows(args.db, args.sport)
    if not rows:
        print("No upcoming props in the database. Run `ingest-props` first (or `demo`).")
        return 1
    plays = find_prop_plays(rows, args.min_ev, args.top)
    title = "Best player props"
    print(props_to_text(plays, title))
    _snapshot_note(rows, "props")
    _save("props", props_to_markdown(plays, title), write_props_csv, plays)
    return 0


def _weekly(db, sport_arg, splits_path, min_score, min_ev, top, title, prefix) -> int:
    game_rows, prop_rows = _game_rows(db, sport_arg), _prop_rows(db, sport_arg)
    if not game_rows and not prop_rows:
        print("Nothing upcoming in the database. Run `ingest` / `ingest-props` first (or `demo`).")
        return 1
    splits = load_splits(Path(splits_path)) if splits_path else None
    games = find_sharp_plays(game_rows, splits, min_score, only_value=True)[:top]
    props = find_prop_plays(prop_rows, min_ev, top)
    print(f"{title}\n")
    print(to_text(games, "Sides & totals: sharp money with value still available"))
    print()
    print(props_to_text(props, "Player props: best +EV prices"))
    md = (f"# {title}\n\n_Generated {datetime.now():%Y-%m-%d %H:%M}_\n\n"
          + to_markdown(games, "Sides & totals").replace("# ", "## ", 1) + "\n"
          + props_to_markdown(props, "Player props").replace("# ", "## ", 1))
    _save(prefix, md)
    return 0


def cmd_weekly(args) -> int:
    return _weekly(args.db, args.sport, args.splits, args.min_score, args.min_ev, args.top,
                   "Best plays of the week", "weekly")


def cmd_demo(args) -> int:
    from .demo import generate, generate_props
    if C.DEMO_DB.exists():
        C.DEMO_DB.unlink()
    rows, splits = generate(args.seed)
    prop_rows = generate_props(args.seed)
    conn = connect(C.DEMO_DB)
    insert_rows(conn, rows)
    insert_prop_rows(conn, prop_rows)
    splits_path = C.DEMO_DB.parent / "demo_splits.csv"
    with open(splits_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(splits[0]))
        w.writeheader()
        w.writerows(splits)
    print(f"Generated {len(rows)} game prices and {len(prop_rows)} prop prices "
          f"(SIMULATED) -> {C.DEMO_DB}\n")
    return _weekly(C.DEMO_DB, "all", splits_path, args.min_score, args.min_ev, args.top,
                   "DEMO (simulated data) - Best plays of the week", "demo")


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="football_edge", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sport = dict(choices=["nfl", "cfb", "all"], default="all")

    p = sub.add_parser("ingest", help="store a snapshot of spreads/totals/moneylines")
    p.add_argument("--sport", **sport)
    p.add_argument("--regions", default="us,eu", help="'us,eu' includes Pinnacle (default)")
    p.add_argument("--markets", default="spreads,totals,h2h")
    p.add_argument("--bookmakers", help="comma list; overrides --regions")
    p.add_argument("--api-key")
    p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ingest-props", help="store a snapshot of player props (costs credits per game)")
    p.add_argument("--sport", choices=["nfl", "cfb", "all"], default="nfl")
    p.add_argument("--markets", default=",".join(C.DEFAULT_PROP_MARKETS),
                   help=f"comma list from: {', '.join(C.PROP_MARKETS)}")
    p.add_argument("--bookmakers", default=C.DEFAULT_PROP_BOOKS,
                   help="up to 10 books = 1 region of credit cost")
    p.add_argument("--days", type=int, default=7, help="only games starting within N days")
    p.add_argument("--max-events", type=int, help="cap the number of games pulled")
    p.add_argument("--teams", help="comma list of team-name fragments to limit games")
    p.add_argument("--budget", type=int, default=C.PROP_BUDGET,
                   help=f"max credits to spend this run (default {C.PROP_BUDGET})")
    p.add_argument("--api-key")
    p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
    p.set_defaults(func=cmd_ingest_props)

    p = sub.add_parser("sharp", help="rank sides/totals the sharp money is on")
    p.add_argument("--sport", **sport)
    p.add_argument("--splits", help="CSV of public bet%%/money%% splits (see splits.py)")
    p.add_argument("--min-score", type=float, default=C.DEFAULT_MIN_SCORE)
    p.add_argument("--only-value", action="store_true",
                   help="only show plays where some book still beats the sharp line")
    p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
    p.set_defaults(func=cmd_sharp)

    p = sub.add_parser("props", help="rank +EV player props")
    p.add_argument("--sport", **sport)
    p.add_argument("--min-ev", type=float, default=C.PROP_MIN_EV, help="e.g. 0.03 = 3%%")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
    p.set_defaults(func=cmd_props)

    for name, fn, hlp in (("weekly", cmd_weekly, "combined best-plays report"),
                          ("demo", cmd_demo, "run the weekly report on simulated data (no key)")):
        p = sub.add_parser(name, help=hlp)
        if name == "weekly":
            p.add_argument("--sport", **sport)
            p.add_argument("--splits")
            p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
        else:
            p.add_argument("--seed", type=int, default=7)
        p.add_argument("--min-score", type=float, default=C.DEFAULT_MIN_SCORE)
        p.add_argument("--min-ev", type=float, default=C.PROP_MIN_EV)
        p.add_argument("--top", type=int, default=15)
        p.set_defaults(func=fn)

    args = ap.parse_args(argv)
    return args.func(args)
