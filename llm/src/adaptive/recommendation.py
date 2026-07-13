"""Recommendation Engine — maps AdaptiveDecision to concrete exercises.

Given a topic and difficulty from the Adaptive Engine, it:
  1. Maps difficulty (easy/medium/hard) to CEFR levels using student's level.
  2. Searches materials whose tags or name match the topic.
  3. Excludes exercises the student has already attempted recently.
  4. Ranks by level relevance and returns up to `limit` results.
"""

# CEFR scale used for level mapping
CEFR_LEVELS: list[str] = ["A1", "A2", "B1", "B2", "C1", "C2"]

# How many adjacent levels to include when filtering materials
_WINDOW = 1


def difficulty_to_cefr(student_level: str, difficulty: str) -> list[str]:
    """Map a student level + difficulty to a list of acceptable CEFR levels.

    Parameters
    ----------
    student_level : str
        Student's current CEFR level (e.g. "B1").
    difficulty : str
        Target difficulty: "easy" | "medium" | "hard".

    Returns
    -------
    list[str]
        Acceptable CEFR levels, ordered from most to least preferred.
    """
    try:
        base = CEFR_LEVELS.index(student_level.upper())
    except ValueError:
        base = 2  # default to B1

    if difficulty == "easy":
        target = max(0, base - 1)
    elif difficulty == "hard":
        target = min(len(CEFR_LEVELS) - 1, base + 1)
    else:
        target = base

    # target level first, then adjacent levels as fallback
    candidates: list[str] = [CEFR_LEVELS[target]]
    if target > 0:
        candidates.append(CEFR_LEVELS[target - 1])
    if target < len(CEFR_LEVELS) - 1:
        candidates.append(CEFR_LEVELS[target + 1])
    return candidates


def rank_materials(
    materials: list[dict],
    topic: str,
    preferred_levels: list[str],
    seen_ids: set[int],
) -> list[dict]:
    """Score and rank materials by relevance.

    Scoring:
      +3  — exact topic match in tags
      +2  — topic appears in name (case-insensitive)
      +2  — first preferred level (exact match)
      +1  — second preferred level
       0  — any other level
      -10 — already attempted (moved to end)

    Parameters
    ----------
    materials : list[dict]
        Raw material dicts from the repository.
    topic : str
        Target topic (e.g. "Present Perfect").
    preferred_levels : list[str]
        Ordered list of acceptable CEFR levels (most preferred first).
    seen_ids : set[int]
        Exercise IDs the student has already attempted.

    Returns
    -------
    list[dict]
        Materials sorted by score descending.
    """
    topic_lower = topic.lower()

    def score(m: dict) -> int:
        s = 0
        tags = [t.lower() for t in (m.get("tags") or [])]
        if topic_lower in tags:
            s += 3
        if topic_lower in (m.get("name") or "").lower():
            s += 2
        level = (m.get("level") or "").upper()
        if preferred_levels and level == preferred_levels[0]:
            s += 2
        elif len(preferred_levels) > 1 and level == preferred_levels[1]:
            s += 1
        if m["id"] in seen_ids:
            s -= 10
        return s

    return sorted(materials, key=score, reverse=True)
