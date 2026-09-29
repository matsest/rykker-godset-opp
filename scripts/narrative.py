#!/usr/bin/env python3
"""Build-time narrative judgments via Jev (TypeSafe System One).

Prototype for issue #10 (idea 1: kampetikett). Asks one batched
``Choice`` question per completed match in ``last_matches`` and returns
a typed storyline label the template renders as a pill.

Rules:
- Code owns all data prep and gating; Jev only picks a label.
- Any failure (missing key, API error) returns {} so the site builds
  without badges. Never raise into the stats pipeline.
- Historical rounds are frozen: generate_stats.py only enriches the
  latest round.

Usage (manual review, writes nothing):
    uv run python scripts/narrative.py --round 22
"""

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

# Neutral keys; Norwegian labels/blurbs are user-facing text only.
STORYLINE_LABELS = {
    "dominant_win": "Dominant",
    "grind_win": "Sliteseier",
    "deserved_draw": "Fortjent poeng",
    "lucky_point": "Heldig poeng",
    "wasteful_draw": "Burde vunnet",
    "deserved_loss": "Ufortjent tap",
    "warning_sign": "Varsellampe",
    "even": "Jevn",
}

# Plain-language explanations, shown in the legend and tooltips.
STORYLINE_BLURBS = {
    "dominant_win": "Godset styrte kampen og vant fortjent.",
    "grind_win": "Seier uten å styre kampen, kriget frem eller avgjort på effektivitet.",
    "deserved_draw": "Jevn kamp der ett poeng var som forventet.",
    "lucky_point": "Godset var mest presset, men berget ett poeng.",
    "wasteful_draw": "Godset var klart best, men seieren glapp.",
    "deserved_loss": "Godset var minst like gode, men tapte.",
    "warning_sign": "Tap der lite stemte for Godset.",
}


def get_legend() -> dict:
    """Static legend data (no API call): {key: {label, blurb}}.

    Excludes the internal `even` fallback, which is never displayed.
    """
    return {
        key: {"label": STORYLINE_LABELS[key], "blurb": STORYLINE_BLURBS[key]}
        for key in STORYLINE_LABELS
        if key != "even"
    }

CRITERIA = {
    "dominant_win": "Won and was clearly the better team: more shots, more shots on target, more chances, or clearly more possession. A one-goal win with even underlying stats is never dominant. Conceding 3 or more goals is never dominant either, regardless of shot stats: a shootout win like that is grind_win. Only for wins.",
    "grind_win": "Won without controlling the game: stats even or worse than the opponent, or a scoreline that flatters an even performance. Covers narrow wins, comebacks, and clinical wins built on finishing rather than control. Only for wins.",
    "deserved_draw": "Drew and matched the opponent; the performance warranted a point. If the team clearly outplayed the opponent and should have won, that is wasteful_draw, not this. Only for draws.",
    "lucky_point": "Drew while clearly second-best across multiple columns: worse on at least two of shots, chances and possession. Level shots with only a possession deficit is a deserved_draw, especially away where low possession is normal. Only for draws.",
    "wasteful_draw": "Drew while clearly the better team: much better on shots, chances or possession. The performance warranted a win, not just a point; wasteful finishing or bad luck denied it. Only for draws.",
    "deserved_loss": "Lost while matching or bettering the opponent on stats; the performance deserved more. Only for losses.",
    "warning_sign": "Lost while clearly second-best across multiple columns: worse on at least two of shots, chances and possession. A loss with level underlying stats is a deserved_loss, not a warning sign. Only for losses.",
    "even": "None of the above fits this match.",
}

CONFIDENCE_GATE = 0.6
MARGIN_GATE = 0.2


