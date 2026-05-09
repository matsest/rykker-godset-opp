#!/usr/bin/env python3
"""Generate statistics from raw NIFS data and save to data/stats.json."""

import json
import os
import sys
from datetime import datetime, timezone

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
STATS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "stats.json")
MATCH_STATS_PATH = os.path.join(RAW_DIR, "match_stats.json")

TEAM_NAME = "Strømsgodset"
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


def load_raw(name: str):
    path = os.path.join(RAW_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_match_stats() -> dict:
    """Load cached match statistics if available."""
    if os.path.exists(MATCH_STATS_PATH):
        with open(MATCH_STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def calculate_last_5_points(matches_data: list) -> dict[str, int]:
    """Calculate points from last 5 completed matches for every team."""
    team_matches: dict[str, list[dict]] = {}
    for m in matches_data:
        result = m.get("result", {})
        home_score = result.get("homeScore90")
        away_score = result.get("awayScore90")
        if home_score is None or away_score is None:
            continue

        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        timestamp = m["timestamp"]

        for team, is_home in [(home, True), (away, False)]:
            if team not in team_matches:
                team_matches[team] = []

            if home_score == away_score:
                points = 1
            elif is_home:
                points = 3 if home_score > away_score else 0
            else:
                points = 3 if away_score > home_score else 0

            team_matches[team].append({"timestamp": timestamp, "points": points})

    last_5_points = {}
    for team, matches in team_matches.items():
        matches.sort(key=lambda x: x["timestamp"])
        last_5 = matches[-5:] if len(matches) >= 5 else matches
        last_5_points[team] = sum(m["points"] for m in last_5)

    return last_5_points


def aggregate_team_stats(match_stats: dict, table_rows: list, matches_data: list) -> list[dict]:
    """Aggregate match-level stats per team and combine with table data."""
    # Initialize with table data
    teams = {}
    for row in table_rows:
        name = row["name"]
        teams[name] = {
            "name": name,
            "short_name": row.get("shortName", name),
            "position": row["place"],
            "played": row["played"],
            "goals_scored": row["goalsScored"],
            "goals_conceded": row["goalsConceded"],
            "goal_difference": row["goalDifference"],
            "total_shots": 0,
            "shots_on_goal": 0,
            "chances": 0,
            "possession_sum": 0,
            "possession_matches": 0,
        }

    # Points from last 5 matches
    last_5_points = calculate_last_5_points(matches_data)
    for name, points in last_5_points.items():
        if name in teams:
            teams[name]["points_last_5"] = points

    # Aggregate from match stats cache
    for match_id, data in match_stats.items():
        home_team = data.get("home_team")
        away_team = data.get("away_team")
        home_stats = data.get("home_stats", {})
        away_stats = data.get("away_stats", {})

        for team_name, stats in [(home_team, home_stats), (away_team, away_stats)]:
            if team_name not in teams:
                continue
            t = teams[team_name]
            if "totalShots" in stats and stats["totalShots"] is not None:
                t["total_shots"] += stats["totalShots"]
            if "shotsOnGoal" in stats and stats["shotsOnGoal"] is not None:
                t["shots_on_goal"] += stats["shotsOnGoal"]
            if "chances" in stats and stats["chances"] is not None:
                t["chances"] += stats["chances"]
            if "possession" in stats and stats["possession"] is not None:
                t["possession_sum"] += stats["possession"]
                t["possession_matches"] += 1

    # Calculate derived stats and build final list
    result = []
    for name, t in teams.items():
        possession = round(t["possession_sum"] / t["possession_matches"], 1) if t["possession_matches"] > 0 else 0.0
        conversion_rate = round(t["goals_scored"] / t["shots_on_goal"] * 100, 1) if t["shots_on_goal"] > 0 else 0.0

        result.append({
            "name": t["name"],
            "short_name": t["short_name"],
            "position": t["position"],
            "played": t["played"],
            "goals_scored": t["goals_scored"],
            "goals_conceded": t["goals_conceded"],
            "goal_difference": t["goal_difference"],
            "total_shots": t["total_shots"],
            "shots_on_goal": t["shots_on_goal"],
            "chances": t["chances"],
            "possession": possession,
            "conversion_rate": conversion_rate,
            "points_last_5": t.get("points_last_5", 0),
        })

    return result


def calculate_top_scorers(match_stats: dict) -> list[dict]:
    """Aggregate team goalscorers and assists across all matches and return sorted list by goal points."""
    scorers: dict[str, dict] = {}
    for match_id, data in match_stats.items():
        for g in data.get("goalscorers", []):
            name = g.get("name")
            team = g.get("team")
            if not name or team != TEAM_NAME:
                continue
            if name not in scorers:
                scorers[name] = {"name": name, "goals": 0, "assists": 0}
            scorers[name]["goals"] += 1

        for a in data.get("assists", []):
            name = a.get("name")
            team = a.get("team")
            if not name or team != TEAM_NAME:
                continue
            if name not in scorers:
                scorers[name] = {"name": name, "goals": 0, "assists": 0}
            scorers[name]["assists"] += 1

    for s in scorers.values():
        s["points"] = s["goals"] + s["assists"]

    sorted_scorers = sorted(scorers.values(), key=lambda x: (x["points"], x["goals"]), reverse=True)
    return sorted_scorers


def calculate_rankings(team_stats: list[dict]) -> dict[str, list[tuple]]:
    """Calculate league rankings for each stat category."""
    rankings = {}

    # (field, ascending)
    categories = [
        ("goals_scored", False),
        ("goals_conceded", True),
        ("goal_difference", False),
        ("total_shots", False),
        ("shots_on_goal", False),
        ("chances", False),
        ("possession", False),
        ("conversion_rate", False),
        ("points_last_5", False),
    ]

    for field, ascending in categories:
        # Filter out teams with invalid values; allow negatives for goal_difference
        if field == "goal_difference":
            valid = [(t["name"], t[field]) for t in team_stats if t[field] is not None]
        else:
            valid = [(t["name"], t[field]) for t in team_stats if t[field] is not None and t[field] >= 0]
        sorted_teams = sorted(valid, key=lambda x: x[1], reverse=not ascending)
        rankings[field] = sorted_teams

    return rankings


def get_team_rank(team_name: str, rankings: dict, field: str) -> tuple | None:
    """Return (value, rank, total) for a team in a given ranking."""
    ranked = rankings.get(field, [])
    for i, (name, value) in enumerate(ranked):
        if name == team_name:
            return (value, i + 1, len(ranked))
    return None


def compare_to_table(rank: int, table_position: int) -> str:
    """Return whether a stat rank is better, worse, or equal vs table position."""
    if rank < table_position:
        return "better"
    elif rank > table_position:
        return "worse"
    return "equal"


def main():
    table_data = load_raw("table")
    matches_data = load_raw("matches")
    teams_data = load_raw("teams")
    match_stats = load_match_stats()

    # Extract table rows
    table_rows = table_data.get("teams", [])
    stage_info = table_data.get("stage", {})

    # Find Godset
    team_row = None
    for row in table_rows:
        if row["name"] == TEAM_NAME:
            team_row = row
            break

    if team_row is None:
        print(f"ERROR: Could not find {TEAM_NAME} in table", file=sys.stderr)
        sys.exit(1)

    position = team_row["place"]
    points = team_row["points"]
    played = team_row["played"]

    status_key, status_text = determine_status(position)

    # Calculate distances
    first_place_points = table_rows[0]["points"] if len(table_rows) > 0 else points
    second_place_points = table_rows[1]["points"] if len(table_rows) > 1 else points
    sixth_place_points = table_rows[5]["points"] if len(table_rows) > 5 else points

    points_to_1st = first_place_points - points
    points_to_2nd = second_place_points - points
    points_to_6th = sixth_place_points - points

    # Process all Godset matches
    team_matches = []
    for m in matches_data:
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        if home == TEAM_NAME or away == TEAM_NAME:
            result = parse_match_result(m, TEAM_NAME)
            is_home = home == TEAM_NAME
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
            team_matches.append({
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
    team_matches.sort(key=lambda m: m["date"])

    completed = [m for m in team_matches if m["result"] is not None]
    upcoming = [m for m in team_matches if m["result"] is None]

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

    # W-D-L last 5
    won_last_5 = sum(1 for m in last_5 if m["result"] == "W")
    drawn_last_5 = sum(1 for m in last_5 if m["result"] == "D")
    lost_last_5 = sum(1 for m in last_5 if m["result"] == "L")

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

    # Aggregate league-wide stats from match stats cache
    team_stats = aggregate_team_stats(match_stats, table_rows, matches_data)
    rankings = calculate_rankings(team_stats)

    # Build Godset rank info
    rank_fields = {
        "goals_scored": {"label": "Mål scoret", "format": "{value}"},
        "goals_conceded": {"label": "Mål sluppet inn", "format": "{value}"},
        "goal_difference": {"label": "Målforskjell", "format": "{value}"},
        "total_shots": {"label": "Skudd totalt", "format": "{value}"},
        "shots_on_goal": {"label": "Skudd på mål", "format": "{value}"},
        "chances": {"label": "Sjanser skapt", "format": "{value}"},
        "possession": {"label": "Ballbesittelse", "format": "{value}%"},
        "conversion_rate": {"label": "Målprosent", "format": "{value}%"},
        "points_last_5": {"label": "Form (siste 5)", "format": "{value}"},
    }

    team_ranks = {}
    for field, meta in rank_fields.items():
        rank_info = get_team_rank(TEAM_NAME, rankings, field)
        if rank_info:
            value, rank, total = rank_info
            comparison = compare_to_table(rank, position)
            if field == "goal_difference":
                display_value = f"{'+' if value > 0 else ''}{value}"
            else:
                display_value = meta["format"].format(value=value)
            team_ranks[field] = {
                "label": meta["label"],
                "value": value,
                "rank": rank,
                "total": total,
                "display_value": display_value,
                "display_rank": f"{rank}. av {total}",
                "vs_table": comparison,
            }

    top_scorers = calculate_top_scorers(match_stats)

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": {
            "year": stage_info.get("yearStart"),
            "stage_id": stage_info.get("id"),
            "name": stage_info.get("fullName", "OBOS-ligaen 2026"),
            "total_rounds": stage_info.get("numberOfRounds", 30),
            "current_round": max((m["round"] for m in completed), default=0),
        },
        "top_scorers": top_scorers,
        "godset": {
            "name": TEAM_NAME,
            "short_name": team_row.get("shortName", "Godset"),
            "position": position,
            "played": played,
            "won": team_row["won"],
            "drawn": team_row["draw"],
            "lost": team_row["lost"],
            "goals_for": team_row["goalsScored"],
            "goals_against": team_row["goalsConceded"],
            "goal_difference": team_row["goalDifference"],
            "points": points,
            "points_per_game": round(points / played, 2) if played else 0.0,
            "form_last_5": [m["result"] for m in last_5],
            "points_last_5": points_last_5,
            "points_avg_last_5": points_avg_last_5,
            "won_last_5": won_last_5,
            "drawn_last_5": drawn_last_5,
            "lost_last_5": lost_last_5,
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
            "ranks": team_ranks,
        },
        "last_matches": last_5,
        "upcoming_matches": next_5,
        "table": full_table,
        "team_stats": team_stats,
    }

    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"Stats saved to {STATS_PATH}", file=sys.stderr)
    print(f"Godset: {position}. plass, {points} poeng – {status_text}", file=sys.stderr)

    # Print rank summary
    if team_ranks:
        print(f"\nLigarankinger:", file=sys.stderr)
        for field, info in team_ranks.items():
            indicator = "↑" if info["vs_table"] == "better" else "↓" if info["vs_table"] == "worse" else "→"
            print(f"  {info['label']}: {info['display_value']} ({info['display_rank']}) {indicator}", file=sys.stderr)


if __name__ == "__main__":
    main()
