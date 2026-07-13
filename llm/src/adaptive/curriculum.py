"""Curriculum Planner — Stage 7.

Builds a personalized multi-lesson study plan using:
  1. Prerequisite DAG  — determines valid learning order (topological sort)
  2. ZPD classification — groups topics by student readiness
  3. Lesson assignment  — packs topics into lessons by priority

ZPD zones (based on BKT P(know)):
  mastered   : p_know >= 0.90  → skip
  in_progress: 0.30 <= p_know < 0.90  → prioritize first
  ready      : p_know < 0.30 AND all prerequisites mastered  → can start
  blocked    : one or more prerequisites not mastered  → defer
  new        : never studied, prerequisites satisfied  → same as ready
"""

from dataclasses import dataclass, field
from collections import deque

# ── Prerequisite graph ────────────────────────────────────────────────────────
# Key: topic → topics that must be mastered (p_know >= 0.6) before starting.
# A topic not listed here has no prerequisites (A1 base topics).
TOPIC_GRAPH: dict[str, list[str]] = {
    # A2
    "Past Continuous":          ["Past Simple"],
    "Future Simple":            ["Present Simple"],
    "Present Perfect":          ["Past Simple"],
    "Adjectives and Adverbs":   ["Present Simple"],
    "Comparatives":             ["Adjectives and Adverbs"],
    "Prepositions":             ["Present Simple"],

    # B1
    "Past Perfect":             ["Past Simple", "Present Perfect"],
    "Future Continuous":        ["Present Continuous", "Future Simple"],
    "Future Perfect":           ["Future Simple", "Present Perfect"],
    "Modal Verbs":              ["Present Simple"],
    "Conditional Type 1":       ["Present Simple", "Future Simple"],
    "Passive Voice":            ["Past Simple"],
    "Reported Speech":          ["Present Simple", "Past Simple"],
    "Relative Clauses":         ["Present Simple"],

    # B2
    "Past Perfect Continuous":  ["Past Continuous", "Past Perfect"],
    "Conditional Type 2":       ["Past Simple", "Modal Verbs"],
    "Conditional Type 3":       ["Past Perfect", "Modal Verbs"],
    "Mixed Conditionals":       ["Conditional Type 2", "Conditional Type 3"],

    # C1
    "Subjunctive":              ["Conditional Type 2", "Conditional Type 3"],
    "Inversion":                ["Present Simple", "Past Simple"],
    "Cleft Sentences":          ["Relative Clauses"],
    "Advanced Modals":          ["Modal Verbs"],
}

# Topics with no prerequisites (A1 base)
BASE_TOPICS: list[str] = [
    "Present Simple",
    "Present Continuous",
    "Past Simple",
    "Nouns and Articles",
    "Personal Pronouns",
]

# Full ordered topic list for reference
ALL_TOPICS: list[str] = BASE_TOPICS + list(TOPIC_GRAPH.keys())

# Mastery threshold for "prerequisite satisfied"
PREREQ_THRESHOLD: float = 0.6
MASTERY_THRESHOLD: float = 0.90
IN_PROGRESS_THRESHOLD: float = 0.30


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class TopicStatus:
    topic: str
    zone: str        # mastered | in_progress | ready | blocked | new
    p_know: float
    prerequisites: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)   # unmet prerequisites


@dataclass
class PlannedLesson:
    lesson_number: int
    topics: list[TopicStatus]


@dataclass
class CurriculumPlan:
    lessons: list[PlannedLesson]
    mastered: list[str]
    blocked: list[TopicStatus]
    summary: str


# ── Core algorithm ────────────────────────────────────────────────────────────

