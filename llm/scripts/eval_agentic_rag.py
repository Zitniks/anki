"""Agentic RAG Этап 5 — compare router branch vs agentic branch on both
quality and latency, with and without settings.AGENTIC_RAG_ENABLED.

Run: uv run python scripts/eval_agentic_rag.py [N]

No pre-existing eval dataset/script was found in this repo copy despite the
task assuming one exists (analytics/embeddings.py's docstring references a
"scripts/eval_rag.py" and a "130-query eval set" from when embeddings were
switched — neither the script nor the labeled dataset are present in this
`ankis/llm` mirror; likely never synced over from adaptive-learning-repetitor).
So this script builds its own small representative query set (reusing
measure_chat_latency.py's 24 queries) and computes what CAN be measured
without labeled ground truth: latency percentiles, real LLM-judge Faithfulness/
Relevancy scores (settings.llm_cheap, same structured-output pattern as
chat/intent.py), and the four new agentic-specific metrics from the task spec.

Recall@5 needs a labeled "correct docs per query" set that doesn't exist here
— reported as N/A with the reason, not faked. See the printed report for the
full honesty caveat this run's corpus size implies.
"""

import asyncio
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from chat.graph import build_tutor_graph  # noqa: E402
from chat.search_tools import _SEARCH_TOOL_NAMES  # noqa: E402
from chat.state import TutorRuntimeContext  # noqa: E402
from schemas import ProjectContext  # noqa: E402
from settings import settings  # noqa: E402

# Same seeded Anki-side user_id as Этап 1's verification (3 rows: materials/
# example_bank/knowledge_docs, all "Present Perfect") — real corpus hits are
# only possible for queries that actually match that topic; everything else
# is a legitimate zero-recall case given this tiny local corpus, not a bug.
SEEDED_USER_ID = "49b2ef00-aa88-42cf-8e0a-9927e6503ce9"

EVAL_QUERIES = [
    {"query": "объясни present perfect", "educational": True},
    {"query": "как отличить past simple от present perfect", "educational": True},
    {"query": "расскажи про пассивный залог", "educational": True},
    {"query": "что такое conditional type 2", "educational": True},
    {"query": "дай мне упражнение на present continuous", "educational": True},
    {"query": "хочу попрактиковаться в неправильных глаголах", "educational": True},
    {"query": "приведи примеры использования present perfect continuous", "educational": True},
    {"query": "покажи примеры предложений с would", "educational": True},
    {"query": "привет, как дела", "educational": False},
    {"query": "спасибо за помощь", "educational": False},
    {"query": "что ты умеешь", "educational": False},
    {"query": "не понимаю когда использовать present perfect, а когда past simple", "educational": True},
    {"query": "в чём разница между present perfect и past simple, и дай упражнение на эту тему", "educational": True},
    {"query": "объясни как строится вопрос в present perfect", "educational": True},
]


class QualityJudgment(BaseModel):
    faithfulness: float = Field(ge=0, le=1, description=(
        "Насколько ответ подтверждается ТОЛЬКО предоставленным контекстом (0 — полностью выдуман "
        "или противоречит контексту / контекста не было и ответ не признаёт этого, 1 — каждое "
        "утверждение прослеживается к контексту, либо контекста не требовалось и ответ этого не выдумал)."))
    relevancy: float = Field(ge=0, le=1, description=(
        "Насколько ответ релевантен и по существу отвечает на вопрос студента (0 — не по теме, "
        "1 — прямо и по существу отвечает)."))


_judge = settings.llm_cheap.with_structured_output(QualityJudgment, method="function_calling")


async def judge(query: str, context: str, answer: str) -> QualityJudgment:
    prompt = (
        "Ты оцениваешь ответ AI-репетитора студенту.\n\n"
        f"Вопрос студента: {query}\n\n"
        f"Контекст, доступный AI (пусто, если поиск не делался или ничего не нашёл):\n{context or '(пусто)'}\n\n"
        f"Ответ AI: {answer}\n\n"
        "Оцени faithfulness (не выдумал ли AI факты сверх контекста/своих обоснованных общих знаний "
        "о грамматике английского) и relevancy (отвечает ли по существу на вопрос).")
    return await _judge.ainvoke(prompt)


def make_ctx(query: str) -> TutorRuntimeContext:
    return TutorRuntimeContext(
        chat_id=f"eval-{uuid4()}", project_id=f"eval-{uuid4()}", user_id=SEEDED_USER_ID,
        current_user_message=HumanMessage(content=query),
        project=ProjectContext(
            student_name="Eval Student", student_level="B1", description="",
            existing_vocabulary=[], existing_topics=[],
        ),
    )


