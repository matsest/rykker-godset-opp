#!/usr/bin/env python3
"""Generate statistics from raw NIFS data and save to data/stats.json."""

import json
import math
import os
import sys
from datetime import datetime, timezone
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

# Fixture Difficulty Rating (FDR) weights, inspired by FPL methodology:
# season strength dominates, recent form (last 5) matters less, and
# venue is adjusted from the teams' actual points averages on that ground.
SEASON_WEIGHT = 0.65
FORM_WEIGHT = 0.35
VENUE_SCALE = 0.5
VENUE_MAX = 1.0
# Fallback venue adjustments before enough matches are played.
HOME_ADJ = -0.35
AWAY_ADJ = 0.5

DIFFICULTY_LABELS = {
    1: "Enkel",
    2: "Overkommelig",
    3: "Middels",
    4: "Tøff",
    5: "Svært tøff",
}


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
        return 95 - (position - 1) * 15
    elif position <= 6:  # Tja
        return 65 - (position - 3) * 8
    else:  # Nei
        return max(5, 30 - (position - 7) * 3)


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


def calculate_last_5_points(matches_data: list) -> dict[str, dict]:
    """Calculate points and average from last 5 completed matches for every team."""
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

            goals_for = home_score if is_home else away_score
            goals_against = away_score if is_home else home_score

            team_matches[team].append({
                "timestamp": timestamp,
                "points": points,
                "goals_for": goals_for,
                "goals_against": goals_against,
            })

    last_5_stats = {}
    for team, matches in team_matches.items():
        matches.sort(key=lambda x: x["timestamp"])
        last_5 = matches[-5:] if len(matches) >= 5 else matches
        total_points = sum(m["points"] for m in last_5)
        goals_for = sum(m["goals_for"] for m in last_5)
        goals_against = sum(m["goals_against"] for m in last_5)
        last_5_stats[team] = {
            "points": total_points,
            "avg": round(total_points / len(last_5), 2) if last_5 else 0.0,
            "goal_difference": goals_for - goals_against,
        }

    return last_5_stats


def calculate_last_5_form(matches_data: list) -> dict[str, list[str]]:
    """Return W/D/L results for last 5 completed matches per team."""
    team_matches: dict[str, list[dict]] = {}
    for m in matches_data:
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        timestamp = m["timestamp"]

        for team in (home, away):
            result = parse_match_result(m, team)
            if result is None:
                continue
            if team not in team_matches:
                team_matches[team] = []
            team_matches[team].append({"timestamp": timestamp, "result": result})

    last_5_form = {}
    for team, matches in team_matches.items():
        matches.sort(key=lambda x: x["timestamp"])
        last_5 = matches[-5:] if len(matches) >= 5 else matches
        last_5_form[team] = [m["result"] for m in last_5]

    return last_5_form


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
    last_5_stats = calculate_last_5_points(matches_data)
    for name, form_stats in last_5_stats.items():
        if name in teams:
            teams[name]["points_last_5"] = form_stats["points"]
            teams[name]["points_avg_last_5"] = form_stats["avg"]
            teams[name]["goal_difference_last_5"] = form_stats["goal_difference"]

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
            "points_avg_last_5": t.get("points_avg_last_5", 0.0),
            "goal_difference_last_5": t.get("goal_difference_last_5", 0),
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

    first_half = sum(counts[:3])
    second_half = sum(counts[3:])

    return {
        "intervals": result,
        "total": total,
        "first_half": first_half,
        "second_half": second_half,
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
        ("points_avg_last_5", False),
        ("goal_difference_last_5", False),
        ("clean_sheets", False),
        ("low_conceded", False),
        ("high_conceded", True),
        ("total_shots_against", True),
        ("shots_on_goal_against", True),
        ("chances_against", True),
    ]

    for field, ascending in categories:
        # Filter out teams with invalid values; allow negatives for goal_difference
        if field == "goal_difference" or field == "goal_difference_last_5":
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
    """Return whether a stat rank is better, worse, equal, or top vs table position."""
    if rank == 1 and table_position == 1:
        return "top"
    if rank < table_position:
        return "better"
    elif rank > table_position:
        return "worse"
    return "equal"


