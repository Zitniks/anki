"""Adaptive Engine — rule-based pedagogical decision maker.

Reads the Student Model (list of TopicMastery dicts) and returns an
AdaptiveDecision: what to teach next and at what difficulty.

Rules (in priority order):
  1. accuracy < 0.5 AND attempts >= 3  → go to prerequisite topic
  2. hint_usage_rate > 0.7             → repeat topic with more examples (easier)
  3. accuracy < 0.6  OR als < 0.4     → repeat topic at same/lower difficulty
  4. accuracy > 0.9 AND als > 0.8     → increase difficulty or move to next topic
  5. default                           → continue current topic at same difficulty
"""

from dataclasses import dataclass
from analytics.calibration import difficulty_adjustment, calibration_label


# Simplified prerequisite map for English grammar topics.
# Key: topic → list of topics that should be mastered first.
PREREQUISITES: dict[str, list[str]] = {
    "Present Perfect": ["Past Simple", "Past Participle"],
    "Past Perfect": ["Past Simple", "Present Perfect"],
    "Future Perfect": ["Present Perfect", "Future Simple"],
    "Passive Voice": ["Past Simple", "Past Participle"],
    "Conditional Type 2": ["Past Simple"],
    "Conditional Type 3": ["Past Perfect"],
    "Reported Speech": ["Present Simple", "Past Simple"],
    "Relative Clauses": ["Present Simple"],
}

_DIFFICULTY_UP: dict[str, str] = {"easy": "medium", "medium": "hard", "hard": "hard"}
_DIFFICULTY_DOWN: dict[str, str] = {"hard": "medium", "medium": "easy", "easy": "easy"}


@dataclass
class AdaptiveDecision:
    """Output of the Adaptive Engine for one student at one point in time."""

    action: str        # repeat | increase_difficulty | decrease_difficulty | prerequisite | next_topic | more_examples
    topic: str         # which topic to work on
    difficulty: str    # easy | medium | hard
    reason: str        # human-readable explanation
    mastery_score: float
    als_score: float
    calibration: str = "unknown"  # calibrated | overconfident | underconfident | unknown


def _pick_weakest(mastery_records: list[dict]) -> dict:
    """Return the record with the lowest als_score."""
    return min(mastery_records, key=lambda r: r["als_score"])


def _find_unmastered_prerequisite(topic: str, mastery_map: dict[str, dict]) -> str | None:
    """Return the first prerequisite of *topic* whose mastery < 0.6, or None."""
    for prereq in PREREQUISITES.get(topic, []):
        rec = mastery_map.get(prereq)
        if rec is None or rec["mastery_score"] < 0.6:
            return prereq
    return None


def _current_difficulty(record: dict) -> str:
    """Infer current difficulty from average time and accuracy heuristic."""
    als = record["als_score"]
    if als >= 0.75:
        return "medium"
    if als >= 0.5:
        return "easy"
    return "easy"


