#!/usr/bin/env python3
"""Generate statistics from raw NIFS data and save to data/stats.json."""

import json
import os
import sys
from datetime import datetime, timezone

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
STATS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "stats.json")

GODSET_NAME = "Strømsgodset"
PROMOTION_SPOTS = 2
QUALIFICATION_SPOTS = 4  # 3rd to 6th
RELEGATION_ZONE = 15


def determine_status(position: int) -> tuple[str, str]:
    """Return (status_key, status_text) based on table position."""
    if position <= PROMOTION_SPOTS:
        return "JA", "Ja!"
    elif position <= PROMOTION_SPOTS + QUALIFICATION_SPOTS:
        return "TJA", "Tja"
    else:
        return "NEI", "Nei"


def gauge_percent(position: int) -> int:
    """Map table position to a 0-100 gauge percentage."""
    if position <= 2:  # Ja!
        return 75 + (2 - position) * 10
    elif position <= 6:  # Tja
        return 35 + (6 - position) * 8
    else:  # Nei
        return max(5, 30 - (position - 7) * 2)


def parse_match_result(match: dict, team_name: str) -> str | None:
    """Return 'W', 'D', 'L', or None if match not completed."""
    result = match.get("result", {})
    home_score = result.get("homeScore90")
    away_score = result.get("awayScore90")
    if home_score is None or away_score is None:
        return None

    home_team = match["homeTeam"]["name"]
    is_home = home_team == team_name

    if home_score == away_score:
        return "D"
    if is_home:
        return "W" if home_score > away_score else "L"
    else:
        return "W" if away_score > home_score else "L"