async def run_one(graph, item: dict) -> dict:
    query = item["query"]
    ctx = make_ctx(query)

    t0 = time.perf_counter()
    ttft: float | None = None
    input_tokens = 0
    output_tokens = 0
    final_output: dict | None = None

    async for event in graph.astream_events({"messages": []}, context=ctx, version="v2"):
        kind = event["event"]
        if kind == "on_chat_model_stream" and ttft is None:
            ttft = time.perf_counter() - t0
        elif kind == "on_chat_model_end":
            usage = getattr(event["data"].get("output"), "usage_metadata", None)
            if usage:
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
        elif kind == "on_chain_end" and event.get("name") == "LangGraph":
            final_output = event["data"].get("output")

    total_s = time.perf_counter() - t0
    messages = (final_output or {}).get("messages", [])
    final_answer = next((m.content for m in reversed(messages) if isinstance(m, AIMessage) and m.content), "")

    # Context actually available to the model this turn — router branch: the
    # SystemMessage _route() injects; agentic branch: every search-tool
    # ToolMessage (real hits AND limit/dedup stubs, doesn't matter for judging
    # since a stub means "no new context", which the judge can see for itself).
    context_parts = []
    for m in messages:
        if isinstance(m, SystemMessage) and "Retrieved Context" in str(m.content):
            context_parts.append(m.content)
        elif isinstance(m, SystemMessage) and "обязательного поиска" in str(m.content):
            context_parts.append(m.content)
        elif isinstance(m, ToolMessage) and getattr(m, "name", None) in _SEARCH_TOOL_NAMES:
            context_parts.append(m.content)
    context_text = "\n\n".join(context_parts)

    searched = bool(context_parts)
    corpora_used = (final_output or {}).get("corpora_used") or set()
    search_calls = (final_output or {}).get("search_calls", 0)
    route_decision = (final_output or {}).get("route_decision") or {}
    if not settings.AGENTIC_RAG_ENABLED:
        # Router branch has no search_calls counter — derive an equivalent
        # from route_decision so the "share without search" metric is
        # comparable across both branches.
        searched = route_decision.get("mode") not in (None, "none", "refuse") and "Retrieved Context" in context_text
        search_calls = 1 if searched else 0
        if route_decision.get("mode") == "ensemble":
            corpora_used = {"exercise", "explanation", "example"}
        elif route_decision.get("retrievers"):
            corpora_used = set(route_decision["retrievers"])

    q = await judge(query, context_text, final_answer)

    return {
        "query": query,
        "educational": item["educational"],
        "total_s": total_s,
        "ttft_s": ttft,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "searched": searched,
        "search_calls": search_calls,
        "corpora_used": corpora_used,
        "faithfulness": q.faithfulness,
        "relevancy": q.relevancy,
    }


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = min(len(s) - 1, int(round(p * (len(s) - 1))))
    return s[idx]