def decide(mastery_records: list[dict], current_topic: str | None = None) -> AdaptiveDecision:
    """Compute the next pedagogical action for a student.

    Parameters
    ----------
    mastery_records : list[dict]
        All TopicMastery dicts for this student (from GET /analytics/student-model).
    current_topic : str or None
        The topic the student is currently working on.
        If None, the engine picks the weakest topic.

    Returns
    -------
    AdaptiveDecision
        Structured decision with action, topic, difficulty, and reason.
    """
    if not mastery_records:
        return AdaptiveDecision(
            action="next_topic",
            topic=current_topic or "Present Simple",
            difficulty="easy",
            reason="No learning history yet — start with the basics.",
            mastery_score=0.0,
            als_score=0.0,
        )

    mastery_map = {r["topic"]: r for r in mastery_records}

    # Determine which record to evaluate
    if current_topic and current_topic in mastery_map:
        record = mastery_map[current_topic]
    else:
        record = _pick_weakest(mastery_records)
        current_topic = record["topic"]

    accuracy = record["accuracy"]
    als = record["als_score"]
    hint_rate = record["hint_usage_rate"] or 0.0
    attempts = record["total_attempts"]
    mastery = record["mastery_score"]
    difficulty = _current_difficulty(record)

    # Calibration — adjust difficulty based on confidence accuracy
    calib = record.get("calibration") or {}
    conf_bias = calib.get("confidence_bias")
    calib_nudge = difficulty_adjustment(conf_bias)
    calib_str = calibration_label(conf_bias)

    # Rule 1: Too many failed attempts → unblock with prerequisite
    if attempts >= 3 and accuracy < 0.5:
        prereq = _find_unmastered_prerequisite(current_topic, mastery_map)
        if prereq:
            return AdaptiveDecision(
                action="prerequisite",
                topic=prereq,
                difficulty="easy",
                reason=f"Accuracy {accuracy:.0%} after {attempts} attempts on '{current_topic}'. "
                       f"Return to prerequisite '{prereq}' first.",
                mastery_score=mastery,
                als_score=als,
                calibration=calib_str,
            )

    # Rule 2: Too many hints → more examples, easier
    if hint_rate > 0.7:
        return AdaptiveDecision(
            action="more_examples",
            topic=current_topic,
            difficulty=_DIFFICULTY_DOWN[difficulty],
            reason=f"Hints used in {hint_rate:.0%} of attempts. "
                   "Provide more worked examples before exercises.",
            mastery_score=mastery,
            als_score=als,
            calibration=calib_str,
        )

    # Rule 3: Low accuracy or low ALS → repeat
    if accuracy < 0.6 or als < 0.4:
        return AdaptiveDecision(
            action="repeat",
            topic=current_topic,
            difficulty=_DIFFICULTY_DOWN[difficulty],
            reason=f"Accuracy {accuracy:.0%}, ALS {als:.2f}. "
                   "Repeat the topic at a lower difficulty.",
            mastery_score=mastery,
            als_score=als,
            calibration=calib_str,
        )

    # Rule 4: High accuracy and high ALS → level up or next topic
    if accuracy > 0.9 and als > 0.8:
        if difficulty != "hard":
            # Underconfident student: stay one more round at current level
            if calib_nudge < 0:
                return AdaptiveDecision(
                    action="continue",
                    topic=current_topic,
                    difficulty=difficulty,
                    reason=f"Accuracy {accuracy:.0%}, ALS {als:.2f}. "
                           f"Student is {calib_str} — reinforcing current level before advancing.",
                    mastery_score=mastery,
                    als_score=als,
                    calibration=calib_str,
                )
            return AdaptiveDecision(
                action="increase_difficulty",
                topic=current_topic,
                difficulty=_DIFFICULTY_UP[difficulty],
                reason=f"Accuracy {accuracy:.0%}, ALS {als:.2f}. "
                       "Student is ready for a harder challenge.",
                mastery_score=mastery,
                als_score=als,
                calibration=calib_str,
            )
        # Already at hard → find next weakest topic
        others = [r for r in mastery_records if r["topic"] != current_topic]
        if others:
            next_rec = _pick_weakest(others)
            return AdaptiveDecision(
                action="next_topic",
                topic=next_rec["topic"],
                difficulty=_current_difficulty(next_rec),
                reason=f"'{current_topic}' is mastered at hard level. "
                       f"Move to '{next_rec['topic']}' (ALS {next_rec['als_score']:.2f}).",
                mastery_score=next_rec["mastery_score"],
                als_score=next_rec["als_score"],
                calibration=calib_str,
            )

    # Rule 5: Default — continue; overconfident students get a harder nudge
    nudged_difficulty = difficulty
    nudge_note = ""
    if calib_nudge > 0 and difficulty != "hard":
        nudged_difficulty = _DIFFICULTY_UP[difficulty]
        nudge_note = f" Calibration: {calib_str} — nudging difficulty up."
    elif calib_nudge < 0 and difficulty != "easy":
        nudged_difficulty = _DIFFICULTY_DOWN[difficulty]
        nudge_note = f" Calibration: {calib_str} — easing difficulty to build confidence."

    return AdaptiveDecision(
        action="continue",
        topic=current_topic,
        difficulty=nudged_difficulty,
        reason=f"Accuracy {accuracy:.0%}, ALS {als:.2f}. Continue at the current level.{nudge_note}",
        mastery_score=mastery,
        als_score=als,
        calibration=calib_str,
    )