def build_rating_map(team_stats: list[dict], key: str) -> dict[str, float]:
    """Rank teams by a numeric key (highest first) and map rank linearly to 1-5.

    Each rank step is worth 4/(n-1), so there are no bucket cliffs: teams one
    rank apart always differ by the same small amount. Teams with equal values
    share the same rank (competition ranking).
    """
    sorted_teams = sorted(team_stats, key=lambda t: t.get(key, 0), reverse=True)
    n = len(sorted_teams)
    ratings: dict[str, float] = {}
    rank = 0
    prev_value = None
    for i, t in enumerate(sorted_teams):
        value = t.get(key, 0)
        if prev_value is None or value != prev_value:
            rank = i + 1
            prev_value = value
        if n <= 1:
            ratings[t["name"]] = 5.0
        else:
            ratings[t["name"]] = round(1 + 4 * (n - rank) / (n - 1), 2)
    return ratings


def calculate_fixture_difficulty(
    opponent_name: str,
    is_home: bool,
    lookup: dict[str, dict],
    season_ratings: dict[str, float],
    form_ratings: dict[str, float],
    own_name: str,
    form_lists: dict[str, list[str]] | None = None,
) -> dict:
    """Calculate relative FDR 1-5 (1 = easiest) for one upcoming fixture."""
    opp = lookup.get(opponent_name, {})
    own = lookup.get(own_name, {})

    opp_season = season_ratings.get(opponent_name, 3)
    own_season = season_ratings.get(own_name, 3)
    opp_form = form_ratings.get(opponent_name, 3)
    own_form = form_ratings.get(own_name, 3)

    opp_played = opp.get("played", 0)
    own_played = own.get("played", 0)
    league_home = sum(t.get("home_avg", 0.0) for t in lookup.values()) / max(len(lookup), 1)
    league_away = sum(t.get("away_avg", 0.0) for t in lookup.values()) / max(len(lookup), 1)
    if opp_played < 5 or own_played < 5:
        # Early season: form is too noisy, rely on season strength only.
        opp_combined = float(opp_season)
        own_combined = float(own_season)
    else:
        opp_combined = SEASON_WEIGHT * opp_season + FORM_WEIGHT * opp_form
        own_combined = SEASON_WEIGHT * own_season + FORM_WEIGHT * own_form

    if opp_played < 5 or own_played < 5:
        # Too few matches for reliable venue averages: use fixed adjustment.
        venue_adj = HOME_ADJ if is_home else AWAY_ADJ
        own_venue = own.get("home_avg", 0.0) if is_home else own.get("away_avg", 0.0)
        opp_venue = opp.get("away_avg", 0.0) if is_home else opp.get("home_avg", 0.0)
    else:
        # Venue edge measured against the league average on each ground, so
        # home and away figures (which have different baselines) are comparable.
        # Positive edge means the opponent is relatively stronger there.
        own_venue = own.get("home_avg", 0.0) if is_home else own.get("away_avg", 0.0)
        opp_venue = opp.get("away_avg", 0.0) if is_home else opp.get("home_avg", 0.0)
        if is_home:
            edge = (opp_venue - league_away) - (own_venue - league_home)
        else:
            edge = (opp_venue - league_home) - (own_venue - league_away)
        venue_adj = round(
            max(-VENUE_MAX, min(VENUE_MAX, edge * VENUE_SCALE)), 2
        )
    raw = (opp_combined - own_combined) + 3 + venue_adj
    # Absolute elite-opponent bonus: even for a top-rated team, an elite
    # opponent in form can make a fixture very tough. Only applies above
    # combined 4, adding 0-0.5 difficulty.
    elite_bonus = round(max(0.0, opp_combined - 4) * 0.5, 2)
    raw += elite_bonus
    difficulty = max(1, min(5, math.floor(raw + 0.5)))

    opp_ppg = opp.get("points_per_game", 0.0)
    opp_form_avg = opp.get("points_avg_last_5", 0.0)
    own_ground = "hjemme" if is_home else "borte"
    opp_ground = "borte" if is_home else "hjemme"

    opponent_line = (
        f"{opponent_name}: {opp.get('position', '?')}. plass, "
        f"{opp.get('points', '?')} poeng på {opp.get('played', '?')} kamper"
    )
    if elite_bonus > 0:
        opponent_line += (
            f". Toppmotstand: topp 3 på poengsnitt og i form (+{elite_bonus:.2f})"
        )

    form_results = (form_lists or {}).get(opponent_name, [])
    won = form_results.count("W")
    drawn = form_results.count("D")
    lost = form_results.count("L")
    form_points = 3 * won + drawn
    form_line = (
        f"Form siste {len(form_results)}: "
        f"{won} {'seier' if won == 1 else 'seire'}, "
        f"{drawn} uavgjort, {lost} tap ({form_points} poeng)"
    )

    if venue_adj < 0:
        venue_effect = "trekker ned"
    elif venue_adj > 0:
        venue_effect = "trekker opp"
    else:
        venue_effect = "nøytral"

    if is_home:
        own_dev = own_venue - league_home
        opp_dev = opp_venue - league_away
    else:
        own_dev = own_venue - league_away
        opp_dev = opp_venue - league_home

    def dev_words(dev: float, ground: str) -> str:
        if dev > 0.05:
            return f"er {abs(dev):.2f} over {ground}snittet"
        if dev < -0.05:
            return f"er {abs(dev):.2f} under {ground}snittet"
        return f"er på {ground}snittet"

    advantage = own_dev - opp_dev
    if advantage >= 0.5:
        verdict = "klar fordel oss"
    elif advantage >= 0.15:
        verdict = "liten fordel oss"
    elif advantage > -0.15:
        verdict = "omtrent jevnt"
    elif advantage > -0.5:
        verdict = f"liten fordel {opponent_name}"
    else:
        verdict = f"klar fordel {opponent_name}"

    venue_line = (
        f"Bane ({own_ground}): vi {dev_words(own_dev, own_ground)}, "
        f"{opponent_name} {dev_words(opp_dev, opp_ground)} – {verdict}"
    )

    return {
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS[difficulty],
        "opponent_line": opponent_line,
        "form_line": form_line,
        "venue_line": venue_line,
        "opponent_position": opp.get("position"),
        "opponent_points_per_game": opp_ppg,
        "opponent_form_avg": opp_form_avg,
    }


