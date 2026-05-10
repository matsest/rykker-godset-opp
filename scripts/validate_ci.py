#!/usr/bin/env python3
"""Validate data integrity for CI. Run after `make all`."""

import json
import os
import sys

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
STATS_PATH = os.path.join(PROJECT_ROOT, "data", "stats.json")

TEAM_NAME = "Strømsgodset"
EXPECTED_TEAMS = 16

errors = []
warnings = []


def error(msg: str):
    errors.append(msg)
    print(f"  ERROR: {msg}", file=sys.stderr)


def warn(msg: str):
    warnings.append(msg)
    print(f"  WARN:  {msg}", file=sys.stderr)


def load_json(path: str) -> dict | list | None:
    if not os.path.exists(path):
        error(f"Missing file: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON in {path}: {e}")
        return None


def validate_raw():
    print("Validating raw data...", file=sys.stderr)

    table = load_json(os.path.join(RAW_DIR, "table.json"))
    matches = load_json(os.path.join(RAW_DIR, "matches.json"))
    match_stats = load_json(os.path.join(RAW_DIR, "match_stats.json"))

    # table.json structure
    if isinstance(table, dict):
        teams = table.get("teams")
        if not isinstance(teams, list):
            error("table.json missing 'teams' array")
        else:
            if len(teams) != EXPECTED_TEAMS:
                warn(f"table.json has {len(teams)} teams, expected {EXPECTED_TEAMS}")
            team_names = {t.get("name") for t in teams if isinstance(t, dict)}
            if TEAM_NAME not in team_names:
                error(f"'{TEAM_NAME}' not found in table.json")
            else:
                print(f"  -> {len(teams)} teams, {TEAM_NAME} found", file=sys.stderr)
    else:
        error("table.json is not a dict")

    # matches.json structure
    if isinstance(matches, list):
        print(f"  -> {len(matches)} matches in matches.json", file=sys.stderr)
    else:
        error("matches.json is not a list")

    # match_stats coverage
    if isinstance(matches, list) and isinstance(match_stats, dict):
        completed = 0
        for m in matches:
            if not isinstance(m, dict):
                continue
            result = m.get("result", {})
            if result.get("homeScore90") is not None and result.get("awayScore90") is not None:
                completed += 1

        cached = len(match_stats)
        if completed > 0:
            coverage = cached / completed
            print(f"  -> match stats: {cached}/{completed} cached ({coverage:.0%})", file=sys.stderr)
            if coverage < 0.8:
                warn(f"Match stats coverage is only {coverage:.0%} ({cached}/{completed})")
        else:
            print("  -> 0 completed matches, skipping coverage check", file=sys.stderr)
    else:
        warn("Could not compute match stats coverage")


def validate_stats():
    print("Validating stats.json...", file=sys.stderr)

    stats = load_json(STATS_PATH)
    if not isinstance(stats, dict):
        error("stats.json is not a dict")
        return

    # Top-level keys
    required_top = ["generated_at", "season", "top_scorers", "team", "last_matches", "upcoming_matches", "table", "team_stats"]
    for key in required_top:
        if key not in stats:
            error(f"stats.json missing top-level key: '{key}'")

    # team structure
    team = stats.get("team")
    if not isinstance(team, dict):
        error("stats.json 'team' is missing or not a dict")
        return

    team_required = [
        "name", "short_name", "position", "played", "won", "drawn", "lost",
        "goals_for", "goals_against", "goal_difference", "points", "points_per_game",
        "form_last_5", "points_last_5", "points_avg_last_5",
        "won_last_5", "drawn_last_5", "lost_last_5", "goal_difference_last_5",
        "home", "away", "promotion", "ranks", "goal_timing",
    ]
    for key in team_required:
        if key not in team:
            error(f"team missing key: '{key}'")

    # promotion structure
    promo = team.get("promotion")
    if isinstance(promo, dict):
        for key in ["status", "status_text", "gauge_percent", "spots_direct", "spots_qualification", "points_to_1st", "points_to_2nd", "points_to_6th"]:
            if key not in promo:
                error(f"team.promotion missing key: '{key}'")
    else:
        error("team.promotion is missing or not a dict")

    # home / away structure
    for label, key in [("home", "home"), ("away", "away")]:
        section = team.get(key)
        if isinstance(section, dict):
            for sub in ["played", "points", "avg", "played_last_5", "points_last_5", "avg_last_5"]:
                if sub not in section:
                    error(f"team.{key} missing key: '{sub}'")
        else:
            error(f"team.{key} is missing or not a dict")

    # ranks structure
    ranks = team.get("ranks")
    if isinstance(ranks, dict):
        for cat in ["offense", "defense", "efficiency"]:
            if cat not in ranks:
                warn(f"team.ranks missing category: '{cat}'")
            else:
                cat_data = ranks[cat]
                if not isinstance(cat_data, dict) or "stats" not in cat_data:
                    error(f"team.ranks.{cat} has invalid structure")
    else:
        error("team.ranks is missing or not a dict")

    # Sanity checks
    position = team.get("position")
    if isinstance(position, int):
        if not (1 <= position <= EXPECTED_TEAMS):
            error(f"team.position ({position}) is out of range 1-{EXPECTED_TEAMS}")
    else:
        error("team.position is not an int")

    played = team.get("played")
    if isinstance(played, int) and played < 0:
        error("team.played is negative")

    points = team.get("points")
    if isinstance(points, int) and points < 0:
        error("team.points is negative")

    # season structure
    season = stats.get("season")
    if isinstance(season, dict):
        for key in ["year", "stage_id", "name", "total_rounds", "current_round"]:
            if key not in season:
                error(f"season missing key: '{key}'")
    else:
        error("season is missing or not a dict")

    # table structure
    table = stats.get("table")
    if isinstance(table, list):
        if len(table) != EXPECTED_TEAMS:
            warn(f"table has {len(table)} rows, expected {EXPECTED_TEAMS}")
        for i, row in enumerate(table):
            for key in ["position", "name", "short_name", "display_name", "played", "won", "drawn", "lost", "goals_for", "goals_against", "goal_difference", "points"]:
                if key not in row:
                    error(f"table row {i} missing key: '{key}'")
                    break
    else:
        error("table is not a list")

    # last_matches / upcoming_matches
    for key in ["last_matches", "upcoming_matches"]:
        val = stats.get(key)
        if not isinstance(val, list):
            error(f"'{key}' is not a list")


def main():
    print("Running CI data validation...", file=sys.stderr)
    validate_raw()
    validate_stats()

    if warnings:
        print(f"\n{len(warnings)} warning(s)", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} error(s) – CI check failed", file=sys.stderr)
        sys.exit(1)

    print("\nCI validation passed – all data looks good", file=sys.stderr)


if __name__ == "__main__":
    main()
