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
    return _get(f"/sports/{SPORT_KEYS[sport]}/odds", params, timeout)


def _get(path: str, params: dict, timeout: int = 30):
    url = f"{ODDS_API_BASE}{path}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "football-edge/0.1"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            quota = {h: resp.headers.get(h) for h in QUOTA_HEADERS}
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        hint = {401: "invalid or missing API key", 404: "event not found",
                422: "bad request parameters (market not offered for this sport?)",
                429: "rate limited / out of credits"}.get(exc.code, "")
        raise OddsAPIError(f"HTTP {exc.code} {hint}: {body}") from exc
    return data, quota


def fetch_events(api_key: str, sport: str, start: datetime, end: datetime) -> tuple[list, dict]:
    """List upcoming events (free: costs no credits)."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return _get(f"/sports/{SPORT_KEYS[sport]}/events", {
        "apiKey": api_key,
        "commenceTimeFrom": start.astimezone(timezone.utc).strftime(fmt),
        "commenceTimeTo": end.astimezone(timezone.utc).strftime(fmt),
    })


def fetch_event_props(api_key: str, sport: str, event_id: str, markets: str,
                      bookmakers: str | None = None, regions: str = "us") -> tuple[dict, dict]:
    """Player-prop odds for one event. Cost: (#markets returned) x (#regions) credits;
    up to 10 `bookmakers` count as one region."""
    params = {"apiKey": api_key, "markets": markets, "oddsFormat": "american",
              "dateFormat": "iso"}
    if bookmakers:
        params["bookmakers"] = bookmakers
    else:
        params["regions"] = regions
    return _get(f"/sports/{SPORT_KEYS[sport]}/events/{event_id}/odds", params)


def normalize_props(event: dict, sport: str, fetched_at: str) -> list[dict]:
    """Flatten one event-odds response into prop snapshot rows."""
    rows = []
    for bm in event.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            for oc in mkt.get("outcomes", []):
                player = oc.get("description")
                if not player:
                    continue
                rows.append({
                    "fetched_at": fetched_at,
                    "sport": sport,
                    "event_id": event["id"],
                    "commence_time": event["commence_time"],
                    "home": event["home_team"],
                    "away": event["away_team"],
                    "book": bm["key"],
                    "market": mkt["key"],
                    "player": player,
                    "outcome": oc["name"],
                    "price": oc["price"],
                    "point": oc.get("point"),
                })
    return rows


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
