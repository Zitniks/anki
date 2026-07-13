"""Adaptive Learning Score (ALS) calculation and mastery update logic."""


def calculate_als(
    accuracy: float,
    time_seconds: float,
    avg_attempts: float,
    hint_rate: float,
    confidence: float,
    mastery: float,
) -> float:
    """Compute Adaptive Learning Score in [0.0, 1.0].

    ALS = weighted sum of six signals:
      accuracy (0.35), time (0.15), attempts (0.15),
      hints (0.15), confidence (0.10), mastery (0.10).

    Parameters
    ----------
    accuracy : float
        Fraction of correct answers for this topic (0.0–1.0).
    time_seconds : float
        Time spent on the last exercise in seconds.
        Ideal <= 30 s → 1.0; >= 120 s → 0.0.
    avg_attempts : float
        Average number of attempts per exercise.
        1 attempt → 1.0; 3+ attempts → 0.0.
    hint_rate : float
        Fraction of exercises where a hint was used (0.0–1.0).
    confidence : float
        User self-assessment normalised to 0.0–1.0.
    mastery : float
        Current topic mastery score (0.0–1.0).

    Returns
    -------
    float
        ALS rounded to 4 decimal places.
    """
    time_score = max(0.0, 1.0 - max(0.0, time_seconds - 30.0) / 90.0)
    attempts_score = max(0.0, 1.0 - (avg_attempts - 1.0) / 2.0)
    hints_score = 1.0 - hint_rate

    als = (
        0.35 * accuracy
        + 0.15 * time_score
        + 0.15 * attempts_score
        + 0.15 * hints_score
        + 0.10 * confidence
        + 0.10 * mastery
    )
    return round(min(1.0, max(0.0, als)), 4)


def update_mastery(current: float, correct: bool, weight: float = 0.3) -> float:
    """Update mastery score via exponential moving average.

    Parameters
    ----------
    current : float
        Current mastery score (0.0–1.0).
    correct : bool
        Whether the user answered correctly.
    weight : float, optional
        Learning rate; higher = faster adaptation (default 0.3).

    Returns
    -------
    float
        Updated mastery score (0.0–1.0), rounded to 4 decimal places.
    """
    signal = 1.0 if correct else 0.0
    return round(current * (1.0 - weight) + signal * weight, 4)
