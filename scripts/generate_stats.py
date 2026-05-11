#!/usr/bin/env python3
"""Generate statistics from raw NIFS data and save to data/stats.json."""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

MONTHS_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]

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


def calculate_defensive_distributions(matches_data: list) -> dict[str, dict]:
    """Calculate clean sheets and low-conceded matches per team."""
    team_stats: dict[str, dict] = {}
    for m in matches_data:
        result = m.get("result", {})
        home_score = result.get("homeScore90")
        away_score = result.get("awayScore90")
        if home_score is None or away_score is None:
            continue

        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]

        for team, conceded in [(home, away_score), (away, home_score)]:
            if team not in team_stats:
                team_stats[team] = {"clean_sheets": 0, "low_conceded": 0, "high_conceded": 0}
            if conceded == 0:
                team_stats[team]["clean_sheets"] += 1
            if conceded <= 1:
                team_stats[team]["low_conceded"] += 1
            if conceded >= 2:
                team_stats[team]["high_conceded"] += 1

    return team_stats


def calculate_home_away_averages(matches_data: list) -> dict[str, dict]:
    """Calculate points per game for home and away matches per team."""
    team_home: dict[str, list[int]] = {}
    team_away: dict[str, list[int]] = {}

    for m in matches_data:
        result = m.get("result", {})
        home_score = result.get("homeScore90")
        away_score = result.get("awayScore90")
        if home_score is None or away_score is None:
            continue

        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]

        if home_score == away_score:
            home_points = 1
            away_points = 1
        elif home_score > away_score:
            home_points = 3
            away_points = 0
        else:
            home_points = 0
            away_points = 3

        if home not in team_home:
            team_home[home] = []
        team_home[home].append(home_points)

        if away not in team_away:
            team_away[away] = []
        team_away[away].append(away_points)

    averages = {}
    all_teams = set(team_home.keys()) | set(team_away.keys())
    for team in all_teams:
        home_games = team_home.get(team, [])
        away_games = team_away.get(team, [])
        home_avg = round(sum(home_games) / len(home_games), 2) if home_games else 0.0
        away_avg = round(sum(away_games) / len(away_games), 2) if away_games else 0.0
        averages[team] = {"home_avg": home_avg, "away_avg": away_avg}

    return averages


