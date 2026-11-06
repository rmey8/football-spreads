"""Client for The Odds API (https://the-odds-api.com), v4.

Free tier: 500 credits/month. Each call costs (#markets x #regions) credits,
so spreads+totals+h2h across us+eu = 6 credits per sport per pull.
"""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import ODDS_API_BASE, SPORT_KEYS

QUOTA_HEADERS = ("x-requests-remaining", "x-requests-used", "x-requests-last")


class OddsAPIError(RuntimeError):
    pass


def fetch_odds(api_key: str, sport: str, regions: str = "us,eu",
               markets: str = "spreads,totals,h2h", bookmakers: str | None = None,
               timeout: int = 30) -> tuple[list, dict]:
    """Return (events JSON, quota headers) for upcoming games in `sport`."""
    params = {
        "apiKey": api_key,
        "markets": markets,
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    # `bookmakers` overrides `regions` in the API
    if bookmakers:
        params["bookmakers"] = bookmakers
    else:
        params["regions"] = regions
    url = f"{ODDS_API_BASE}/sports/{SPORT_KEYS[sport]}/odds?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "football-edge/0.1"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            quota = {h: resp.headers.get(h) for h in QUOTA_HEADERS}
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        hint = {401: "invalid or missing API key", 422: "bad request parameters",
                429: "rate limited / out of credits"}.get(exc.code, "")
        raise OddsAPIError(f"HTTP {exc.code} {hint}: {body}") from exc
    return data, quota


def normalize(events: list, sport: str, fetched_at: str | None = None) -> list[dict]:
    """Flatten the API response into snapshot rows."""
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for ev in events:
        for bm in ev.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                for oc in mkt.get("outcomes", []):
                    rows.append({
                        "fetched_at": fetched_at,
                        "sport": sport,
                        "event_id": ev["id"],
                        "commence_time": ev["commence_time"],
                        "home": ev["home_team"],
                        "away": ev["away_team"],
                        "book": bm["key"],
                        "market": mkt["key"],
                        "outcome": oc["name"],
                        "price": oc["price"],
                        "point": oc.get("point"),
                    })
    return rows
