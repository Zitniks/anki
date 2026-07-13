"""Confidence Calibration — Extra Task.

Measures how accurately a student estimates their own knowledge.

confidence_bias  = avg_reported_confidence - actual_accuracy
  > +0.2  → overconfident: student thinks they know more than they do
  < -0.2  → underconfident: student underestimates their ability
  ≈ 0     → well-calibrated

calibration_error = |confidence_bias|  (0 = perfect calibration)

Used by the Adaptive Engine to adjust difficulty:
  - Overconfident → push toward harder tasks sooner (don't trust "I know this")
  - Underconfident → hold at current level longer, give positive reinforcement
"""

# Bias thresholds for adjustment
OVERCONFIDENT_THRESHOLD: float = 0.20   # confidence >> accuracy
UNDERCONFIDENT_THRESHOLD: float = -0.20  # confidence << accuracy


def update_calibration(
    prev_avg_confidence: float | None,
    new_confidence: float,
    total_attempts: int,
    accuracy: float,
) -> tuple[float, float, float]:
    """Compute rolling confidence calibration metrics after a new event.

    Parameters
    ----------
    prev_avg_confidence : float or None
        Previous rolling average confidence (None if first attempt).
    new_confidence : float
        Student's self-reported confidence for this attempt (0.0–1.0).
    total_attempts : int
        Total attempts INCLUDING the current one.
    accuracy : float
        Current overall accuracy (correct / total) after this attempt.

    Returns
    -------
    tuple[float, float, float]
        (avg_confidence, confidence_bias, calibration_error)
    """
    if prev_avg_confidence is None or total_attempts <= 1:
        avg_confidence = new_confidence
    else:
        # Rolling average: blend previous average with new value
        prev_total = total_attempts - 1
        avg_confidence = (prev_avg_confidence * prev_total + new_confidence) / total_attempts

    avg_confidence = round(min(1.0, max(0.0, avg_confidence)), 4)
    confidence_bias = round(avg_confidence - accuracy, 4)
    calibration_error = round(abs(confidence_bias), 4)

    return avg_confidence, confidence_bias, calibration_error


def calibration_label(confidence_bias: float | None) -> str:
    """Return a human-readable calibration label."""
    if confidence_bias is None:
        return "unknown"
    if confidence_bias > OVERCONFIDENT_THRESHOLD:
        return "overconfident"
    if confidence_bias < UNDERCONFIDENT_THRESHOLD:
        return "underconfident"
    return "calibrated"


def difficulty_adjustment(confidence_bias: float | None) -> int:
    """Return a difficulty nudge based on calibration.

    Returns
    -------
    int
        +1 → push difficulty up (overconfident student needs reality check)
        -1 → hold difficulty down (underconfident needs confidence building)
         0 → no adjustment
    """
    if confidence_bias is None:
        return 0
    if confidence_bias > OVERCONFIDENT_THRESHOLD:
        return +1
    if confidence_bias < UNDERCONFIDENT_THRESHOLD:
        return -1
    return 0
