#!/usr/bin/env python3
"""Search the curated Kecon/xRobotDesigner help knowledge base."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_KB = Path(__file__).resolve().parents[1] / "references" / "kecon-help-kb.md"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass
class Section:
    heading: str
    body: str


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    current_heading = "概览"
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append(Section(current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(Section(current_heading, "\n".join(current_lines).strip()))
    return sections


def tokenize(query: str) -> list[str]:
    parts = re.findall(r"[A-Za-z0-9_+\-]+|[\u4e00-\u9fff]{2,}", query)
    return [part.lower() for part in parts if part.strip()]


def score_section(section: Section, terms: list[str]) -> int:
    haystack = f"{section.heading}\n{section.body}".lower()
    score = 0
    for term in terms:
        score += haystack.count(term) * max(1, len(term))
    return score


def compact_snippet(text: str, terms: list[str], width: int = 360) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    lower = one_line.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    start = max(0, min(positions) - 80) if positions else 0
    snippet = one_line[start : start + width]
    if start:
        snippet = "..." + snippet
    if start + width < len(one_line):
        snippet += "..."
    return snippet


def cmd_search(args: argparse.Namespace) -> int:
    kb_path = args.kb
    text = kb_path.read_text(encoding="utf-8")
    terms = tokenize(args.query)
    if not terms:
        raise SystemExit("query is empty")
    scored = [(score_section(section, terms), section) for section in split_sections(text)]
    hits = [(score, section) for score, section in scored if score > 0]
    hits.sort(key=lambda item: item[0], reverse=True)
    if not hits:
        print("未在提炼知识库中找到命中。请按 KB 中的“原文兜底查询”说明检索 CHM/PDF 原文。")
        return 1
    print(f"KB={kb_path}")
    print(f"Query={args.query}")
    print()
    for score, section in hits[: args.limit]:
        print(f"## {section.heading}  (score={score})")
        print(compact_snippet(section.body, terms))
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search curated Kecon/xRobotDesigner help notes")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search", help="search the curated help knowledge base")
    p.add_argument("query")
    p.add_argument("--kb", type=Path, default=DEFAULT_KB)
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_search)
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