def build_form_stat_rank(
    team_name: str,
    field: str,
    label: str,
    rankings: dict,
    position: int,
    format_value=lambda v: str(v),
) -> dict | None:
    """Build rank info for a form-section stat card."""
    rank_info = get_team_rank(team_name, rankings, field)
    if not rank_info:
        return None
    value, rank, total = rank_info
    comparison = compare_to_table(rank, position)
    tier = min(abs(rank - position), 3)
    return {
        "label": label,
        "value": value,
        "rank": rank,
        "total": total,
        "display_value": format_value(value),
        "display_rank": f"{rank}. av {total}",
        "vs_table": comparison,
        "vs_table_tier": tier,
        "full_table": [
            {
                "rank": r,
                "name": n,
                "value": v,
                "display_value": format_value(v),
            }
            for n, v, r in rankings.get(field, [])
        ],
    }


def get_completed_rounds(matches_data: list) -> list[int]:
    """Return sorted rounds where at least one match has a completed result."""
    rounds = set()
    for m in matches_data:
        if not isinstance(m.get("round"), int):
            continue
        result = m.get("result", {}) or {}
        if result.get("homeScore90") is not None and result.get("awayScore90") is not None:
            rounds.add(m["round"])
    return sorted(rounds)


def build_historical_table_rows(table_data: dict, matches_data: list, target_round: int) -> list[dict]:
    """Rebuild league table from match results up to and including target_round.

    table.json only reflects the latest standings, so historical round pages
    must replay results. Points, goal difference and goals scored decide the
    order; NIFS head-to-head tiebreakers are not reproducible from
    matches.json alone, so remaining ties fall back to name order.
    """
    source_rows = table_data.get("teams", []) if isinstance(table_data, dict) else []
    records: dict[str, dict] = {}
    for row in source_rows:
        name = row["name"]
        records[name] = {
            "name": name,
            "shortName": row.get("shortName", name),
            "withdrawn": row.get("withdrawnPoints", 0) or 0,
            "played": 0,
            "won": 0,
            "draw": 0,
            "lost": 0,
            "goalsScored": 0,
            "goalsConceded": 0,
        }

    for m in matches_data:
        if m.get("round", 0) > target_round:
            continue
        result = m.get("result", {}) or {}
        home_score = result.get("homeScore90")
        away_score = result.get("awayScore90")
        if home_score is None or away_score is None:
            continue
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        for team in (home, away):
            if team not in records:
                records[team] = {
                    "name": team,
                    "shortName": team,
                    "withdrawn": 0,
                    "played": 0,
                    "won": 0,
                    "draw": 0,
                    "lost": 0,
                    "goalsScored": 0,
                    "goalsConceded": 0,
                }
        records[home]["played"] += 1
        records[away]["played"] += 1
        records[home]["goalsScored"] += home_score
        records[home]["goalsConceded"] += away_score
        records[away]["goalsScored"] += away_score
        records[away]["goalsConceded"] += home_score
        if home_score == away_score:
            records[home]["draw"] += 1
            records[away]["draw"] += 1
        elif home_score > away_score:
            records[home]["won"] += 1
            records[away]["lost"] += 1
        else:
            records[away]["won"] += 1
            records[home]["lost"] += 1

    rows = []
    for r in records.values():
        points = r["won"] * 3 + r["draw"] - r["withdrawn"]
        rows.append({
            "name": r["name"],
            "shortName": r["shortName"],
            "played": r["played"],
            "won": r["won"],
            "draw": r["draw"],
            "lost": r["lost"],
            "goalsScored": r["goalsScored"],
            "goalsConceded": r["goalsConceded"],
            "goalDifference": r["goalsScored"] - r["goalsConceded"],
            "points": points,
        })

    rows.sort(key=lambda r: (-r["points"], -r["goalDifference"], -r["goalsScored"], r["name"]))
    for i, r in enumerate(rows):
        r["place"] = i + 1
    return rows


