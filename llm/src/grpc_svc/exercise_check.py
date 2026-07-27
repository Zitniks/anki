"""Check a student's typed answers for a theory-topic exercise against the
known answer key, grounded by the LLM (tolerates equivalent phrasings like
"she'd" vs "she had") — returns per-blank verdict + explanation on mistakes.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from settings import settings


class AnswerCheckItem(BaseModel):
    correct: bool = Field(description="Whether the student's answer is an acceptable match for the blank.")
    correct_answer: str = Field(description="The expected correct answer for this blank, from the answer key (in English).")
    explanation: str = Field(
        description=(
            "1-2 sentences IN RUSSIAN explaining the grammar rule when the student's answer is wrong "
            "(quote the English word/phrase itself in English inside the Russian sentence); "
            "empty string if correct."
        )
    )


class AnswerCheckResult(BaseModel):
    results: list[AnswerCheckItem]


_check_generator = settings.llm_cheap.with_structured_output(AnswerCheckResult, method="function_calling")

_CONTROL_CHARS = "".join(chr(c) for c in range(0x20) if c not in (0x09, 0x0A, 0x0D))
_CONTROL_TABLE = str.maketrans("", "", _CONTROL_CHARS)


def _clean(text: str) -> str:
    return text.translate(_CONTROL_TABLE).strip()


def build_check_prompt(exercise_context: str, answer_key: str, user_answers: list[str]) -> str:
    numbered_answers = "\n".join(f"{i + 1}. {a or '(пусто)'}" for i, a in enumerate(user_answers))
    return (
        "You are an English tutor checking a student's fill-in-the-blank exercise.\n"
        "The exercise text below has numbered blanks (___1___, ___2___, ...). The answer key gives the "
        "expected answer(s) per blank (blank 1's answer is usually shown inline in the exercise itself, "
        "so the key may start from blank 2).\n"
        "For each blank, decide if the student's answer is an acceptable match for the expected answer — "
        "accept equivalent phrasings (contractions vs full forms, minor spelling) but reject actual grammar "
        "mistakes. If wrong, write the explanation IN RUSSIAN (1-2 sentences) explaining the grammar rule, "
        "quoting the English word/phrase itself in English inside the Russian sentence; if correct, leave "
        "explanation empty. The student's own answer is written in Russian keyboard layout by mistake "
        "sometimes (e.g. 'фвы' instead of English letters) — always treat those as simply wrong, not as an "
        "attempt to answer in Russian.\n"
        f"Return exactly {len(user_answers)} results, in blank order.\n"
        f"Fresh variant token: {time.time_ns()}.\n"
        f"\nExercise text:\n{exercise_context}\n"
        f"\nAnswer key:\n{answer_key}\n"
        f"\nStudent's answers:\n{numbered_answers}"
    )


async def check_answers(exercise_context: str, answer_key: str, user_answers: list[str]) -> dict[str, Any]:
    prompt = build_check_prompt(exercise_context, answer_key, user_answers)
    result: AnswerCheckResult = await _check_generator.ainvoke(prompt)
    results = [
        {
            "correct": r.correct,
            "correct_answer": _clean(r.correct_answer),
            "explanation": _clean(r.explanation),
        }
        for r in result.results
    ]
    return {"results": results}