def load_dotenv():
    """Load TYPESAFE_API_KEY from project .env if not already exported."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("TYPESAFE_API_KEY="):
                os.environ["TYPESAFE_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
                return


def first_goal_side(match: dict) -> str:
    """Return 'us', 'them' or 'none' based on earliest goalscorer entry."""
    scorers = ((match.get("stats") or {}).get("goalscorers") or [])
    if not scorers:
        return "none"
    first = min(scorers, key=lambda g: g.get("minute", 999))
    team = first.get("team")
    if not team:
        return "none"
    if match["is_home"]:
        return "us" if team == match["home_team"] else "them"
    return "us" if team == match["away_team"] else "them"


def build_state(last_matches: list) -> dict:
    """Build the shared Jev state from deterministic match facts."""
    entries = []
    for m in last_matches:
        stats = m.get("stats") or {}
        first = first_goal_side(m)
        entries.append({
            "match_id": m["match_id"],
            "venue": "home" if m["is_home"] else "away",
            "result": m["result"],
            "score": m["score"],
            "goals_for": m["goals_for"],
            "goals_against": m["goals_against"],
            "possession_for": stats.get("possession"),
            "possession_against": stats.get("opponent_possession"),
            "shots_for": stats.get("total_shots"),
            "shots_against": stats.get("opponent_total_shots"),
            "shots_on_goal_for": stats.get("shots_on_goal"),
            "shots_on_goal_against": stats.get("opponent_shots_on_goal"),
            "chances_for": stats.get("chances"),
            "chances_against": stats.get("opponent_chances"),
            "first_goal": first,
            "comeback": first == "them" and m["result"] in ("W", "D"),
        })
    return {"matches": entries}


def build_questions(state: dict) -> dict:
    """One Choice question per match over the shared state."""
    from typesafe_sdk import Choice

    questions = {}
    for i, entry in enumerate(state["matches"]):
        questions[f"storyline_{entry['match_id']}"] = Choice(
            instructions=(
                f"Which label best describes the followed team's underlying "
                f"performance in `matches[{i}]`? Judge from the stat comparison "
                f"(shots, shots on target, chances, possession), not just "
                f"`matches[{i}].result`: a win with worse stats is a grind_win, "
                f"a loss with even stats is a deserved_loss. The `result` "
                f"decides the label family: `W` allows only dominant_win or "
                f"grind_win, `D` only deserved_draw, lucky_point or "
                f"wasteful_draw, `L` only deserved_loss or warning_sign. "
                f"In away matches "
                f"the followed team normally holds less possession, so weigh "
                f"shots and chances more than possession there. A label needs "
                f"support across multiple stat columns, not just one. Use "
                f"`even` when none of the other labels fit."
            ),
            criteria=CRITERIA,
        )
    return questions


CACHE_PATH = os.path.join(PROJECT_ROOT, "data", "storyline_cache.json")

# Bump when CRITERIA/instructions change meaningfully; stale entries are re-queried.
CRITERIA_VERSION = 1


def load_cache() -> dict:
    """Load cached raw Jev answers {match_id: {key, confidence}}."""
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict) or data.get("version") != CRITERIA_VERSION:
        return {}
    labels = data.get("labels")
    return labels if isinstance(labels, dict) else {}


def save_cache(labels: dict) -> None:
    """Persist raw Jev answers alongside the criteria version."""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": CRITERIA_VERSION, "labels": labels}, f, indent=2)


def apply_gate(key: str | None, confidence: float, probabilities: dict) -> bool:
    """Decide whether a raw answer earns a badge."""
    if key in ("even", None):
        return False
    # Confident outright, or a decisive margin over the runner-up:
    # a peaked-but-diffuse split like 0.59/0.26 is still a clear pick.
    probs = sorted(probabilities.values(), reverse=True)
    margin = probs[0] - probs[1] if len(probs) > 1 else 1.0
    return confidence >= CONFIDENCE_GATE or margin >= MARGIN_GATE


def fetch_storylines(last_matches: list, refresh: bool = False) -> dict:
    """Return {match_id: {key, label, confidence}} for gated-in matches.

    Raw answers are cached per match in data/storyline_cache.json, so quiet
    days cost zero tokens: only matches missing from the cache are queried,
    in a single batched call. Gating is applied at read time, so tuning the
    gate never invalidates the cache. Any failure falls back to cached (or
    badge-less) output; never raises into the pipeline.
    """
    completed = [m for m in last_matches if m.get("result") is not None]
    if not completed:
        return {}

    cache = {} if refresh else load_cache()
    pending = [m for m in completed if m["match_id"] not in cache]

    if pending:
        load_dotenv()
        if not os.environ.get("TYPESAFE_API_KEY"):
            print("  (narrative: no TYPESAFE_API_KEY, using cache only)", file=sys.stderr)
            pending = []
        else:
            try:
                from typesafe_sdk import TypeSafeClient

                state = build_state(pending)
                questions = build_questions(state)
                with TypeSafeClient() as client:
                    response = client.system_one(state=state, questions=questions)
                for m in pending:
                    answer = response.answers.get(f"storyline_{m['match_id']}")
                    if answer is not None and answer.choice is not None:
                        cache[m["match_id"]] = {
                            "key": answer.choice,
                            "confidence": round(answer.confidence, 2),
                            "probabilities": {
                                k: round(v, 2) for k, v in answer.probabilities.items()
                            },
                        }
                save_cache(cache)
                print(f"  (narrative: queried Jev for {len(pending)} new match(es), "
                      f"{len(completed) - len(pending)} from cache)", file=sys.stderr)
            except Exception as e:  # noqa: BLE001 - build must never fail on Jev
                print(f"  (narrative: Jev call failed, using cache only: {e})", file=sys.stderr)
    else:
        print(f"  (narrative: all {len(completed)} labels from cache, 0 tokens)", file=sys.stderr)

    result = {}
    for m in completed:
        entry = cache.get(m["match_id"])
        if entry is None:
            continue
        key = entry.get("key")
        if not apply_gate(key, entry.get("confidence", 0.0), entry.get("probabilities", {})):
            continue
        result[m["match_id"]] = {
            "key": key,
            "label": STORYLINE_LABELS[key],
            "confidence": entry.get("confidence", 0.0),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review Jev storyline labels for a round (prints only, writes nothing)."
    )
    parser.add_argument("--round", type=int, required=True, help="Round number to review")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and re-query Jev")
    args = parser.parse_args()

    path = os.path.join(PROJECT_ROOT, "data", f"stats_round_{args.round}.json")
    with open(path, "r", encoding="utf-8") as f:
        stats = json.load(f)

    storylines = fetch_storylines(stats.get("last_matches", []), refresh=args.refresh)
    print(f"Round {args.round} storyline review:")
    for m in stats.get("last_matches", []):
        opp = m["away_team"] if m["is_home"] else m["home_team"]
        venue = "H" if m["is_home"] else "B"
        s = storylines.get(m["match_id"])
        label = f"{s['key']} ({s['confidence']})" if s else "- (gated/cached-miss)"
        print(f"  {venue} vs {opp} {m['score']} [{m['result']}]: {label}")


if __name__ == "__main__":
    main()