def main():
    table_data = load_raw("table")
    matches_data = load_raw("matches")
    teams_data = load_raw("teams")

    # Extract table rows
    table_rows = table_data.get("teams", [])
    stage_info = table_data.get("stage", {})

    # Find Godset
    godset_row = None
    for row in table_rows:
        if row["name"] == GODSET_NAME:
            godset_row = row
            break

    if godset_row is None:
        print(f"ERROR: Could not find {GODSET_NAME} in table", file=sys.stderr)
        sys.exit(1)

    position = godset_row["place"]
    points = godset_row["points"]
    played = godset_row["played"]

    status_key, status_text = determine_status(position)

    # Calculate distances
    first_place_points = table_rows[0]["points"] if len(table_rows) > 0 else points
    second_place_points = table_rows[1]["points"] if len(table_rows) > 1 else points
    sixth_place_points = table_rows[5]["points"] if len(table_rows) > 5 else points

    points_to_1st = first_place_points - points
    points_to_2nd = second_place_points - points
    points_to_6th = sixth_place_points - points

    # Process all Godset matches
    godset_matches = []
    for m in matches_data:
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        if home == GODSET_NAME or away == GODSET_NAME:
            result = parse_match_result(m, GODSET_NAME)
            is_home = home == GODSET_NAME
            score = None
            goals_for = None
            goals_against = None
            if result is not None:
                score = f"{m['result']['homeScore90']}-{m['result']['awayScore90']}"
                if is_home:
                    goals_for = m["result"]["homeScore90"]
                    goals_against = m["result"]["awayScore90"]
                else:
                    goals_for = m["result"]["awayScore90"]
                    goals_against = m["result"]["homeScore90"]
            godset_matches.append({
                "date": m["timestamp"],
                "home_team": home,
                "away_team": away,
                "is_home": is_home,
                "result": result,
                "score": score,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "round": m["round"],
            })

    # Sort by timestamp
    godset_matches.sort(key=lambda m: m["date"])

    completed = [m for m in godset_matches if m["result"] is not None]
    upcoming = [m for m in godset_matches if m["result"] is None]

    # Last 5 completed matches (overall)
    last_5 = completed[-5:] if len(completed) >= 5 else completed

    # Last 5 home matches
    home_matches = [m for m in completed if m["is_home"]][-5:]
    # Last 5 away matches
    away_matches = [m for m in completed if not m["is_home"]][-5:]

    # Points from last 5 overall
    points_last_5 = sum(3 if m["result"] == "W" else 1 if m["result"] == "D" else 0 for m in last_5)
    points_avg_last_5 = round(points_last_5 / len(last_5), 2) if last_5 else 0.0

    # Goal difference last 5
    goals_for_last_5 = sum(m["goals_for"] for m in last_5)
    goals_against_last_5 = sum(m["goals_against"] for m in last_5)
    goal_difference_last_5 = goals_for_last_5 - goals_against_last_5

    # Home stats (all home matches)
    home_all = [m for m in completed if m["is_home"]]
    home_all_points = sum(3 if m["result"] == "W" else 1 if m["result"] == "D" else 0 for m in home_all)
    home_all_avg = round(home_all_points / len(home_all), 2) if home_all else 0.0

    # Home stats (last 5 home matches)
    home_points = sum(3 if m["result"] == "W" else 1 if m["result"] == "D" else 0 for m in home_matches)
    home_avg = round(home_points / len(home_matches), 2) if home_matches else 0.0

    # Away stats (all away matches)
    away_all = [m for m in completed if not m["is_home"]]
    away_all_points = sum(3 if m["result"] == "W" else 1 if m["result"] == "D" else 0 for m in away_all)
    away_all_avg = round(away_all_points / len(away_all), 2) if away_all else 0.0

    # Away stats (last 5 away matches)
    away_points = sum(3 if m["result"] == "W" else 1 if m["result"] == "D" else 0 for m in away_matches)
    away_avg = round(away_points / len(away_matches), 2) if away_matches else 0.0

    # Next 5 upcoming matches
    next_5 = upcoming[:5]

    # Display name overrides for specific teams
    DISPLAY_NAME_OVERRIDES = {
        "Strømsgodset": "Strømsgodset",
        "Kongsvinger": "Kongsvinger",
        "Haugesund": "Haugesund",
        "Egersund": "Egersund",
    }

    # Build full table for frontend
    full_table = []
    for row in table_rows:
        api_name = row["name"]
        short_name = row.get("shortName", api_name)
        display_name = DISPLAY_NAME_OVERRIDES.get(api_name, short_name)
        full_table.append({
            "position": row["place"],
            "name": api_name,
            "short_name": short_name,
            "display_name": display_name,
            "played": row["played"],
            "won": row["won"],
            "drawn": row["draw"],
            "lost": row["lost"],
            "goals_for": row["goalsScored"],
            "goals_against": row["goalsConceded"],
            "goal_difference": row["goalDifference"],
            "points": row["points"],
            "form": row.get("lastSixMatches", "").split(",") if row.get("lastSixMatches") else [],
        })

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": {
            "year": stage_info.get("yearStart"),
            "stage_id": stage_info.get("id"),
            "name": stage_info.get("fullName", "OBOS-ligaen 2026"),
            "total_rounds": stage_info.get("numberOfRounds", 30),
            "current_round": max((m["round"] for m in completed), default=0),
        },
        "godset": {
            "name": GODSET_NAME,
            "short_name": godset_row.get("shortName", "Godset"),
            "position": position,
            "played": played,
            "won": godset_row["won"],
            "drawn": godset_row["draw"],
            "lost": godset_row["lost"],
            "goals_for": godset_row["goalsScored"],
            "goals_against": godset_row["goalsConceded"],
            "goal_difference": godset_row["goalDifference"],
            "points": points,
            "points_per_game": round(points / played, 2) if played else 0.0,
            "form_last_5": [m["result"] for m in last_5],
            "points_last_5": points_last_5,
            "points_avg_last_5": points_avg_last_5,
            "goal_difference_last_5": goal_difference_last_5,
            "home": {
                "played": len(home_all),
                "points": home_all_points,
                "avg": home_all_avg,
                "played_last_5": len(home_matches),
                "points_last_5": home_points,
                "avg_last_5": home_avg,
            },
            "away": {
                "played": len(away_all),
                "points": away_all_points,
                "avg": away_all_avg,
                "played_last_5": len(away_matches),
                "points_last_5": away_points,
                "avg_last_5": away_avg,
            },
            "promotion": {
                "status": status_key,
                "status_text": status_text,
                "gauge_percent": gauge_percent(position),
                "spots_direct": PROMOTION_SPOTS,
                "spots_qualification": QUALIFICATION_SPOTS,
                "points_to_1st": points_to_1st,
                "points_to_2nd": points_to_2nd,
                "points_to_6th": points_to_6th,
            },
        },
        "last_matches": last_5,
        "upcoming_matches": next_5,
        "table": full_table,
    }

    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"Stats saved to {STATS_PATH}", file=sys.stderr)
    print(f"Godset: {position}. plass, {points} poeng – {status_text}", file=sys.stderr)


def load_raw(name: str):
    path = os.path.join(RAW_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
