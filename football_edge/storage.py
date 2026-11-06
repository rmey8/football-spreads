"""SQLite storage for timestamped odds snapshots.

Every ingest appends a full snapshot, so line movement can be reconstructed
later (opening line, current line, steam moves, closing line value).
"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    fetched_at    TEXT NOT NULL,
    sport         TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    home          TEXT NOT NULL,
    away          TEXT NOT NULL,
    book          TEXT NOT NULL,
    market        TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    price         REAL NOT NULL,
    point         REAL
);
CREATE INDEX IF NOT EXISTS idx_snap_event
    ON snapshots (sport, event_id, market, book, fetched_at);

CREATE TABLE IF NOT EXISTS prop_snapshots (
    fetched_at    TEXT NOT NULL,
    sport         TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    home          TEXT NOT NULL,
    away          TEXT NOT NULL,
    book          TEXT NOT NULL,
    market        TEXT NOT NULL,
    player        TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    price         REAL NOT NULL,
    point         REAL
);
CREATE INDEX IF NOT EXISTS idx_prop_event
    ON prop_snapshots (sport, event_id, market, player, book, fetched_at);
"""

COLUMNS = ("fetched_at", "sport", "event_id", "commence_time", "home", "away",
           "book", "market", "outcome", "price", "point")
PROP_COLUMNS = ("fetched_at", "sport", "event_id", "commence_time", "home", "away",
                "book", "market", "player", "outcome", "price", "point")


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _insert(conn, table, cols, rows) -> int:
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [tuple(r[c] for c in cols) for r in rows],
    )
    conn.commit()
    return len(rows)


def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    return _insert(conn, "snapshots", COLUMNS, rows)


def insert_prop_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    return _insert(conn, "prop_snapshots", PROP_COLUMNS, rows)


def load_rows(conn: sqlite3.Connection, sport: str | None = None,
              starts_after: str | None = None, table: str = "snapshots") -> list[dict]:
    if table not in ("snapshots", "prop_snapshots"):
        raise ValueError(table)
    sql = f"SELECT * FROM {table} WHERE 1=1"
    args: list = []
    if sport:
        sql += " AND sport = ?"
        args.append(sport)
    if starts_after:
        sql += " AND commence_time > ?"
        args.append(starts_after)
    sql += " ORDER BY fetched_at"
    return [dict(r) for r in conn.execute(sql, args)]


def load_prop_rows(conn: sqlite3.Connection, sport: str | None = None,
                   starts_after: str | None = None) -> list[dict]:
    return load_rows(conn, sport, starts_after, table="prop_snapshots")
