#!/usr/bin/env python3
"""One-off converter: theory_tenses.md -> theory_tenses.json.

Splits the markdown file into topics by "## " headers (grouped by the
preceding "# ЧАСТЬ N." header) and renders each topic's body to plain HTML
with a small hand-rolled converter (no external markdown dependency).
Regenerate after editing theory_tenses.md by re-running this script.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "theory_tenses.md"
DST = ROOT / "theory_tenses.json"

GROUP_TITLES = {
    "ЧАСТЬ 1. НАСТОЯЩЕЕ ВРЕМЯ": "Настоящее время",
    "ЧАСТЬ 2. ПРОШЕДШЕЕ ВРЕМЯ": "Прошедшее время",
    "ЧАСТЬ 3. БУДУЩЕЕ ВРЕМЯ": "Будущее время",
    "ЧАСТЬ 4. СПРАВОЧНЫЕ ТАБЛИЦЫ": "Справочные таблицы",
}

LEVEL_RE = re.compile(r"[—–-]\s*([ABC][12](?:/[ABC][12])?)\s*⭐?\s*$")
NUMBERING_RE = re.compile(r"^\d+\.\d+\s+")


def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text):
    text = escape_html(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text, flags=re.DOTALL)
    text = text.replace("\n", "<br>")
    return text


def render_table(rows):
    header, *rest = rows
    body_rows = [r for r in rest if not re.match(r"^[\s:|-]+$", r)]

    def cells(row):
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]

    head_html = "".join(f"<th>{inline(c)}</th>" for c in cells(header))
    body_html = ""
    for row in body_rows:
        body_html += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells(row)) + "</tr>"
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


def render_body(lines):
    html = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(escape_html(lines[i].rstrip("\n")))
                i += 1
            i += 1  # skip closing fence
            html.append(f"<pre><code>{chr(10).join(code_lines)}</code></pre>")
            continue

        if stripped.startswith("### "):
            html.append(f"<h3>{inline(stripped[4:])}</h3>")
            i += 1
            continue

        if stripped == "---":
            html.append("<hr>")
            i += 1
            continue

        if stripped.startswith("|"):
            table_lines = []
            while i < n and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            html.append(render_table(table_lines))
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            # Join before applying inline markup: bold/italic spans occasionally
            # cross line boundaries within a single blockquote (see 1.5's rule box).
            html.append(f"<blockquote><p>{inline(chr(10).join(quote_lines))}</p></blockquote>")
            continue

        if re.match(r"^[-*]\s+", stripped):
            item_lines = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                item_lines.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            html.append("<ul>" + "".join(f"<li>{inline(it)}</li>" for it in item_lines) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            item_lines = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_lines.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            html.append("<ol>" + "".join(f"<li>{inline(it)}</li>" for it in item_lines) + "</ol>")
            continue

        html.append(f"<p>{inline(stripped)}</p>")
        i += 1

    return "\n".join(html)


def parse_topics(text):
    lines = text.split("\n")
    group = None
    topics = []
    current_title = None
    current_body = []

    def flush():
        if current_title is None:
            return
        body_html = render_body(current_body)
        level_match = LEVEL_RE.search(current_title)
        level = level_match.group(1) if level_match else None
        title = current_title
        if level_match:
            title = title[: level_match.start()].rstrip()
        title = NUMBERING_RE.sub("", title).strip()
        topic_id = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", "-", title.lower()).strip("-")
        topics.append({
            "id": topic_id,
            "title": title,
            "group": group,
            "level": level,
            "html": body_html,
        })

    for line in lines:
        if line.startswith("# "):
            flush()
            current_title = None
            current_body = []
            heading = line[2:].strip()
            group = GROUP_TITLES.get(heading, group)
            continue
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            current_body = []
            continue
        current_body.append(line)

    flush()
    return topics


def main():
    text = SRC.read_text(encoding="utf-8")
    topics = parse_topics(text)
    data = {"categories": [{"id": "tenses", "title": "Времена", "topics": topics}]}
    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {DST} with {len(topics)} topics")


if __name__ == "__main__":
    main()
