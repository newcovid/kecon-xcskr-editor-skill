#!/usr/bin/env python3
"""Search Kecon/xRobotDesigner help: the curated notes plus the local CHM.

Two sources are supported.

* The curated knowledge base shipped with this skill (`references/kecon-help-kb.md`).
* A local index built from the xRobotDesigner CHM installed on the machine.
  The CHM itself is vendor material and is never copied into this repository;
  `index` decompiles it with the Windows built-in `hh.exe`, extracts plain text
  from each topic, and stores the result in a cache directory outside the skill.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_KB = SKILL_DIR / "references" / "kecon-help-kb.md"
DEFAULT_CACHE = Path(os.environ.get("KECON_HELP_CACHE", Path.home() / ".kecon-xcskr-editor" / "help"))
INDEX_NAME = "index.json"
TOPIC_DIR = "topics"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# --------------------------------------------------------------------------
# curated knowledge base
# --------------------------------------------------------------------------


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


def score_text(text: str, terms: list[str], weight: int = 1, cap: int = 0) -> int:
    """Weighted term score.

    A cap keeps a very long topic from outranking a precise short one purely by
    repeating a term; `matched_terms` then adds the coverage bonus.
    """
    haystack = text.lower()
    score = 0
    for term in terms:
        count = haystack.count(term)
        if cap:
            count = min(count, cap)
        score += count * max(1, len(term)) * weight
    return score


def matched_terms(text: str, terms: list[str]) -> int:
    haystack = text.lower()
    return sum(1 for term in terms if term in haystack)


def score_section(section: Section, terms: list[str]) -> int:
    return score_text(f"{section.heading}\n{section.body}", terms)


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


# --------------------------------------------------------------------------
# CHM extraction
# --------------------------------------------------------------------------


class TextExtractor(HTMLParser):
    """Turn one Word-exported help page into readable plain text.

    Table rows become lines and cells are separated by a pipe, which keeps the
    parameter tables that make up most of the Kecon help readable.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "tr":
            self.parts.append("\n")
        elif tag in ("td", "th"):
            if self.parts and not self.parts[-1].endswith("\n"):
                self.parts.append(" | ")
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        cleaned = re.sub(r"\s+", " ", data)
        if not cleaned.strip():
            return
        if self.in_title:
            self.title_parts.append(cleaned)
        else:
            self.parts.append(cleaned)

    def text(self) -> str:
        joined = "".join(self.parts)
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r" *\n *", "\n", joined)
        joined = re.sub(r"\n{2,}", "\n", joined)
        return joined.strip()

    def title(self) -> str:
        return " ".join(self.title_parts).strip()


def decode_help_bytes(raw: bytes) -> str:
    match = re.search(rb"charset=([\w-]+)", raw[:4096], flags=re.IGNORECASE)
    encoding = match.group(1).decode("ascii", "replace").lower() if match else "gbk"
    if encoding in ("gb2312", "gb_2312-80", "gbk", "ms936"):
        encoding = "gbk"
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("gbk", errors="replace")


def html_to_text(raw: bytes) -> tuple[str, str]:
    parser = TextExtractor()
    parser.feed(decode_help_bytes(raw))
    return parser.title(), parser.text()