def compute_history(table_data: dict, matches_data: list, completed_rounds: list[int]) -> list[dict]:
    """Return per-round position/points/result for the team across the season."""
    results_by_round: dict[int, str | None] = {}
    for m in matches_data:
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        if home != TEAM_NAME and away != TEAM_NAME:
            continue
        result = parse_match_result(m, TEAM_NAME)
        if result is not None:
            results_by_round[m["round"]] = result

    history = []
    for r in completed_rounds:
        rows = build_historical_table_rows(table_data, matches_data, r)
        for row in rows:
            if row["name"] == TEAM_NAME:
                history.append({
                    "round": r,
                    "position": row["place"],
                    "points": row["points"],
                    "played": row["played"],
                    "result": results_by_round.get(r),
                })
                break
    return history


def build_history_chart(history: list[dict], total_teams: int = 16) -> dict:
    """Precompute SVG coordinates for the season position chart."""
    width, height = 620, 240
    pad_left, pad_right, pad_top, pad_bottom = 30, 12, 12, 24
    rounds = [h["round"] for h in history]
    min_round, max_round = (min(rounds), max(rounds)) if rounds else (1, 1)
    span = max(max_round - min_round, 1)

    def x_pos(r: int) -> float:
        return round(pad_left + (r - min_round) / span * (width - pad_left - pad_right), 1)

    def y_pos(position: int) -> float:
        return round(pad_top + (position - 1) / max(total_teams - 1, 1) * (height - pad_top - pad_bottom), 1)

    dots = [
        {
            "round": h["round"],
            "x": x_pos(h["round"]),
            "y": y_pos(h["position"]),
            "position": h["position"],
            "points": h["points"],
            "result": h.get("result"),
        }
        for h in history
    ]

    def tick_class(position: int) -> str:
        if total_teams != 16:
            return ""
        if position <= 2:
            return "tick-promotion"
        if position <= 6:
            return "tick-qualification"
        if position == 14:
            return "tick-playoff"
        if position >= 15:
            return "tick-relegation"
        return ""
    ticks = [
        {"position": p, "y": y_pos(p), "class": tick_class(p)}
        for p in range(1, total_teams + 1)
    ]
    picked_rounds = sorted(
        {min_round, max_round}
        | {r for r in range(min_round, max_round + 1) if r % 5 == 0}
    )
    x_labels = [{"round": r, "x": x_pos(r)} for r in picked_rounds]
    plot_width = width - pad_left - pad_right
    step = (height - pad_top - pad_bottom) / max(total_teams - 1, 1)

    def band(top: int, bottom: int, css_class: str) -> dict:
        top = max(top, 1)
        bottom = min(bottom, total_teams)
        y = max(y_pos(top) - step / 2, pad_top)
        bottom_edge = min(y_pos(bottom) + step / 2, height - pad_bottom)
        return {
            "x": pad_left,
            "y": round(y, 1),
            "width": plot_width,
            "height": round(max(bottom_edge - y, 0), 1),
            "class": css_class,
        }

    zones = [
        band(1, 2, "zone-promotion"),
        band(3, 6, "zone-qualification"),
        band(14, 14, "zone-playoff"),
        band(15, 16, "zone-relegation"),
    ]
    return {
        "width": width,
        "height": height,
        "pad_bottom": pad_bottom,
        "plot_left": pad_left,
        "plot_right": width - pad_right,
        "min_round": min_round,
        "max_round": max_round,
        "position_points": " ".join(f"{d['x']},{d['y']}" for d in dots),
        "dots": dots,
        "ticks": ticks,
        "zones": zones,
        "x_labels": x_labels,
    }