async def run_branch(label: str, enabled: bool, n: int) -> list[dict]:
    settings.AGENTIC_RAG_ENABLED = enabled
    graph = build_tutor_graph()
    queries = (EVAL_QUERIES * ((n // len(EVAL_QUERIES)) + 1))[:n]
    results = []
    print(f"\n--- {label} (AGENTIC_RAG_ENABLED={enabled}) ---")
    for i, item in enumerate(queries, 1):
        r = await run_one(graph, item)
        results.append(r)
        print(f"[{i}/{len(queries)}] {item['query']!r} -> total={r['total_s']:.2f}s "
              f"searched={r['searched']} search_calls={r['search_calls']} "
              f"corpora={sorted(r['corpora_used'])} faith={r['faithfulness']:.2f} "
              f"rel={r['relevancy']:.2f}")
    return results


def summarize(label: str, results: list[dict]) -> dict:
    totals = [r["total_s"] for r in results]
    ttfts = [r["ttft_s"] for r in results if r["ttft_s"] is not None]
    faith = [r["faithfulness"] for r in results]
    rel = [r["relevancy"] for r in results]
    edu = [r for r in results if r["educational"]]
    edu_no_search = [r for r in edu if not r["searched"]]
    multi_corpus = [r for r in results if len(r["corpora_used"]) > 1]
    avg_search_calls = statistics.mean([r["search_calls"] for r in edu]) if edu else 0.0
    total_tokens = sum(r["input_tokens"] + r["output_tokens"] for r in results)

    summary = {
        "label": label,
        "n": len(results),
        "faithfulness_mean": statistics.mean(faith) if faith else float("nan"),
        "relevancy_mean": statistics.mean(rel) if rel else float("nan"),
        "recall_at_5": None,  # see honesty caveat in report
        "latency_p50": pct(totals, 0.50),
        "latency_p95": pct(totals, 0.95),
        "ttft_p50": pct(ttfts, 0.50) if ttfts else float("nan"),
        "pct_educational_no_search": (len(edu_no_search) / len(edu) * 100) if edu else float("nan"),
        "avg_search_calls_per_educational_query": avg_search_calls,
        "pct_multi_corpus": (len(multi_corpus) / len(results) * 100) if results else float("nan"),
        "total_tokens": total_tokens,
        "tokens_per_query": total_tokens / len(results) if results else 0,
    }
    return summary


def print_report(router_summary: dict, agentic_summary: dict) -> None:
    print("\n" + "=" * 78)
    print("ИТОГОВАЯ ТАБЛИЦА — router (флаг выкл.) vs agentic (флаг вкл.)")
    print("=" * 78)
    rows = [
        ("N запросов", "n", "{}"),
        ("Faithfulness (LLM-judge, не RAGAS)", "faithfulness_mean", "{:.2f}"),
        ("Answer Relevancy (LLM-judge)", "relevancy_mean", "{:.2f}"),
        ("Recall@5", "recall_at_5", "{}"),
        ("Латентность p50, с", "latency_p50", "{:.2f}"),
        ("Латентность p95, с", "latency_p95", "{:.2f}"),
        ("TTFT p50, с", "ttft_p50", "{:.2f}"),
        ("% учебных запросов БЕЗ поиска", "pct_educational_no_search", "{:.1f}%"),
        ("Среднее поисков/учебный запрос", "avg_search_calls_per_educational_query", "{:.2f}"),
        ("% запросов, >1 корпус", "pct_multi_corpus", "{:.1f}%"),
        ("Токенов/запрос (input+output)", "tokens_per_query", "{:.0f}"),
    ]
    label_w = max(len(r[0]) for r in rows)
    print(f"{'Метрика':<{label_w}}  {'router':>12}  {'agentic':>12}")
    for name, key, fmt in rows:
        rv = router_summary[key]
        av = agentic_summary[key]
        rv_s = fmt.format(rv) if rv is not None else "N/A"
        av_s = fmt.format(av) if av is not None else "N/A"
        print(f"{name:<{label_w}}  {rv_s:>12}  {av_s:>12}")

    print("\nПороги из ТЗ и честный статус:")
    print(f"  Faithfulness >= 0.85: router={'PASS' if router_summary['faithfulness_mean'] >= 0.85 else 'FAIL'} "
          f"agentic={'PASS' if agentic_summary['faithfulness_mean'] >= 0.85 else 'FAIL'} "
          f"(LLM-judge на {router_summary['n']} запросах, НЕ формальный RAGAS-eval)")
    print(f"  Answer Relevancy >= 0.79: router={'PASS' if router_summary['relevancy_mean'] >= 0.79 else 'FAIL'} "
          f"agentic={'PASS' if agentic_summary['relevancy_mean'] >= 0.79 else 'FAIL'}")
    print("  Recall@5 >= 87%: N/A ОБЕ ветки — нет размеченного датасета (\"какие документы правильные "
          "для запроса X\") ни в этом репозитории, ни в локальной llm-db. analytics/embeddings.py "
          "ссылается на историческую цифру recall@5=76.9% с отдельным 130-запросным eval-датасетом, "
          "которого нет в этой копии `ankis/llm` (не засинкано из adaptive-learning-repetitor). Корпус "
          "в этой среде — 3 строки, засеянные вручную в Этапе 1 (все про Present Perfect), недостаточно "
          "для честного Recall@5 в принципе.")
    print(f"  Латентность p50 <= 2.5s: router={'PASS' if router_summary['latency_p50'] <= 2.5 else 'FAIL'} "
          f"agentic={'PASS' if agentic_summary['latency_p50'] <= 2.5 else 'FAIL'}")
    print(f"  Латентность p95 <= 5s: router={'PASS' if router_summary['latency_p95'] <= 5 else 'FAIL'} "
          f"agentic={'PASS' if agentic_summary['latency_p95'] <= 5 else 'FAIL'}")
    print(f"  Доля учебных без поиска <= 5%: agentic="
          f"{'PASS' if agentic_summary['pct_educational_no_search'] <= 5 else 'FAIL'}")
    print(f"  Среднее поисков 1.2-1.5: agentic="
          f"{'PASS' if 1.2 <= agentic_summary['avg_search_calls_per_educational_query'] <= 1.5 else 'FAIL'}")
    print(f"  Доля >1 корпуса (не близко к 0): agentic="
          f"{'OK' if agentic_summary['pct_multi_corpus'] > 5 else 'БЛИЗКО К НУЛЮ — см. предупреждение в ТЗ'}")


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(EVAL_QUERIES)
    router_results = await run_branch("ROUTER", False, n)
    agentic_results = await run_branch("AGENTIC", True, n)
    router_summary = summarize("router", router_results)
    agentic_summary = summarize("agentic", agentic_results)
    print_report(router_summary, agentic_summary)


if __name__ == "__main__":
    asyncio.run(main())
