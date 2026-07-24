"""Epic 8, Task 8.1 — measure per-stage chat latency across representative queries.

Run: uv run python scripts/measure_chat_latency.py [N]

Instruments the graph externally via astream_events' own on_chain_start/end
timestamps for the classify/route/model nodes, plus the first
on_chat_model_stream event for time-to-first-token — no changes to
chat/graph.py needed. Aggregates mean/median/min/max across N representative
queries spanning all four classifier intents (explanation/exercise/example/chat).

Uses synthetic project/chat/user ids (no DB rows exist for them) — classify's
topic_mastery lookup just returns an empty list for an unknown project_id, so
the Adaptive Engine takes its "no history yet" default path. That's a fair
baseline for pipeline-mechanics latency; a real student's history would add
one more DB round-trip inside classify, not change route/model timing.
"""

import asyncio
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_core.messages import HumanMessage  # noqa: E402

from chat.graph import build_tutor_graph  # noqa: E402
from chat.state import TutorRuntimeContext  # noqa: E402
from schemas import ProjectContext  # noqa: E402

QUERIES = [
    # explanation
    "объясни present perfect",
    "как отличить past simple от present perfect",
    "расскажи про пассивный залог",
    "что такое conditional type 2",
    "объясни разницу между since и for",
    # exercise
    "дай мне упражнение на present continuous",
    "хочу попрактиковаться в неправильных глаголах",
    "сделай задание на артикли",
    "дай упражнение на предлоги времени",
    "составь тест на модальные глаголы",
    # example
    "приведи примеры использования present perfect continuous",
    "покажи примеры предложений с would",
    "дай примеры фразовых глаголов с get",
    "приведи примеры вопросительных предложений в past simple",
    "покажи примеры употребления used to",
    # chat
    "привет, как дела",
    "спасибо за помощь",
    "что ты умеешь",
    "с чего лучше начать изучение английского",
    "как часто нужно повторять слова",
    # mixed / real-world phrasing (ambiguous intent, low-confidence path)
    "не понимаю когда использовать present perfect, а когда past simple",
    "почему тут used to, а не would",
    "объясни как строится вопрос в present perfect",
    "дай практику по теме reported speech",
]

STAGE_NODES = ("classify", "route", "model")


async def measure_one(graph, query: str) -> dict:
    ctx = TutorRuntimeContext(
        chat_id=f"bench-{uuid4()}",
        project_id=f"bench-{uuid4()}",
        user_id=uuid4(),
        current_user_message=HumanMessage(content=query),
        project=ProjectContext(
            student_name="Bench Student",
            student_level="B1",
            description="",
            existing_vocabulary=[],
            existing_topics=[],
        ),
    )

    t0 = time.perf_counter()
    stage_totals = dict.fromkeys(STAGE_NODES, 0.0)
    node_starts: dict[str, float] = {}
    first_token_t: float | None = None
    tool_calls = 0

    async for event in graph.astream_events({"messages": []}, context=ctx, version="v2"):
        kind = event["event"]
        name = event.get("name")
        now = time.perf_counter()

        if kind == "on_chain_start" and name in STAGE_NODES:
            node_starts[name] = now
        elif kind == "on_chain_end" and name in STAGE_NODES and name in node_starts:
            stage_totals[name] += now - node_starts.pop(name)
        elif kind == "on_chat_model_stream" and first_token_t is None:
            first_token_t = now
        elif kind == "on_tool_start":
            tool_calls += 1

    t_end = time.perf_counter()

    return {
        "query": query,
        "classify_s": stage_totals["classify"],
        "route_s": stage_totals["route"],
        "ttft_s": (first_token_t - t0) if first_token_t else None,
        "model_s": stage_totals["model"],
        "total_s": t_end - t0,
        "tool_calls": tool_calls,
    }


def summarize(label: str, values: list[float]) -> None:
    if not values:
        print(f"  {label}: no data")
        return
    print(f"  {label}: mean={statistics.mean(values):.2f}s median={statistics.median(values):.2f}s "
          f"min={min(values):.2f}s max={max(values):.2f}s (n={len(values)})")


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(QUERIES)
    queries = (QUERIES * ((n // len(QUERIES)) + 1))[:n]

    graph = build_tutor_graph()
    results = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q!r}...")
        r = await measure_one(graph, q)
        results.append(r)
        ttft = f"{r['ttft_s']:.2f}s" if r["ttft_s"] is not None else "n/a"
        print(f"    classify={r['classify_s']:.2f}s route={r['route_s']:.2f}s "
              f"ttft={ttft} model_total={r['model_s']:.2f}s total={r['total_s']:.2f}s "
              f"tool_calls={r['tool_calls']}")

    print(f"\n=== Summary across {len(results)} queries ===")
    summarize("classify", [r["classify_s"] for r in results])
    summarize("route (RAG retrieval, only turns that queried it)", [r["route_s"] for r in results if r["route_s"] > 0])
    summarize("time-to-first-token", [r["ttft_s"] for r in results if r["ttft_s"] is not None])
    summarize("model node total (incl. tool loop)", [r["model_s"] for r in results])
    summarize("full turn total", [r["total_s"] for r in results])


if __name__ == "__main__":
    asyncio.run(main())
