"""Reflection Engine — Stage 9.

Generates a template-based progress report from the Student Model.
No LLM — pure data → text transformation.

Report sections:
  overview    — high-level numbers (topics studied, mastery rate, accuracy)
  strengths   — topics with p_know >= 0.70
  weaknesses  — topics with p_know < 0.35 and at least 1 attempt
  in_progress — topics between 0.35 and 0.70
  patterns    — learning behaviour (speed, hint usage, confidence)
  next_steps  — what to focus on next (top 3 weakest non-mastered topics)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


# ── Thresholds ────────────────────────────────────────────────────────────────
_STRONG: float = 0.70
_WEAK: float = 0.35
_MASTERED: float = 0.90


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ReportSection:
    title: str
    text: str


@dataclass
class ProgressReport:
    generated_at: str
    summary: str
    sections: list[ReportSection]
    stats: dict = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _p_know(record: dict) -> float:
    bkt = record.get("bkt") or {}
    return float(bkt.get("p_know") or record.get("mastery_score") or 0.0)


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _fmt_topic(record: dict) -> str:
    p = _p_know(record)
    acc = record.get("accuracy") or 0.0
    attempts = record.get("total_attempts") or 0
    return f"  • {record['topic']}: mastery {_pct(p)}, accuracy {_pct(acc)} ({attempts} attempts)"


# ── Core ──────────────────────────────────────────────────────────────────────

def generate(mastery_records: list[dict]) -> ProgressReport:
    """Build a human-readable progress report from Student Model records.

    Parameters
    ----------
    mastery_records : list[dict]
        All TopicMastery dicts for one student (from GET /analytics/student-model).

    Returns
    -------
    ProgressReport
        Structured report with summary and named sections.
    """
    now = datetime.now(timezone.utc).isoformat()

    if not mastery_records:
        return ProgressReport(
            generated_at=now,
            summary="No learning activity recorded yet.",
            sections=[
                ReportSection(
                    title="Overview",
                    text="The student has not completed any exercises yet. "
                         "Start with Present Simple to build the foundation.",
                )
            ],
            stats={},
        )

    # ── Aggregate stats ──────────────────────────────────────────────────────
    total_topics = len(mastery_records)
    total_attempts = sum(r.get("total_attempts") or 0 for r in mastery_records)
    total_correct = sum(r.get("correct_attempts") or 0 for r in mastery_records)
    overall_accuracy = total_correct / total_attempts if total_attempts else 0.0

    p_knows = [_p_know(r) for r in mastery_records]
    avg_mastery = sum(p_knows) / len(p_knows)

    avg_als = sum(r.get("als_score") or 0.0 for r in mastery_records) / total_topics
    avg_time = sum(r.get("avg_time_seconds") or 0.0 for r in mastery_records) / total_topics
    avg_hints = sum(r.get("hint_usage_rate") or 0.0 for r in mastery_records) / total_topics

    mastered = [r for r in mastery_records if _p_know(r) >= _MASTERED]
    strong = [r for r in mastery_records if _STRONG <= _p_know(r) < _MASTERED]
    in_prog = [r for r in mastery_records if _WEAK <= _p_know(r) < _STRONG]
    weak = [r for r in mastery_records if _p_know(r) < _WEAK and (r.get("total_attempts") or 0) > 0]

    stats = {
        "topics_studied": total_topics,
        "total_attempts": total_attempts,
        "overall_accuracy": round(overall_accuracy, 3),
        "avg_mastery": round(avg_mastery, 3),
        "avg_als": round(avg_als, 3),
        "avg_time_seconds": round(avg_time, 1),
        "avg_hint_rate": round(avg_hints, 3),
        "mastered_count": len(mastered),
        "strong_count": len(strong),
        "in_progress_count": len(in_prog),
        "weak_count": len(weak),
    }

    # ── Section: Overview ────────────────────────────────────────────────────
    overview_lines = [
        f"Topics studied: {total_topics}",
        f"Total exercises: {total_attempts}",
        f"Overall accuracy: {_pct(overall_accuracy)}",
        f"Average mastery (BKT): {_pct(avg_mastery)}",
        f"Adaptive Learning Score: {avg_als:.2f} / 1.00",
        f"Mastered topics: {len(mastered)} / {total_topics}",
    ]
    sections = [ReportSection(title="Overview", text="\n".join(overview_lines))]

    # ── Section: Strengths ───────────────────────────────────────────────────
    strength_records = sorted(mastered + strong, key=_p_know, reverse=True)
    if strength_records:
        lines = ["Topics where you perform well:"]
        lines += [_fmt_topic(r) for r in strength_records]
        if len(mastered) > 0:
            lines.append(
                f"\n{len(mastered)} topic(s) fully mastered "
                "(P(know) ≥ 90%) — these won't appear in your study plan."
            )
        sections.append(ReportSection(title="Strengths", text="\n".join(lines)))
    else:
        sections.append(ReportSection(
            title="Strengths",
            text="No strong topics yet — keep practising! Mastery is built through repetition.",
        ))

    # ── Section: In Progress ─────────────────────────────────────────────────
    if in_prog:
        lines = ["Topics currently being learned (35%–70% mastery):"]
        lines += [_fmt_topic(r) for r in sorted(in_prog, key=_p_know)]
        sections.append(ReportSection(title="In Progress", text="\n".join(lines)))

    # ── Section: Weaknesses ──────────────────────────────────────────────────
    if weak:
        lines = ["Topics that need more attention (below 35% mastery):"]
        lines += [_fmt_topic(r) for r in sorted(weak, key=_p_know)]
        sections.append(ReportSection(title="Weaknesses", text="\n".join(lines)))

    # ── Section: Learning Patterns ───────────────────────────────────────────
    pattern_lines = []

    speed_label = (
        "fast" if avg_time < 25 else
        "average" if avg_time < 60 else
        "slow"
    )
    pattern_lines.append(f"Response speed: {avg_time:.0f}s per exercise ({speed_label})")

    if avg_hints > 0.5:
        pattern_lines.append(
            f"Hint usage: {_pct(avg_hints)} — high. "
            "Consider reviewing theory before attempting exercises."
        )
    elif avg_hints > 0.2:
        pattern_lines.append(f"Hint usage: {_pct(avg_hints)} — moderate.")
    else:
        pattern_lines.append(f"Hint usage: {_pct(avg_hints)} — low. Good independence!")

    als_label = (
        "excellent" if avg_als >= 0.80 else
        "good" if avg_als >= 0.65 else
        "needs improvement" if avg_als >= 0.45 else
        "low"
    )
    pattern_lines.append(f"Adaptive Learning Score: {avg_als:.2f} ({als_label})")

    sections.append(ReportSection(title="Learning Patterns", text="\n".join(pattern_lines)))

    # ── Section: Next Steps ──────────────────────────────────────────────────
    non_mastered = [r for r in mastery_records if _p_know(r) < _MASTERED]
    priorities = sorted(non_mastered, key=lambda r: _p_know(r))[:3]

    if priorities:
        lines = ["Recommended focus for your next sessions:"]
        for i, r in enumerate(priorities, 1):
            p = _p_know(r)
            bkt = r.get("bkt") or {}
            p_next = bkt.get("p_correct_next")
            hint = (
                f"predicted success rate {_pct(p_next)}" if p_next else
                "not yet attempted"
            )
            lines.append(f"  {i}. {r['topic']} (mastery {_pct(p)}, {hint})")
        sections.append(ReportSection(title="Next Steps", text="\n".join(lines)))

    # ── Summary sentence ─────────────────────────────────────────────────────
    if len(mastered) == total_topics:
        summary = f"Outstanding! All {total_topics} topics mastered."
    elif overall_accuracy >= 0.80:
        summary = (
            f"Strong performance: {_pct(overall_accuracy)} accuracy across {total_topics} topics, "
            f"{len(mastered)} mastered."
        )
    elif overall_accuracy >= 0.60:
        summary = (
            f"Good progress: {_pct(overall_accuracy)} accuracy, "
            f"{len(mastered)} topic(s) mastered out of {total_topics}."
        )
    else:
        summary = (
            f"Keep going: {_pct(overall_accuracy)} accuracy so far. "
            f"Focus on the weakest topics listed below."
        )

    return ProgressReport(
        generated_at=now,
        summary=summary,
        sections=sections,
        stats=stats,
    )