def aggregate_team_stats(match_stats: dict, table_rows: list, matches_data: list, first_goal_stats: dict) -> list[dict]:
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
            "points": row["points"],
            "points_per_game": round(row["points"] / row["played"], 2) if row["played"] > 0 else 0.0,
            "goals_scored": row["goalsScored"],
            "goals_conceded": row["goalsConceded"],
            "goal_difference": row["goalDifference"],
            "total_shots": 0,
            "shots_on_goal": 0,
            "shots_off_target": 0,
            "chances": 0,
            "possession_sum": 0,
            "possession_matches": 0,
            "clean_sheets": 0,
            "low_conceded": 0,
            "high_conceded": 0,
            "total_shots_against": 0,
            "shots_on_goal_against": 0,
            "chances_against": 0,
            "home_avg": 0.0,
            "away_avg": 0.0,
            "stats_matches": 0,
            "first_goal_pct": 0.0,
            "win_when_first_pct": 0.0,
            "conceded_first_pct": 0.0,
            "win_when_conceded_pct": 0.0,
        }

    # Defensive distributions
    defensive_dist = calculate_defensive_distributions(matches_data)
    for name, dist in defensive_dist.items():
        if name in teams:
            teams[name]["clean_sheets"] = dist["clean_sheets"]
            teams[name]["low_conceded"] = dist["low_conceded"]
            teams[name]["high_conceded"] = dist["high_conceded"]

    # Home and away averages
    home_away_avgs = calculate_home_away_averages(matches_data)
    for name, avgs in home_away_avgs.items():
        if name in teams:
            teams[name]["home_avg"] = avgs["home_avg"]
            teams[name]["away_avg"] = avgs["away_avg"]

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

        for team_name, stats, opponent_stats in [
            (home_team, home_stats, away_stats),
            (away_team, away_stats, home_stats),
        ]:
            if team_name not in teams:
                continue
            t = teams[team_name]
            t["stats_matches"] += 1
            if "totalShots" in stats and stats["totalShots"] is not None:
                t["total_shots"] += stats["totalShots"]
            if "shotsOnGoal" in stats and stats["shotsOnGoal"] is not None:
                t["shots_on_goal"] += stats["shotsOnGoal"]
            if "shotsOffTarget" in stats and stats["shotsOffTarget"] is not None:
                t["shots_off_target"] += stats["shotsOffTarget"]
            if "chances" in stats and stats["chances"] is not None:
                t["chances"] += stats["chances"]
            if "possession" in stats and stats["possession"] is not None:
                t["possession_sum"] += stats["possession"]
                t["possession_matches"] += 1
            # Opponent stats (against)
            if "totalShots" in opponent_stats and opponent_stats["totalShots"] is not None:
                t["total_shots_against"] += opponent_stats["totalShots"]
            if "shotsOnGoal" in opponent_stats and opponent_stats["shotsOnGoal"] is not None:
                t["shots_on_goal_against"] += opponent_stats["shotsOnGoal"]
            if "chances" in opponent_stats and opponent_stats["chances"] is not None:
                t["chances_against"] += opponent_stats["chances"]

    # Merge first goal stats
    for name, t in teams.items():
        fg = first_goal_stats.get(name)
        if fg:
            t["first_goal_pct"] = fg["first_goal_pct"]
            t["win_when_first_pct"] = fg["win_when_first_pct"]
            t["conceded_first_pct"] = fg["conceded_first_pct"]
            t["win_when_conceded_pct"] = fg["win_when_conceded_pct"]

    # Normalize per game / percentage to account for different matches played
    for name, t in teams.items():
        played = t["played"]
        stats_matches = t.get("stats_matches", 0)
        if played > 0:
            t["goals_scored"] = round(t["goals_scored"] / played, 2)
            t["goals_conceded"] = round(t["goals_conceded"] / played, 2)
            t["clean_sheets"] = round(t["clean_sheets"] / played * 100, 1)
            t["low_conceded"] = round(t["low_conceded"] / played * 100, 1)
            t["high_conceded"] = round(t["high_conceded"] / played * 100, 1)
        if stats_matches > 0:
            t["total_shots"] = round(t["total_shots"] / stats_matches, 1)
            t["shots_on_goal"] = round(t["shots_on_goal"] / stats_matches, 1)
            t["shots_off_target"] = round(t["shots_off_target"] / stats_matches, 1)
            t["chances"] = round(t["chances"] / stats_matches, 1)
            t["total_shots_against"] = round(t["total_shots_against"] / stats_matches, 1)
            t["shots_on_goal_against"] = round(t["shots_on_goal_against"] / stats_matches, 1)
            t["chances_against"] = round(t["chances_against"] / stats_matches, 1)

    # Calculate derived stats and build final list
    result = []
    for name, t in teams.items():
        possession = round(t["possession_sum"] / t["possession_matches"], 1) if t["possession_matches"] > 0 else 0.0
        conversion_rate = round(t["goals_scored"] / t["shots_on_goal"] * 100, 1) if t["shots_on_goal"] > 0 else 0.0
        accuracy = round(t["shots_on_goal"] / t["total_shots"] * 100, 1) if t["total_shots"] > 0 else 0.0
        chance_conversion = round(t["goals_scored"] / t["chances"] * 100, 1) if t["chances"] > 0 else 0.0

        result.append({
            "name": t["name"],
            "short_name": t["short_name"],
            "position": t["position"],
            "played": t["played"],
            "points": t["points"],
            "points_per_game": t["points_per_game"],
            "goals_scored": t["goals_scored"],
            "goals_conceded": t["goals_conceded"],
            "goal_difference": t["goal_difference"],
            "total_shots": t["total_shots"],
            "shots_on_goal": t["shots_on_goal"],
            "chances": t["chances"],
            "possession": possession,
            "conversion_rate": conversion_rate,
            "accuracy": accuracy,
            "chance_conversion": chance_conversion,
            "points_last_5": t.get("points_last_5", 0),
            "clean_sheets": t["clean_sheets"],
            "low_conceded": t["low_conceded"],
            "high_conceded": t["high_conceded"],
            "total_shots_against": t["total_shots_against"],
            "shots_on_goal_against": t["shots_on_goal_against"],
            "chances_against": t["chances_against"],
            "home_avg": t["home_avg"],
            "away_avg": t["away_avg"],
            "first_goal_pct": t["first_goal_pct"],
            "win_when_first_pct": t["win_when_first_pct"],
            "conceded_first_pct": t["conceded_first_pct"],
            "win_when_conceded_pct": t["win_when_conceded_pct"],
        })

    return result