class TocParser(HTMLParser):
    """Read an HTML Help .hhc sitemap into (title, target, breadcrumb) rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.stack: list[str] = []
        self.current: dict[str, str] = {}
        self.in_object = False
        self.rows: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag == "ul":
            self.depth += 1
        elif tag == "object" and attr_map.get("type", "").lower() == "text/sitemap":
            self.in_object = True
            self.current = {}
        elif tag == "param" and self.in_object:
            self.current[attr_map.get("name", "").lower()] = attr_map.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "ul":
            self.depth = max(0, self.depth - 1)
            del self.stack[self.depth :]
        elif tag == "object" and self.in_object:
            self.in_object = False
            name = self.current.get("name", "").strip()
            local = self.current.get("local", "").strip()
            if not name:
                return
            level = max(0, self.depth - 1)
            del self.stack[level:]
            self.stack.append(name)
            if local:
                self.rows.append({"title": name, "local": local, "path": list(self.stack)})


def parse_toc(hhc_path: Path) -> dict[str, dict[str, object]]:
    parser = TocParser()
    parser.feed(decode_help_bytes(hhc_path.read_bytes()))
    mapping: dict[str, dict[str, object]] = {}
    for row in parser.rows:
        key = normalize_local(str(row["local"]))
        mapping.setdefault(key, row)
    return mapping


def normalize_local(local: str) -> str:
    cleaned = local.replace("\\", "/").split("#", 1)[0].strip().lstrip("./")
    return cleaned.lower()


def find_hh_exe() -> str:
    found = shutil.which("hh") or shutil.which("hh.exe")
    if found:
        return found
    fallback = Path(os.environ.get("SystemRoot", "C:/Windows")) / "hh.exe"
    if fallback.exists():
        return str(fallback)
    raise SystemExit("hh.exe not found; CHM decompiling needs Windows HTML Help (hh.exe)")


def decompile_chm(chm: Path, work_dir: Path, timeout: float = 180.0) -> Path:
    """Decompile a CHM with hh.exe and wait for the output to settle.

    hh.exe returns immediately and keeps writing in the background, so the file
    count is polled until it stops growing.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_hh_exe(), "-decompile", str(work_dir), str(chm)], check=False)
    deadline = time.monotonic() + timeout
    last_count = -1
    stable_for = 0.0
    while time.monotonic() < deadline:
        count = sum(1 for _ in work_dir.rglob("*"))
        if count and count == last_count:
            stable_for += 0.5
            if stable_for >= 2.0:
                return work_dir
        else:
            stable_for = 0.0
        last_count = count
        time.sleep(0.5)
    if last_count <= 0:
        raise SystemExit(f"hh.exe produced no output in {work_dir}")
    return work_dir


def iter_topic_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in (".htm", ".html"):
            continue
        if any(part.lower().endswith(".files") for part in path.parts):
            continue
        files.append(path)
    return files


def slugify(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value).strip("_")


def topic_id(root: Path, path: Path, title: str = "") -> str:
    """Prefer a readable id from the TOC title; fall back to the file path.

    Help pages inside the bundled V3.0 tree are named outline_NN.htm, which is
    useless on the command line, while the TOC gives them real names.
    """
    if title:
        slug = slugify(title)
        if slug:
            return slug[:60]
    rel = path.relative_to(root).as_posix()
    return slugify(rel[: -len(path.suffix)])[:60] or "topic"


