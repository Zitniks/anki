#!/usr/bin/env python3
"""Забирает дословный текст уроков грамматики с lingust.ru/english/grammar
и подставляет его в поле "html" соответствующих тем в back/theory_tenses.json.

Не трогает back/theory_tenses.md и back/scripts/gen_theory_json.py — они уже
разошлись с живым JSON и не являются источником для этого скрипта.

Запуск: python3 back/scripts/fetch_theory_content.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent.parent
THEORY_JSON = ROOT / "theory_tenses.json"

BASE_URL = "https://lingust.ru/english/grammar/lesson{n}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# lesson number(s) -> topic id. Two-part "continuation" lessons are merged
# into a single topic (verified by reading each lesson's real <h1>, not by
# assuming the lesson number matches the topic order).
LESSON_TO_TOPIC: dict[tuple[int, ...], str] = {
    (1,): "present-continuous",
    (2,): "present-simple",
    (3, 4): "present-simple-vs-continuous",
    (5,): "past-simple",
    (6,): "past-continuous",
    (7, 8): "present-perfect",
    (9,): "present-perfect-continuous",
    (10,): "present-perfect-continuous-vs-simple",
    (11, 12): "how-long-for-since",
    (13, 14): "present-perfect-vs-past-simple",
    (15,): "past-perfect",
    (16,): "past-perfect-continuous",
    (19,): "present-for-future",
    (20,): "be-going-to",
    (21, 22): "will-shall",
    (23,): "will-vs-going-to",
    (24,): "future-continuous-perfect",
}

ALL_LESSON_NUMBERS = sorted({n for nums in LESSON_TO_TOPIC for n in nums})


def fetch_lesson_html(n: int) -> str:
    req = urllib.request.Request(BASE_URL.format(n=n), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_answer_key_text(tag: Tag) -> str | None:
    """If this tag is just the answer-key tooltip icon, return its plain-text
    answer key (the tooltip's `<br>`-joined content, cleaned to plain text).
    """
    key_span = tag.find("span", attrs={"data-tooltips-content": True})
    if key_span is None:
        return None
    content = key_span.get("data-tooltips-content", "")
    text = re.sub(r"<br\s*/?>", " ", content)
    return re.sub(r"\s+", " ", text).strip()


def render_tag(tag: Tag) -> str:
    """Render a tag verbatim, dropping <img> tags — they point at lingust.ru's
    own relative paths, which we don't mirror, so they'd just render broken
    on our site.
    """
    for img in tag.find_all("img"):
        img.decompose()
    return str(tag)


def extract_lesson_body_html(html: str) -> tuple[str, str]:
    """Returns (h1_title, verbatim_html) for one lesson page."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.select_one(".com-content-article__body")
    if body is None:
        raise RuntimeError("article body not found")
    h1 = body.find("h1")
    h1_title = h1.get_text(" ", strip=True) if h1 else ""

    children = body.find_all(recursive=False)
    # Real lesson content starts at the first lettered section marker
    # (div.row.gbp > span.gb) — everything before it is repeated site
    # boilerplate (title recap, "Урок N", cross-links to other lessons).
    start = None
    for i, child in enumerate(children):
        if "gbp" in (child.get("class") or []):
            start = i
            break
    if start is None:
        raise RuntimeError(f"no section marker found for lesson with h1={h1_title!r}")

    parts: list[str] = []
    for child in children[start:]:
        classes = child.get("class") or []
        if child.name == "div" and "gbp" in classes:
            letter = child.get_text(strip=True)
            parts.append(f"<h3>{letter}</h3>")
            continue
        if child.name == "h4":
            parts.append(f'<h4>{child.get_text(strip=True)}</h4>')
            continue
        if child.name == "p" and not child.get_text(strip=True):
            # Likely just the answer-key tooltip icon (or a spacer paragraph)
            # sitting right after an <ol> — fold its text into that <ol>'s
            # data-answer-key attribute instead of rendering a visible reveal
            # link (the AI-checked exercises use this attribute directly).
            key_text = extract_answer_key_text(child)
            if key_text is not None and parts and parts[-1].startswith("<ol"):
                ol_soup = BeautifulSoup(parts[-1], "lxml")
                ol_soup.ol["data-answer-key"] = key_text
                parts[-1] = str(ol_soup.ol)
            continue
        parts.append(render_tag(child))

    return h1_title, "\n".join(parts)


def build_topic_html(lesson_numbers: tuple[int, ...], cache: dict[int, str]) -> str:
    htmls = []
    for n in lesson_numbers:
        _, html = cache[n]
        htmls.append(html)
    if len(htmls) == 1:
        return htmls[0]
    # Continuation lessons: join with a light divider, exercises from both
    # parts end up concatenated in lesson order (matches how the site itself
    # splits these lessons across two pages).
    return "\n<hr>\n".join(htmls)


def main() -> None:
    cache: dict[int, tuple[str, str]] = {}
    for n in ALL_LESSON_NUMBERS:
        print(f"fetching lesson{n}...")
        html = fetch_lesson_html(n)
        title, body_html = extract_lesson_body_html(html)
        cache[n] = (title, body_html)
        print(f"  -> {title!r} ({len(body_html)} chars)")
        time.sleep(0.3)

    data = json.loads(THEORY_JSON.read_text(encoding="utf-8"))
    topics_by_id = {
        t["id"]: t for cat in data["categories"] for t in cat["topics"]
    }

    updated = []
    for lesson_numbers, topic_id in LESSON_TO_TOPIC.items():
        topic = topics_by_id.get(topic_id)
        if topic is None:
            print(f"WARNING: topic id {topic_id!r} not found in theory_tenses.json, skipping")
            continue
        topic["html"] = build_topic_html(lesson_numbers, cache)
        updated.append(topic_id)

    missing = set(topics_by_id) - set(updated)
    if missing:
        print(f"NOTE: topics left untouched (no lesson mapping): {sorted(missing)}")

    THEORY_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"updated {len(updated)} topics in {THEORY_JSON}")


if __name__ == "__main__":
    main()
