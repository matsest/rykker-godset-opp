#!/usr/bin/env python3
"""Fetch latest data from NIFS API and save to data/raw/."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# NIFS API endpoints for OBOS-ligaen 2026
STAGE_ID = 700912
BASE_URL = "https://api.nifs.no"
ENDPOINTS = {
    "table": f"/stages/{STAGE_ID}/table/",
    "matches": f"/stages/{STAGE_ID}/matches/",
}

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
MATCH_STATS_PATH = os.path.join(RAW_DIR, "match_stats.json")

# Stats to extract from match details
MATCH_STAT_KEYS = [
    "totalShots",
    "shotsOnGoal",
    "shotsOffTarget",
    "possession",
    "chances",
]


def fetch_json(url: str) -> dict | list:
    """Fetch JSON from NIFS API."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "rykkergodsetopp/0.1 (+https://github.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def save_json(data, path: str):
    """Save data as pretty-printed JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: str) -> dict | list:
    """Load JSON from disk if it exists."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def extract_match_stats(match_detail: dict) -> dict:
    """Extract relevant stats and goalscorers from a single match detail response."""
    result = match_detail.get("result", {})
    home_goals = result.get("homeScore90")
    away_goals = result.get("awayScore90")

    # Only process completed matches
    if home_goals is None or away_goals is None:
        return {}

    home_team = match_detail["homeTeam"]["name"]
    away_team = match_detail["awayTeam"]["name"]

    home_raw = match_detail["homeTeam"].get("matchStatistics") or {}
    away_raw = match_detail["awayTeam"].get("matchStatistics") or {}

    def pick(stats):
        return {k: stats.get(k) for k in MATCH_STAT_KEYS if stats.get(k) is not None}

    # Extract goalscorers (typeId 2 = goal, typeId 8 = own goal) and assists (typeId 5 = assist)
    goalscorers = []
    assists = []
    for event in match_detail.get("matchEvents", []):
        event_type = event.get("matchEventTypeId")
        person = event.get("person") or {}
        team = event.get("team") or {}
        if event_type in (2, 8):
            goalscorers.append({
                "name": person.get("name"),
                "team": team.get("name"),
                "minute": event.get("time"),
                "own_goal": event_type == 8,
            })
        elif event_type == 5:
            assists.append({
                "name": person.get("name"),
                "team": team.get("name"),
                "minute": event.get("time"),
            })

    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_stats": pick(home_raw),
        "away_stats": pick(away_raw),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "goalscorers": goalscorers,
        "assists": assists,
        "_schema_version": 1,
    }


def _has_incomplete_goalscorers(entry: dict) -> bool:
    """Check if goals were scored but goalscorer list is incomplete."""
    home_goals = entry.get("home_goals", 0) or 0
    away_goals = entry.get("away_goals", 0) or 0
    total_goals = home_goals + away_goals
    if total_goals == 0:
        return False
    goalscorers = entry.get("goalscorers", [])
    return len(goalscorers) < total_goals


def _is_recent(date_str: str, max_days: int = 7) -> bool:
    """Check if a date string is within the last `max_days` days."""
    try:
        d = datetime.fromisoformat(date_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days <= max_days
    except (ValueError, TypeError):
        return False


def _is_old_format(entry: dict) -> bool:
    """Check if cached entry was created by old code (missing _schema_version)."""
    return entry.get("_schema_version", 0) < 1


def fetch_match_stats_incremental(matches_data: list, cache: dict) -> dict:
    """Fetch match-level stats only for matches not already in cache."""
    updated_cache = dict(cache)
    completed_ids = []
    match_dates: dict[str, str] = {}

    for m in matches_data:
        match_id = str(m.get("id"))
        result = m.get("result", {})
        if result.get("homeScore90") is None or result.get("awayScore90") is None:
            continue
        completed_ids.append(match_id)
        match_dates[match_id] = m.get("timestamp", "")

    cached_ids = set(updated_cache.keys())
    missing_ids = [
        mid for mid in completed_ids
        if mid not in cached_ids
        or "assists" not in updated_cache.get(mid, {})
        or _is_old_format(updated_cache.get(mid, {}))
        or (
            _has_incomplete_goalscorers(updated_cache.get(mid, {}))
            and _is_recent(match_dates.get(mid, ""))
        )
    ]

    stale_incomplete = len([
        mid for mid in completed_ids
        if mid in cached_ids
        and not _is_old_format(updated_cache.get(mid, {}))
        and _has_incomplete_goalscorers(updated_cache.get(mid, {}))
        and not _is_recent(match_dates.get(mid, ""))
    ])
    if stale_incomplete:
        print(f"  ({stale_incomplete} older incomplete matches skipped — data likely final)", file=sys.stderr)

    print(f"Match stats: {len(completed_ids)} completed, {len(cached_ids)} cached, {len(missing_ids)} to fetch", file=sys.stderr)

    fetched = 0
    for match_id in missing_ids:
        url = f"{BASE_URL}/matches/{match_id}/"
        try:
            detail = fetch_json(url)
            stats = extract_match_stats(detail)
            if stats:
                updated_cache[match_id] = stats
                fetched += 1
                if fetched % 10 == 0:
                    print(f"  ... fetched {fetched}/{len(missing_ids)} match stats", file=sys.stderr)
        except urllib.error.HTTPError as e:
            print(f"  HTTP error for match {match_id}: {e.code} {e.reason}", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"  URL error for match {match_id}: {e.reason}", file=sys.stderr)

    print(f"  → fetched {fetched} new match stats", file=sys.stderr)
    return updated_cache


def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    metadata = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stage_id": STAGE_ID,
        "endpoints": {},
    }

    for name, endpoint in ENDPOINTS.items():
        url = BASE_URL + endpoint
        print(f"Fetching {name} from {url} ...", file=sys.stderr)
        try:
            data = fetch_json(url)
        except urllib.error.HTTPError as e:
            print(f"HTTP error for {name}: {e.code} {e.reason}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"URL error for {name}: {e.reason}", file=sys.stderr)
            sys.exit(1)

        path = os.path.join(RAW_DIR, f"{name}.json")
        save_json(data, path)
        metadata["endpoints"][name] = {
            "url": url,
            "saved_to": path,
            "records": len(data) if isinstance(data, list) else None,
        }
        print(f"  → saved {path}", file=sys.stderr)

    # Load existing match stats cache
    match_stats_cache = load_json(MATCH_STATS_PATH)

    # Fetch incremental match stats
    matches_data = load_json(os.path.join(RAW_DIR, "matches.json"))
    if isinstance(matches_data, list):
        updated_cache = fetch_match_stats_incremental(matches_data, match_stats_cache)
        save_json(updated_cache, MATCH_STATS_PATH)
        metadata["match_stats"] = {
            "cached": len(match_stats_cache),
            "total": len(updated_cache),
            "newly_fetched": len(updated_cache) - len(match_stats_cache),
            "saved_to": MATCH_STATS_PATH,
        }
        print(f"Match stats saved to {MATCH_STATS_PATH}", file=sys.stderr)

    # Save metadata
    meta_path = os.path.join(RAW_DIR, "metadata.json")
    save_json(metadata, meta_path)
    print(f"Metadata saved to {meta_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
