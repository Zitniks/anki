"""Forgetting Curve (Ebbinghaus) — Extra Task.

Applies exponential decay to BKT P(know) when a topic hasn't been
practised for a while. Applied dynamically on read — never written back
to the database, so it doesn't corrupt historical data.

Formula:  p_know_decayed = p_know * exp(-decay_rate * days_idle)
          floored at DEFAULT_P_KNOW so a topic never resets completely.

Decay only activates after MIN_IDLE_DAYS of inactivity.
"""

import math
from datetime import datetime, timezone

# After how many idle days to start applying decay
MIN_IDLE_DAYS: float = 1.0

# Fraction of P(know) lost per idle day (5 % per day)
DECAY_RATE: float = 0.05

# P(know) floor — never drop below the BKT prior
P_KNOW_FLOOR: float = 0.10


def _days_idle(last_event_at: str | datetime | None) -> float:
    """Return number of days since last_event_at (UTC now − last event)."""
    if last_event_at is None:
        return 0.0
    if isinstance(last_event_at, str):
        # Strip trailing Z or offset for fromisoformat compat
        ts = last_event_at.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return 0.0
    else:
        dt = last_event_at

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
    return max(0.0, elapsed / 86400.0)


def apply(mastery_records: list[dict]) -> list[dict]:
    """Apply Ebbinghaus decay to a list of mastery dicts (in-place copy).

    Parameters
    ----------
    mastery_records : list[dict]
        Raw records from TopicMasteryRepository.get_by_project().

    Returns
    -------
    list[dict]
        Same records with decayed bkt.p_know and mastery_score.
        A 'forgetting_applied' flag is added when decay > 0.
    """
    result = []
    for rec in mastery_records:
        rec = dict(rec)  # shallow copy — don't mutate original
        bkt = dict(rec.get("bkt") or {})

        p_know = float(bkt.get("p_know") or rec.get("mastery_score") or 0.0)
        idle = _days_idle(rec.get("last_event_at"))

        if idle >= MIN_IDLE_DAYS and p_know > P_KNOW_FLOOR:
            decayed = p_know * math.exp(-DECAY_RATE * idle)
            decayed = round(max(P_KNOW_FLOOR, decayed), 4)
            decay_amount = round(p_know - decayed, 4)

            bkt["p_know"] = decayed
            bkt["forgetting_applied"] = True
            bkt["idle_days"] = round(idle, 1)
            bkt["decay_amount"] = decay_amount

            rec["mastery_score"] = decayed
            rec["bkt"] = bkt
        else:
            bkt["forgetting_applied"] = False
            bkt["idle_days"] = round(idle, 1)
            rec["bkt"] = bkt

        result.append(rec)
    return result