def build_index(source_dir: Path, cache_dir: Path, source_label: str, min_chars: int = 40) -> dict[str, object]:
    topic_dir = cache_dir / TOPIC_DIR
    if topic_dir.exists():
        shutil.rmtree(topic_dir)
    topic_dir.mkdir(parents=True, exist_ok=True)

    toc: dict[str, dict[str, object]] = {}
    for hhc in sorted(source_dir.rglob("*.hhc")):
        toc.update(parse_toc(hhc))

    topics: list[dict[str, object]] = []
    used_ids: set[str] = set()
    for path in iter_topic_files(source_dir):
        try:
            title, text = html_to_text(path.read_bytes())
        except OSError:
            continue
        if len(text) < min_chars:
            continue
        rel = path.relative_to(source_dir).as_posix()
        entry = toc.get(normalize_local(rel), {})
        toc_path = list(entry.get("path", [])) if entry else []
        display = str(entry.get("title") or title or path.stem).strip()
        base_id = topic_id(source_dir, path, display)
        identifier = base_id
        suffix = 2
        while identifier in used_ids:
            identifier = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(identifier)
        (topic_dir / f"{identifier}.txt").write_text(text, encoding="utf-8")
        topics.append(
            {
                "id": identifier,
                "title": display,
                "file": rel,
                "toc_path": toc_path,
                "chars": len(text),
            }
        )

    index = {
        "format": "kecon-help-index/v1",
        "source": source_label,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "topic_count": len(topics),
        "toc_entries": len(toc),
        "topics": topics,
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / INDEX_NAME).write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def load_index(cache_dir: Path) -> dict[str, object] | None:
    path = cache_dir / INDEX_NAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def topic_text(cache_dir: Path, identifier: str) -> str:
    path = cache_dir / TOPIC_DIR / f"{identifier}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_index(args: argparse.Namespace) -> int:
    if not args.chm and not args.from_dir:
        raise SystemExit("pass --chm to decompile a CHM, or --from-dir for an already decompiled tree")
    cache_dir = args.cache_dir
    if args.from_dir:
        source_dir = args.from_dir
        label = str(args.from_dir)
        index = build_index(source_dir, cache_dir, label)
    else:
        work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="kecon_chm_"))
        print(f"Decompiling {args.chm} -> {work_dir}")
        decompile_chm(args.chm, work_dir)
        try:
            index = build_index(work_dir, cache_dir, str(args.chm))
        finally:
            if args.work_dir is None and not args.keep_work:
                shutil.rmtree(work_dir, ignore_errors=True)
    print("HELP_INDEX=OK")
    print(f"CacheDir={cache_dir}")
    print(f"Source={index['source']}")
    print(f"Topics={index['topic_count']} TocEntries={index['toc_entries']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    index = load_index(args.cache_dir)
    print(f"KB={args.kb} exists={args.kb.exists()}")
    print(f"CacheDir={args.cache_dir}")
    if not index:
        print("LocalIndex=MISSING  (run: kecon_help.py index --chm <path to xCSStudioHelpFile.chm>)")
        return 0
    print(f"LocalIndex=OK topics={index['topic_count']} built_at={index['built_at']}")
    print(f"Source={index['source']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    index = load_index(args.cache_dir)
    if not index:
        print("本地帮助索引未建立，请先运行 index 子命令。")
        return 1
    pattern = re.compile(args.pattern, re.IGNORECASE) if args.pattern else None
    shown = 0
    for topic in index["topics"]:  # type: ignore[index]
        label = " > ".join(topic["toc_path"]) if topic["toc_path"] else topic["title"]
        if pattern and not pattern.search(f"{topic['title']} {label}"):
            continue
        print(f"{topic['id']}\t{topic['title']}\t{label}")
        shown += 1
        if args.limit and shown >= args.limit:
            break
    print(f"Listed={shown}/{index['topic_count']}")
    return 0


def search_kb(kb_path: Path, terms: list[str], limit: int) -> list[tuple[int, Section]]:
    if not kb_path.exists():
        return []
    sections = split_sections(kb_path.read_text(encoding="utf-8"))
    hits = [(score_section(section, terms), section) for section in sections]
    hits = [item for item in hits if item[0] > 0]
    hits.sort(key=lambda item: item[0], reverse=True)
    return hits[:limit]


def search_local(cache_dir: Path, terms: list[str], limit: int) -> list[tuple[int, dict[str, object], str]]:
    index = load_index(cache_dir)
    if not index:
        return []
    scored: list[tuple[int, dict[str, object], str]] = []
    for topic in index["topics"]:  # type: ignore[index]
        text = topic_text(cache_dir, str(topic["id"]))
        if not text:
            continue
        crumb = " > ".join(topic["toc_path"])  # type: ignore[arg-type]
        score = score_text(str(topic["title"]), terms, weight=20)
        score += score_text(crumb, terms, weight=6)
        score += score_text(text, terms, cap=5)
        # Reward covering more of the query rather than repeating one term.
        covered = matched_terms(f"{topic['title']} {crumb}\n{text}", terms)
        score += covered * covered * 25
        if covered < len(terms):
            score //= 2
        if score > 0:
            scored.append((score, topic, text))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]


def cmd_search(args: argparse.Namespace) -> int:
    terms = tokenize(args.query)
    if not terms:
        raise SystemExit("query is empty")

    kb_hits = search_kb(args.kb, terms, args.limit) if args.source in ("kb", "all") else []
    local_hits = search_local(args.cache_dir, terms, args.limit) if args.source in ("local", "all") else []

    print(f"Query={args.query}")
    if kb_hits:
        print(f"\n=== 提炼知识库 KB={args.kb} ===")
        for score, section in kb_hits:
            print(f"## {section.heading}  (score={score})")
            print(compact_snippet(section.body, terms))
            print()

    if local_hits:
        print(f"=== 本机帮助原文索引 CacheDir={args.cache_dir} ===")
        for score, topic, text in local_hits:
            crumb = " > ".join(topic["toc_path"]) if topic["toc_path"] else ""
            print(f"## {topic['title']}  (id={topic['id']}, score={score}, {topic['chars']} 字)")
            if crumb:
                print(f"   目录: {crumb}")
            print(f"   {compact_snippet(text, terms)}")
            print(f"   全文: kecon_help.py show {topic['id']}")
            print()
    elif args.source in ("local", "all") and load_index(args.cache_dir) is None:
        print("\n本机帮助原文索引未建立。建立后可直接检索官方 CHM 原文：")
        print("   kecon_help.py index --chm \"<xCSStudioHelpFile.chm 路径>\"")

    if not kb_hits and not local_hits:
        print("未找到命中。请换关键词，或先建立本机帮助原文索引。")
        return 1
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    index = load_index(args.cache_dir)
    if not index:
        print("本地帮助索引未建立，请先运行 index 子命令。")
        return 1
    needle = args.topic.lower()
    exact = [topic for topic in index["topics"] if str(topic["id"]).lower() == needle]  # type: ignore[index]
    partial = [
        topic
        for topic in index["topics"]  # type: ignore[index]
        if needle in str(topic["id"]).lower() or needle in str(topic["title"]).lower()
    ]
    candidates = exact or partial
    if not candidates:
        print(f"未找到主题 {args.topic!r}")
        return 1
    if len(candidates) > 1 and not exact:
        print(f"匹配到 {len(candidates)} 个主题，请用更精确的 id：")
        for topic in candidates[:20]:
            print(f"  {topic['id']}\t{topic['title']}")
        return 1
    topic = candidates[0]
    text = topic_text(args.cache_dir, str(topic["id"]))
    crumb = " > ".join(topic["toc_path"]) if topic["toc_path"] else ""
    print(f"# {topic['title']}")
    if crumb:
        print(f"目录: {crumb}")
    print(f"来源: {topic['file']}  ({topic['chars']} 字)")
    print()
    if args.max_chars and len(text) > args.max_chars:
        print(text[: args.max_chars])
        print(f"\n... [截断，共 {len(text)} 字，用 --max-chars 0 查看全文]")
    else:
        print(text)
    return 0


def add_cache_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="local help index cache directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search Kecon/xRobotDesigner help notes and the local CHM")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search the curated KB and the local help index")
    p.add_argument("query")
    p.add_argument("--kb", type=Path, default=DEFAULT_KB)
    add_cache_arg(p)
    p.add_argument("--source", choices=["kb", "local", "all"], default="all")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("index", help="build the local help index from a CHM or a decompiled tree")
    p.add_argument("--chm", type=Path, help="path to xCSStudioHelpFile.chm")
    p.add_argument("--from-dir", type=Path, help="already decompiled help tree")
    add_cache_arg(p)
    p.add_argument("--work-dir", type=Path, help="where to decompile; default is a temp dir that is removed afterwards")
    p.add_argument("--keep-work", action="store_true", help="keep the decompiled tree, including images")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("show", help="print one help topic in full")
    p.add_argument("topic", help="topic id or part of its title")
    add_cache_arg(p)
    p.add_argument("--max-chars", type=int, default=0, help="truncate output; 0 prints everything")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("list", help="list indexed help topics")
    add_cache_arg(p)
    p.add_argument("--pattern", help="regular expression matched against title and TOC path")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="show KB and local index state")
    p.add_argument("--kb", type=Path, default=DEFAULT_KB)
    add_cache_arg(p)
    p.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