def calculate_first_goal_stats_league(match_stats: dict) -> dict[str, dict]:
    """Calculate first goal and comeback stats for all teams from match stats."""
    # team -> {matches, first_goal_scored, wins_when_first, conceded_first, wins_when_conceded}
    stats: dict[str, dict] = {}

    for data in match_stats.values():
        home_team = data.get("home_team")
        away_team = data.get("away_team")
        home_goals = data.get("home_goals", 0)
        away_goals = data.get("away_goals", 0)
        goalscorers = data.get("goalscorers", [])

        if not goalscorers:
            continue

        # Find first goal
        first_goal = min(goalscorers, key=lambda g: g.get("minute", 999))
        first_goal_team = first_goal.get("team")
        if not first_goal_team:
            continue

        for team, is_home in [(home_team, True), (away_team, False)]:
            if team not in stats:
                stats[team] = {
                    "matches": 0,
                    "first_goal_scored": 0,
                    "wins_when_first": 0,
                    "conceded_first": 0,
                    "wins_when_conceded": 0,
                }
            stats[team]["matches"] += 1

            if home_goals == away_goals:
                points = 1
            elif is_home:
                points = 3 if home_goals > away_goals else 0
            else:
                points = 3 if away_goals > home_goals else 0

            if first_goal_team == team:
                stats[team]["first_goal_scored"] += 1
                if points == 3:
                    stats[team]["wins_when_first"] += 1
            else:
                stats[team]["conceded_first"] += 1
                if points == 3:
                    stats[team]["wins_when_conceded"] += 1

    # Calculate percentages
    result = {}
    for team, s in stats.items():
        matches = s["matches"]
        first = s["first_goal_scored"]
        conceded = s["conceded_first"]
        result[team] = {
            "first_goal_pct": round(first / matches * 100, 1) if matches > 0 else 0.0,
            "win_when_first_pct": round(s["wins_when_first"] / first * 100, 1) if first > 0 else 0.0,
            "conceded_first_pct": round(conceded / matches * 100, 1) if matches > 0 else 0.0,
            "win_when_conceded_pct": round(s["wins_when_conceded"] / conceded * 100, 1) if conceded > 0 else 0.0,
        }
    return result


def calculate_goal_timing(match_stats: dict) -> dict:
    """Calculate distribution of team goals scored in 15-minute intervals."""
    intervals = [
        (0, 15, "0–15"),
        (16, 30, "16–30"),
        (31, 45, "31–45"),
        (46, 60, "46–60"),
        (61, 75, "61–75"),
        (76, 90, "76–90"),
    ]
    counts = [0] * len(intervals)

    for data in match_stats.values():
        for g in data.get("goalscorers", []):
            if g.get("team") != TEAM_NAME:
                continue
            minute = g.get("minute")
            if minute is None:
                continue
            # Bucket added-time goals into the last interval
            if minute > 90:
                counts[-1] += 1
                continue
            for i, (start, end, _label) in enumerate(intervals):
                if start <= minute <= end:
                    counts[i] += 1
                    break

    total = sum(counts)
    result = []
    for i, (start, end, label) in enumerate(intervals):
        count = counts[i]
        percent = round(count / total * 100, 1) if total > 0 else 0.0
        result.append({
            "label": label,
            "count": count,
            "percent": percent,
        })

    return {
        "intervals": result,
        "total": total,
    }


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
        ("chance_conversion", False),
        ("possession", False),
        ("points_per_game", False),
        ("first_goal_pct", False),
        ("win_when_first_pct", False),
        ("conceded_first_pct", True),
        ("win_when_conceded_pct", False),
        ("home_avg", False),
        ("away_avg", False),
        ("points_last_5", False),
        ("clean_sheets", False),
        ("low_conceded", False),
        ("high_conceded", True),
        ("total_shots_against", True),
        ("shots_on_goal_against", True),
        ("chances_against", True),
    ]

    for field, ascending in categories:
        # Filter out teams with invalid values; allow negatives for goal_difference
        if field == "goal_difference":
            valid = [(t["name"], t[field]) for t in team_stats if t[field] is not None]
        else:
            valid = [(t["name"], t[field]) for t in team_stats if t[field] is not None and t[field] >= 0]
        sorted_teams = sorted(valid, key=lambda x: x[1], reverse=not ascending)

        # Assign dense ranks (teams with same value get same rank)
        ranked = []
        current_rank = 1
        for i, (name, value) in enumerate(sorted_teams):
            if i > 0 and value != sorted_teams[i - 1][1]:
                current_rank = i + 1
            ranked.append((name, value, current_rank))

        rankings[field] = ranked

    return rankings


