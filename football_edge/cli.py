"""Command-line entry point.

    python -m football_edge ingest  --sport all            # pull & store odds (needs ODDS_API_KEY)
    python -m football_edge sharp   --sport all            # rank where sharp money is
    python -m football_edge sharp   --splits splits.csv    # ...with public bet%/money% splits
    python -m football_edge demo                           # try it on simulated data, no key
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from .odds_api import OddsAPIError, fetch_odds, normalize
from .report import to_markdown, to_text, write_csv
from .signals import find_sharp_plays
from .splits import load_splits
from .storage import connect, insert_rows, load_rows


def _sports(arg: str) -> list[str]:
    return list(C.SPORT_KEYS) if arg == "all" else [arg]


def cmd_ingest(args) -> int:
    key = args.api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        print("Set ODDS_API_KEY (free key at https://the-odds-api.com) or pass --api-key.",
              file=sys.stderr)
        return 2
    conn = connect(args.db)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
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


def _run_report(db: Path, sport_arg: str, splits_path, min_score: float, title: str,
                out_prefix: str, only_value: bool = False) -> int:
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [r for s in _sports(sport_arg) for r in load_rows(conn, s, starts_after=now)]
    if not rows:
        print("No upcoming games in the database. Run `ingest` first (or `demo`).")
        return 1
    snaps = len({r["fetched_at"] for r in rows})
    splits = load_splits(Path(splits_path)) if splits_path else None
    plays = find_sharp_plays(rows, splits, min_score, only_value)
    print(to_text(plays, title))
    if snaps < 2:
        print("\nNote: only one snapshot stored - line-movement and steam signals need "
              "at least two ingests over time.")
    C.REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    md, cs = C.REPORTS_DIR / f"{out_prefix}-{stamp}.md", C.REPORTS_DIR / f"{out_prefix}-{stamp}.csv"
    md.write_text(to_markdown(plays, title))
    write_csv(plays, cs)
    print(f"\nSaved {md} and {cs}")
    return 0


def cmd_sharp(args) -> int:
    return _run_report(args.db, args.sport, args.splits, args.min_score,
                       "Where the sharp money is", "sharp", args.only_value)


def cmd_demo(args) -> int:
    from .demo import generate
    if C.DEMO_DB.exists():
        C.DEMO_DB.unlink()
    rows, splits = generate(args.seed)
    insert_rows(connect(C.DEMO_DB), rows)
    splits_path = C.DEMO_DB.parent / "demo_splits.csv"
    with open(splits_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(splits[0]))
        w.writeheader()
        w.writerows(splits)
    print(f"Generated {len(rows)} SIMULATED prices -> {C.DEMO_DB}\n")
    return _run_report(C.DEMO_DB, "all", splits_path, args.min_score,
                       "DEMO (simulated data) - Where the sharp money is", "demo", args.only_value)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="football_edge", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="pull current odds from The Odds API and store a snapshot")
    p.add_argument("--sport", choices=["nfl", "cfb", "all"], default="all")
    p.add_argument("--regions", default="us,eu", help="'us,eu' includes Pinnacle (default)")
    p.add_argument("--markets", default="spreads,totals,h2h")
    p.add_argument("--bookmakers", help="comma list; overrides --regions")
    p.add_argument("--api-key")
    p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("sharp", help="rank sides the sharp money is on")
    p.add_argument("--sport", choices=["nfl", "cfb", "all"], default="all")
    p.add_argument("--splits", help="CSV of public bet%%/money%% splits (see splits.py)")
    p.add_argument("--min-score", type=float, default=C.DEFAULT_MIN_SCORE)
    p.add_argument("--only-value", action="store_true",
                   help="only show plays where some book still beats the sharp line")
    p.add_argument("--db", type=Path, default=C.DEFAULT_DB)
    p.set_defaults(func=cmd_sharp)

    p = sub.add_parser("demo", help="run the sharp report on simulated data (no API key)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--min-score", type=float, default=C.DEFAULT_MIN_SCORE)
    p.add_argument("--only-value", action="store_true",
                   help="only show plays where some book still beats the sharp line")
    p.set_defaults(func=cmd_demo)

    args = ap.parse_args(argv)
    return args.func(args)
