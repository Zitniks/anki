#!/usr/bin/env python3
"""One-off converter: Norwood_Builder_Simplified_A2.docx -> book_norwood_builder.json.

Reads the .docx as a zip of OOXML (stdlib zipfile + xml.etree, no python-docx
dependency) and splits it into front matter (characters, glossary) plus
numbered "Part N: Title" sections of paragraphs.
"""
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "Norwood_Builder_Simplified_A2.docx"
DST = ROOT / "book_norwood_builder.json"

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PART_RE = re.compile(r"^Part (\d+):\s*(.+)$")


def extract_paragraphs(path):
    with zipfile.ZipFile(path) as z:
        xml_bytes = z.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs = []
    for p in root.iter(f"{W_NS}p"):
        text = "".join(t.text or "" for t in p.iter(f"{W_NS}t"))
        paragraphs.append(text)
    return paragraphs


def non_empty_blocks(paragraphs, start, end):
    """Yield non-empty paragraph strings in [start, end)."""
    return [p for p in paragraphs[start:end] if p.strip()]


def main():
    paragraphs = extract_paragraphs(SRC)

    part_starts = [i for i, p in enumerate(paragraphs) if PART_RE.match(p.strip())]
    people_idx = next(i for i, p in enumerate(paragraphs) if p.strip() == "The People in This Story")
    words_idx = next(i for i, p in enumerate(paragraphs) if p.strip() == "Helpful Words Before You Read")

    characters = []
    for line in non_empty_blocks(paragraphs, people_idx + 1, words_idx):
        if " — " in line:
            name, desc = line.split(" — ", 1)
            characters.append({"name": name.strip(), "description": desc.strip()})
        else:
            characters.append({"name": "", "description": line.strip()})

    glossary = non_empty_blocks(paragraphs, words_idx + 1, part_starts[0])

    parts = []
    for idx, start in enumerate(part_starts):
        end = part_starts[idx + 1] if idx + 1 < len(part_starts) else len(paragraphs)
        match = PART_RE.match(paragraphs[start].strip())
        part_paragraphs = non_empty_blocks(paragraphs, start + 1, end)
        parts.append({
            "id": int(match.group(1)),
            "title": match.group(2).strip(),
            "paragraphs": part_paragraphs,
        })

    data = {
        "title": paragraphs[0].strip(),
        "subtitle": paragraphs[1].strip(),
        "source": paragraphs[2].strip(),
        "characters": characters,
        "glossary": glossary,
        "parts": parts,
    }
    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {DST}: {len(characters)} characters, {len(glossary)} glossary entries, {len(parts)} parts")


if __name__ == "__main__":
    main()