def get_team_rank(team_name: str, rankings: dict, field: str) -> tuple | None:
    """Return (value, rank, total) for a team in a given ranking."""
    ranked = rankings.get(field, [])
    for name, value, rank in ranked:
        if name == team_name:
            return (value, rank, len(ranked))
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

    # Build full table for frontend
    full_table = []
    for row in table_rows:
        api_name = row["name"]
        short_name = row.get("shortName", api_name)
        full_table.append({
            "position": row["place"],
            "name": api_name,
            "short_name": short_name,
            "display_name": api_name,
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

    # Calculate first goal stats league-wide
    first_goal_stats_league = calculate_first_goal_stats_league(match_stats)

    # Aggregate league-wide stats from match stats cache
    team_stats = aggregate_team_stats(match_stats, table_rows, matches_data, first_goal_stats_league)
    rankings = calculate_rankings(team_stats)

    # Build Godset rank info grouped by category
    rank_categories = {
        "offense": {
            "label": "Offensivt",
            "fields": {
                "goals_scored": {"label": "Mål per kamp", "format": "{value}"},
                "total_shots": {"label": "Skudd per kamp", "format": "{value}"},
                "shots_on_goal": {"label": "Skudd på mål per kamp", "format": "{value}"},
                "chances": {"label": "Sjanser per kamp", "format": "{value}"},
                "chance_conversion": {"label": "Sjanseomsetning", "format": "{value}%"},
                "goal_difference": {"label": "Målforskjell", "format": "{value}"},
            },
        },
        "defense": {
            "label": "Defensivt",
            "fields": {
                "goals_conceded": {"label": "Mål sluppet inn per kamp", "format": "{value}"},
                "total_shots_against": {"label": "Skudd mot per kamp", "format": "{value}"},
                "shots_on_goal_against": {"label": "Skudd på mål mot per kamp", "format": "{value}"},
                "chances_against": {"label": "Sjanser mot per kamp", "format": "{value}"},
                "clean_sheets": {"label": "Clean sheets", "format": "{value}%"},
                "low_conceded": {"label": "≤1 mål sluppet inn", "format": "{value}%"},
            },
        },
        "result": {
            "label": "Resultat",
            "fields": {
                "points_per_game": {"label": "Poeng per kamp", "format": "{value}"},
                "home_avg": {"label": "Poeng per hjemmekamp", "format": "{value}"},
                "away_avg": {"label": "Poeng per bortekamp", "format": "{value}"},
            },
        },
        "control": {
            "label": "Kontroll",
            "fields": {
                "possession": {"label": "Ballbesittelse", "format": "{value}%"},
                "first_goal_pct": {"label": "Førstemål", "format": "{value}%"},
                "win_when_first_pct": {"label": "Seier ved førstemål", "format": "{value}%"},
                "conceded_first_pct": {"label": "Baklengs først", "format": "{value}%"},
                "win_when_conceded_pct": {"label": "Seier ved baklengs først", "format": "{value}%"},
            },
        },
    }

    team_ranks = {}
    for category_key, category in rank_categories.items():
        category_items = {}
        for field, meta in category["fields"].items():
            rank_info = get_team_rank(TEAM_NAME, rankings, field)
            if rank_info:
                value, rank, total = rank_info
                comparison = compare_to_table(rank, position)
                tier = min(abs(rank - position), 3)
                if field == "goal_difference":
                    display_value = f"{'+' if value > 0 else ''}{value}"
                else:
                    display_value = meta["format"].format(value=value)
                category_items[field] = {
                    "label": meta["label"],
                    "value": value,
                    "rank": rank,
                    "total": total,
                    "display_value": display_value,
                    "display_rank": f"{rank}. av {total}",
                    "vs_table": comparison,
                    "vs_table_tier": tier,
                }
        team_ranks[category_key] = {
            "label": category["label"],
            "stats": category_items,
        }

    top_scorers = calculate_top_scorers(match_stats)
    goal_timing = calculate_goal_timing(match_stats)

    stats = {
        "generated_at": (
            lambda d: f"{d.day}. {MONTHS_NO[d.month - 1]} {d.strftime('%H.%M')}"
        )(datetime.now(ZoneInfo("Europe/Oslo"))),
        "season": {
            "year": stage_info.get("yearStart"),
            "stage_id": stage_info.get("id"),
            "name": stage_info.get("fullName", "OBOS-ligaen 2026"),
            "total_rounds": stage_info.get("numberOfRounds", 30),
            "current_round": max((m["round"] for m in completed), default=0),
        },
        "top_scorers": top_scorers,
        "team": {
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
            "goal_timing": goal_timing,
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
        for category_key, category in team_ranks.items():
            print(f"  {category['label']}:", file=sys.stderr)
            for field, info in category["stats"].items():
                indicator = "↑" if info["vs_table"] == "better" else "↓" if info["vs_table"] == "worse" else "→"
                print(f"    {info['label']}: {info['display_value']} ({info['display_rank']}) {indicator}", file=sys.stderr)


if __name__ == "__main__":
    main()