def _topological_sort(graph: dict[str, list[str]], all_topics: list[str]) -> list[str]:
    """Kahn's algorithm — returns topics in valid learning order."""
    in_degree: dict[str, int] = {t: 0 for t in all_topics}
    dependents: dict[str, list[str]] = {t: [] for t in all_topics}

    for topic, prereqs in graph.items():
        if topic not in in_degree:
            continue
        for p in prereqs:
            if p in in_degree:
                in_degree[topic] += 1
                dependents[p].append(topic)

    queue = deque(t for t in all_topics if in_degree[t] == 0)
    order: list[str] = []

    while queue:
        t = queue.popleft()
        order.append(t)
        for dep in dependents.get(t, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    # Append any remaining (cycles / unknown) at the end
    seen = set(order)
    for t in all_topics:
        if t not in seen:
            order.append(t)

    return order


def _classify(
    topic: str,
    p_know: float,
    mastery_map: dict[str, float],
) -> TopicStatus:
    """Assign a ZPD zone to a single topic."""
    prereqs = TOPIC_GRAPH.get(topic, [])
    blocking = [p for p in prereqs if mastery_map.get(p, 0.0) < PREREQ_THRESHOLD]

    if p_know >= MASTERY_THRESHOLD:
        zone = "mastered"
    elif p_know >= IN_PROGRESS_THRESHOLD:
        zone = "in_progress"
    elif blocking:
        zone = "blocked"
    else:
        zone = "ready" if p_know > 0 else "new"

    return TopicStatus(
        topic=topic,
        zone=zone,
        p_know=round(p_know, 4),
        prerequisites=prereqs,
        blocking=blocking,
    )


def build_plan(
    mastery_records: list[dict],
    num_lessons: int = 5,
    topics_per_lesson: int = 2,
) -> CurriculumPlan:
    """Generate a personalised curriculum plan.

    Parameters
    ----------
    mastery_records : list[dict]
        Student Model records from TopicMasteryRepository.get_by_project().
    num_lessons : int
        How many lessons to plan ahead.
    topics_per_lesson : int
        Max topics per lesson.

    Returns
    -------
    CurriculumPlan
        Ordered lessons, plus metadata about mastered and blocked topics.
    """
    # Build lookup: topic → p_know (default 0.0 for unknown)
    mastery_map: dict[str, float] = {}
    for r in mastery_records:
        bkt = r.get("bkt") or {}
        p_know = bkt.get("p_know") or r.get("mastery_score") or 0.0
        mastery_map[r["topic"]] = float(p_know)

    # Topological order covers all known topics
    known_topics = list(set(ALL_TOPICS) | set(mastery_map.keys()))
    topo_order = _topological_sort(TOPIC_GRAPH, known_topics)

    # Classify every topic
    statuses: list[TopicStatus] = []
    for topic in topo_order:
        p_know = mastery_map.get(topic, 0.0)
        statuses.append(_classify(topic, p_know, mastery_map))

    # Separate by zone
    mastered = [s.topic for s in statuses if s.zone == "mastered"]
    actionable = [
        s for s in statuses
        if s.zone in ("in_progress", "ready", "new")
    ]
    blocked = [s for s in statuses if s.zone == "blocked"]

    # Priority: in_progress first, then new/ready (topo order already respected)
    priority_order = (
        [s for s in actionable if s.zone == "in_progress"]
        + [s for s in actionable if s.zone in ("ready", "new")]
    )

    # Pack into lessons
    slots_total = num_lessons * topics_per_lesson
    to_plan = priority_order[:slots_total]

    lessons: list[PlannedLesson] = []
    for i in range(num_lessons):
        chunk = to_plan[i * topics_per_lesson : (i + 1) * topics_per_lesson]
        if not chunk:
            break
        lessons.append(PlannedLesson(lesson_number=i + 1, topics=chunk))

    summary_parts = []
    in_prog_count = sum(1 for s in statuses if s.zone == "in_progress")
    ready_count = sum(1 for s in statuses if s.zone in ("ready", "new"))
    if in_prog_count:
        summary_parts.append(f"{in_prog_count} topic(s) in progress")
    if ready_count:
        summary_parts.append(f"{ready_count} ready to start")
    if mastered:
        summary_parts.append(f"{len(mastered)} mastered")
    if blocked:
        summary_parts.append(f"{len(blocked)} blocked by prerequisites")

    return CurriculumPlan(
        lessons=lessons,
        mastered=mastered,
        blocked=blocked,
        summary=", ".join(summary_parts) or "No data yet — start learning!",
    )
