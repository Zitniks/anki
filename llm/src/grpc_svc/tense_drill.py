"""Generates a mixed-tense translation drill: Russian sentences the student
must assign to one of several already-studied tenses and translate to English.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from grpc_svc.practice import _strip_html
from settings import settings


class DrillItem(BaseModel):
    sentence_ru: str = Field(description="A Russian sentence that clearly requires one specific tense to translate.")
    correct_tense: str = Field(description="Which of the given topic titles this sentence requires.")
    reference_translation: str = Field(description="A natural English translation using that tense.")


class DrillSet(BaseModel):
    items: list[DrillItem]


_drill_generator = settings.llm_cheap.with_structured_output(DrillSet, method="function_calling")

_CONTROL_CHARS = "".join(chr(c) for c in range(0x20) if c not in (0x09, 0x0A, 0x0D))
_CONTROL_TABLE = str.maketrans("", "", _CONTROL_CHARS)


def _clean(text: str) -> str:
    return text.translate(_CONTROL_TABLE).strip()


def build_drill_prompt(topics: list[dict[str, str]], level: str, count: int) -> str:
    topics_block = "\n\n".join(
        f"### {t['title']} ({t.get('level', '')})\n{_strip_html(t.get('content', ''))[:1500]}" for t in topics
    )
    titles = ", ".join(f'"{t["title"]}"' for t in topics)
    return (
        f"You are an English tutor. Below are grammar topics (tenses) the student has already studied "
        f"(CEFR level {level}).\n"
        f"Write exactly {count} short Russian sentences, MIXED across these tenses ({titles}), each sentence "
        "clearly requiring exactly ONE of them to translate correctly (don't hint at the tense name in the "
        "sentence itself) — try to use each tense at least once if count allows.\n"
        "For each sentence give: the Russian sentence, which tense title it requires (must exactly match one "
        "of the titles above), and a natural reference English translation using that tense.\n"
        f"Fresh variant token: {time.time_ns()}.\n"
        f"\nTopics:\n{topics_block}"
    )


async def generate_tense_drill(topics: list[dict[str, str]], level: str, count: int) -> dict[str, Any]:
    prompt = build_drill_prompt(topics, level or "B1", count)
    result: DrillSet = await _drill_generator.ainvoke(prompt)
    items = [
        {
            "sentence_ru": _clean(i.sentence_ru),
            "correct_tense": _clean(i.correct_tense),
            "reference_translation": _clean(i.reference_translation),
        }
        for i in result.items
    ]
    return {"items": items}