def main(target_round: int | None = None):
    table_data = load_raw("table")
    matches_data = load_raw("matches")
    match_stats = load_match_stats()

    completed_rounds = get_completed_rounds(matches_data)
    if not completed_rounds:
        print("ERROR: No completed rounds found", file=sys.stderr)
        sys.exit(1)
    latest_round = max(completed_rounds)
    if target_round is None:
        target_round = latest_round
    if target_round not in completed_rounds:
        print(f"ERROR: Round {target_round} has no completed matches "
              f"(completed: {completed_rounds[0]}-{latest_round})", file=sys.stderr)
        sys.exit(1)

    # Season history is identical on every round page; compute before filtering.
    history = compute_history(table_data, matches_data, completed_rounds)
    history_chart = build_history_chart(history, total_teams=len(table_data.get("teams", [])))

    match_round_by_id = {str(m.get("id")): m.get("round", 0) for m in matches_data}

    # Strip results beyond the viewed round so form, table and upcoming
    # fixtures reflect what was known at that point in time.
    filtered_matches = []
    for m in matches_data:
        result = m.get("result", {}) or {}
        if m.get("round", 0) > target_round and result.get("homeScore90") is not None:
            m = {**m, "result": {}}
        filtered_matches.append(m)
    matches_data = filtered_matches
    match_stats = {
        mid: data for mid, data in match_stats.items()
        if match_round_by_id.get(mid, 0) <= target_round
    }

    # Extract table rows (rebuilt from results so historical rounds get correct standings)
    table_rows = build_historical_table_rows(table_data, matches_data, target_round)
    stage_info = table_data.get("stage", {})

    round_completed_at = max(
        (
            m["timestamp"][:10] for m in matches_data
            if m.get("round") == target_round
            and (m.get("result", {}) or {}).get("homeScore90") is not None
        ),
        default=None,
    )

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
            home_score = None
            away_score = None
            goals_for = None
            goals_against = None
            if result is not None:
                home_score = m["result"]["homeScore90"]
                away_score = m["result"]["awayScore90"]
                score = f"{home_score}-{away_score}"
                if is_home:
                    goals_for = home_score
                    goals_against = away_score
                else:
                    goals_for = away_score
                    goals_against = home_score
            match_entry = {
                "match_id": str(m.get("id", "")),
                "date": m["timestamp"],
                "home_team": home,
                "away_team": away,
                "is_home": is_home,
                "result": result,
                "score": score,
                "home_score": home_score,
                "away_score": away_score,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "round": m["round"],
            }

            # Convert timestamp to local time (Europe/Oslo)
            ts = m.get("timestamp")
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_oslo = dt.astimezone(ZoneInfo("Europe/Oslo"))
                match_entry["date_display"] = f"{dt_oslo.day}. {MONTHS_NO[dt_oslo.month - 1]}"
                match_entry["time_display"] = dt_oslo.strftime("%H:%M")
            else:
                match_entry["date_display"] = ""
                match_entry["time_display"] = ""

            # Attach per-match stats if available
            if match_entry["match_id"] and match_entry["match_id"] in match_stats:
                stats_data = match_stats[match_entry["match_id"]]
                team_key = "home_stats" if is_home else "away_stats"
                opp_key = "away_stats" if is_home else "home_stats"
                team_raw = stats_data.get(team_key, {})
                opp_raw = stats_data.get(opp_key, {})
                match_entry["stats"] = {
                    "possession": team_raw.get("possession"),
                    "total_shots": team_raw.get("totalShots"),
                    "shots_on_goal": team_raw.get("shotsOnGoal"),
                    "shots_off_target": team_raw.get("shotsOffTarget"),
                    "chances": team_raw.get("chances"),
                    "opponent_possession": opp_raw.get("possession"),
                    "opponent_total_shots": opp_raw.get("totalShots"),
                    "opponent_shots_on_goal": opp_raw.get("shotsOnGoal"),
                    "opponent_shots_off_target": opp_raw.get("shotsOffTarget"),
                    "opponent_chances": opp_raw.get("chances"),
                    "goalscorers": stats_data.get("goalscorers", []),
                    "assists": stats_data.get("assists", []),
                }

            team_matches.append(match_entry)

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
    last_5_form = calculate_last_5_form(matches_data)
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
            "form": last_5_form.get(api_name, []),
        })

    # Calculate first goal stats league-wide
    first_goal_stats_league = calculate_first_goal_stats_league(match_stats)

    # Aggregate league-wide stats from match stats cache
    team_stats = aggregate_team_stats(match_stats, table_rows, matches_data, first_goal_stats_league)
    rankings = calculate_rankings(team_stats)

    # Enrich upcoming matches with relative Fixture Difficulty Rating (1-5)
    lookup = {t["name"]: t for t in team_stats}
    season_ratings = build_rating_map(team_stats, "points_per_game")
    form_ratings = build_rating_map(team_stats, "points_avg_last_5")
    for m in next_5:
        opponent_name = m["away_team"] if m["is_home"] else m["home_team"]
        m["opponent"] = opponent_name
        m.update(calculate_fixture_difficulty(
            opponent_name, m["is_home"], lookup,
            season_ratings, form_ratings, TEAM_NAME, last_5_form,
        ))

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

    def format_stat_value(value, field, fmt):
        if field == "goal_difference":
            return f"{'+' if value > 0 else ''}{value}"
        return fmt.format(value=value)

    team_ranks = {}
    for category_key, category in rank_categories.items():
        category_items = {}
        for field, meta in category["fields"].items():
            rank_info = get_team_rank(TEAM_NAME, rankings, field)
            if rank_info:
                value, rank, total = rank_info
                comparison = compare_to_table(rank, position)
                tier = min(abs(rank - position), 3)
                display_value = format_stat_value(value, field, meta["format"])
                category_items[field] = {
                    "label": meta["label"],
                    "value": value,
                    "rank": rank,
                    "total": total,
                    "display_value": display_value,
                    "display_rank": f"{rank}. av {total}",
                    "vs_table": comparison,
                    "vs_table_tier": tier,
                    "full_table": [
                        {
                            "rank": r,
                            "name": n,
                            "value": v,
                            "display_value": format_stat_value(v, field, meta["format"]),
                        }
                        for n, v, r in rankings.get(field, [])
                    ],
                }
        team_ranks[category_key] = {
            "label": category["label"],
            "stats": category_items,
        }

    form_points_rank = build_form_stat_rank(
        TEAM_NAME, "points_avg_last_5", "Poeng per kamp", rankings, position,
    )
    form_goal_difference_rank = build_form_stat_rank(
        TEAM_NAME,
        "goal_difference_last_5",
        "Målforskjell",
        rankings,
        position,
        format_value=lambda v: f"{'+' if v > 0 else ''}{v}",
    )

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
            "current_round": target_round,
            "viewed_round": target_round,
            "latest_round": latest_round,
            "available_rounds": completed_rounds,
            "is_historical": target_round != latest_round,
            "round_completed_at": round_completed_at,
        },
        "canonical_url": (
            "https://godset.mats.codes/"
            if target_round == latest_round
            else f"https://godset.mats.codes/{target_round}.html"
        ),
        "history": history,
        "history_chart": history_chart,
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
            "form_points_rank": form_points_rank,
            "form_goal_difference_rank": form_goal_difference_rank,
            "goal_timing": goal_timing,
        },
        "last_matches": last_5,
        "upcoming_matches": next_5,
        "table": full_table,
        "team_stats": team_stats,
    }

    round_path = os.path.join(os.path.dirname(STATS_PATH), f"stats_round_{target_round}.json")
    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    with open(round_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    if target_round == latest_round:
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"Round {target_round}: stats saved to {round_path}", file=sys.stderr)
    print(f"Godset: {position}. plass, {points} poeng – {status_text}", file=sys.stderr)

    # Print rank summary for the latest round only to keep multi-round output readable
    if team_ranks and target_round == latest_round:
        print(f"\nLigarankinger:", file=sys.stderr)
        for category_key, category in team_ranks.items():
            print(f"  {category['label']}:", file=sys.stderr)
            for field, info in category["stats"].items():
                indicator = "★" if info["vs_table"] == "top" else "↑" if info["vs_table"] == "better" else "↓" if info["vs_table"] == "worse" else "→"
                print(f"    {info['label']}: {info['display_value']} ({info['display_rank']}) {indicator}", file=sys.stderr)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate statistics, optionally for a single round.")
    parser.add_argument("--round", type=int, default=None, help="Only build stats for this round")
    args = parser.parse_args()

    if args.round is not None:
        main(target_round=args.round)
    else:
        for completed_round in get_completed_rounds(load_raw("matches")):
            main(target_round=completed_round)
