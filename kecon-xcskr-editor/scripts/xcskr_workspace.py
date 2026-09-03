#!/usr/bin/env python3
"""Explode a Kecon `.xcskr` project into an editable text workspace and fold it back.

The GUI editor cannot change its font, size or theme, so the practical way to
write a large project is to edit plain text somewhere else.  `.xcskr` is a
single GBK XML document with ST buried in an attribute value, which is exactly
the shape a general purpose editor handles worst -- hence this round trip.

Design rules, in the order they matter:

1. **One write.**  `import-workspace` applies every change to one in-memory
   string, parses the result once, and writes the file once.  A loop of CLI
   calls would leave the project half-updated when the fifth edit fails.
2. **Never reserialize.**  Every edit is a targeted raw-text patch, because
   ElementTree round-tripping flattens the ST formatting stored in attributes.
3. **Refuse rather than merge.**  The manifest records the project's sha256 at
   export time.  If the project moved on (someone opened the GUI and saved),
   import aborts and asks for a fresh export.  Silently overwriting the GUI's
   work is the one failure this tool must never produce.
4. **Graphical logic is a graph, not a table.**  A `.graph.json` carries blocks,
   pins, wires and comments.  Only the safe subset is writable: pin bindings,
   init values, negation, block deactivation and wires.  Adding or retyping a
   block is refused -- a block TYPE implies a fixed pin list the file does not
   describe, so a new block must be copied from a reference project.

Workspace layout::

    <workspace>/
      manifest.json                 round-trip state; do not hand-edit
      程序/<任务>/NN_<名>.st         one file per program, NN = execution order
      程序/<任务>/NN_<名>.graph.json  graphical program, same ordering
      功能块/<名>.st | .graph.json
      只读/变量.md 结构体.md 任务.md 硬件标签.tsv 声明.st 符号表.json
      README.md

Files under 只读/ are regenerated on every export and ignored by import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xcskr_tool as xt  # noqa: E402

SCHEMA_VERSION = 1
WORKSPACE_ENCODING = "utf-8"

DIR_PROGRAMS = "程序"
DIR_FUNCTION_BLOCKS = "功能块"
DIR_READONLY = "只读"
MANIFEST_NAME = "manifest.json"

# Unit suffixes the project's naming convention uses.  Longest first so that
# `_mps` wins over `_m`; a wrong unit in a hover tip is worse than none.
UNIT_SUFFIXES = [
    ("_01rpm", "0.1 rpm"),
    ("_cdeg", "0.01 度"),
    ("_mps2", "m/s^2"),
    ("_mps", "m/s"),
    ("_radps2", "rad/s^2"),
    ("_radps", "rad/s"),
    ("_deg", "度"),
    ("_ms", "ms"),
    ("_cnt", "计数"),
    ("_pct", "%"),
    ("_mm", "mm"),
    ("_ma", "mA"),
    ("_m", "m"),
    ("_v", "V"),
    ("_a", "A"),
]
UNIT_IN_DESC_RE = re.compile(r"单位\s*[:：]\s*([^\s，,；;。]+)")
ARRAY_INDEX_RE = re.compile(r"\[\d+\]")
MAX_SYMBOL_DEPTH = 6
MAX_SYMBOLS = 50000


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_workspace_file(path: Path) -> str:
    return path.read_text(encoding=WORKSPACE_ENCODING, newline="")


ST_NEWLINE = "\r\n"


def write_workspace_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=WORKSPACE_ENCODING, newline="")


def write_workspace_st(path: Path, text: str) -> None:
    """Write an exported .st with one fixed line ending, CRLF.

    ST bodies live inside a `SECTION_LOGIC_ST CONTENT` attribute, and the GUI
    writes that attribute's line breaks three different ways depending on which
    version last touched the POU -- literal LF, `&#10;`, or `&#x0D;&#x0A;`.
    Exporting the decoded text verbatim therefore hands out a mix: a POU the
    GUI has edited comes out CRLF, its neighbours come out LF.  Every later
    GUI edit flips one more file and shows up as a whole-file diff that buries
    the real change.

    The GUI's own style is `&#x0D;&#x0A;`, and we cannot change the GUI, so the
    workspace converges on CRLF instead of fighting it.  Nothing downstream
    cares: `xml_attr_encode` normalizes newlines before re-encoding, so import
    still writes back in each element's own style and the round trip is stable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", ST_NEWLINE)
    path.write_text(body, encoding=WORKSPACE_ENCODING, newline="")


def write_json_file(path: Path, data: object) -> None:
    write_workspace_file(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def yes(value: str) -> bool:
    return str(value).strip().upper() == "YES"


def yes_no(flag: bool) -> str:
    return "YES" if flag else ""


def task_dir_name(task: dict, seen: dict[str, int]) -> str:
    """Directory name for a task, stable and readable.

    Execution order is a functional property here -- programs run in document
    order -- so the directory and the NN prefix are what make that order
    visible without opening the GUI.
    """
    kind = task.get("kind", "")
    if kind == "main":
        base = "主任务"
    elif kind == "cycle":
        cycle = task.get("cycle_ms") or "?"
        base = f"周期任务{cycle}ms"
    elif kind == "event":
        base = "事件任务"
    elif kind == "startup":
        base = "启动任务"
    else:
        base = f"任务{kind or '未知'}"
    count = seen.get(base, 0)
    seen[base] = count + 1
    if count:
        base = f"{base}_T{task.get('id') or count}"
    return base


def unit_of(name: str, desc: str) -> str:
    match = UNIT_IN_DESC_RE.search(desc or "")
    if match:
        return match.group(1)
    lowered = (name or "").lower()
    for suffix, unit in UNIT_SUFFIXES:
        if lowered.endswith(suffix):
            return unit
    return ""


# --------------------------------------------------------------------------
# raw XML element spans (self-closing and paired forms)
# --------------------------------------------------------------------------


class ElementSpan:
    """A raw-text slice of one XML element, with its start tag isolated."""

    __slots__ = ("tag", "start", "end", "tag_end", "self_closing", "raw")

    def __init__(self, tag: str, start: int, end: int, tag_end: int, self_closing: bool, raw: str):
        self.tag = tag
        self.start = start
        self.end = end
        self.tag_end = tag_end  # end offset of the start tag, relative to `start`
        self.self_closing = self_closing
        self.raw = raw

    @property
    def start_tag(self) -> str:
        return self.raw[: self.tag_end]

    @property
    def inner(self) -> str:
        if self.self_closing:
            return ""
        return self.raw[self.tag_end : -(len(self.tag) + 3)]


def find_element_span(text: str, tag: str, name: str, start_at: int = 0) -> ElementSpan:
    """Locate `<tag ... NAME="name" ...>` whether self-closing or paired.

    None of the tags this module patches (CONTROL_LOGIC_BLOCK, BLOCK_PIN_*,
    CONTROL_LOGIC_LINE) nest inside themselves, so finding the first matching
    close tag is exact.  USER_STRUCT_MEMBER does nest and is deliberately not
    handled here.
    """
    pattern = re.compile(
        rf'<{tag}\b[^>]*?\bNAME="{re.escape(name)}"[^>]*?(/?)>',
        flags=re.DOTALL,
    )
    match = pattern.search(text, start_at)
    if match is None:
        raise ValueError(f"{tag} NAME={name!r} not found")
    tag_end = match.end() - match.start()
    if match.group(1) == "/":
        return ElementSpan(tag, match.start(), match.end(), tag_end, True, match.group(0))
    close = f"</{tag}>"
    close_at = text.find(close, match.end())
    if close_at < 0:
        raise ValueError(f"{tag} NAME={name!r} close tag not found")
    end = close_at + len(close)
    return ElementSpan(tag, match.start(), end, tag_end, False, text[match.start() : end])


def set_start_tag_attr(start_tag: str, key: str, value: str) -> str:
    """Set or insert one attribute on a start tag, leaving everything else byte-identical."""
    pattern = re.compile(rf'(\s{re.escape(key)}=")([^"]*)(")')
    if pattern.search(start_tag):
        return pattern.sub(lambda m: m.group(1) + xt.xml_attr_encode(value) + m.group(3), start_tag, count=1)
    if start_tag.endswith("/>"):
        head, tail = start_tag[:-2].rstrip(), "/>"
    else:
        head, tail = start_tag[:-1].rstrip(), ">"
    return f'{head} {key}="{xt.xml_attr_encode(value)}"{tail}'


def replace_slice(text: str, start: int, end: int, replacement: str) -> str:
    return text[:start] + replacement + text[end:]


# --------------------------------------------------------------------------
# graph model: xcskr <-> graph.json
# --------------------------------------------------------------------------

GRAPH_NOTE = [
    "本文件是图形程序（LD/FBD）的完整快照，回灌时只接受安全子集的改动：",
    "  可改：pins[].bind、pins[].init、pins[].negated、blocks[].deactive、lines 增删",
    "  只读：blocks[] 的增删与 name/type/rect、pins[] 的增删与 name/datatype",
    "块的 TYPE 隐含一张文件里并未描述的固定引脚表，凭空造块会得到一个引脚对不上的块，",
    "所以新增块必须用 xcskr_tool.py copy-block 从参考工程复制。",
    "bind 的三种取值：null（不接）、{\"var\": \"变量名\"}（接变量）、{\"line\": \"_LINE0\"}（接连线）。",
]


def pin_to_json(pin: dict) -> dict:
    conn = pin.get("connection") or {}
    kind = conn.get("kind") or ""
    value = conn.get("value") or ""
    if kind == "variable" and value:
        bind: object = {"var": value}
    elif kind == "line" and value:
        bind = {"line": value}
    else:
        bind = None
    return {
        "dir": "in" if pin.get("direction") == "input" else "out",
        "name": pin.get("name", ""),
        "datatype": pin.get("datatype", ""),
        "desc": pin.get("desc", ""),
        "bind": bind,
        "init": pin.get("init_value", ""),
        "negated": yes(pin.get("negated", "")),
        "enabled": yes(pin.get("enabled", "")),
    }


def graph_to_json(record: dict) -> dict:
    blocks = []
    for block in record.get("blocks", []):
        pins = [pin_to_json(pin) for pin in block.get("inputs", [])]
        pins += [pin_to_json(pin) for pin in block.get("outputs", [])]
        blocks.append(
            {
                "name": block.get("name", ""),
                "type": block.get("type", ""),
                "desc": block.get("desc", ""),
                "rect": block.get("rect_position", ""),
                "deactive": block.get("deactive", "") == "YES",
                "pins": pins,
            }
        )
    lines = [
        {
            "name": line.get("NAME", ""),
            "position": line.get("LINE_POSITION", ""),
            "from_powerrail": yes(line.get("FROM_POWERRAIL", "")),
            "deactive": line.get("DEACTIVE", "") == "YES",
        }
        for line in record.get("lines", [])
    ]
    return {
        "_说明": GRAPH_NOTE,
        "pou": record.get("name", ""),
        "pou_type": record.get("pou_type", ""),
        "language": record.get("language", ""),
        "desc": record.get("desc", ""),
        "blocks": blocks,
        "lines": lines,
        "comments": record.get("comments", []),
    }


def graph_pin_key(pin: dict) -> tuple[str, str]:
    return (pin.get("dir", ""), pin.get("name", ""))


def diff_graph(old: dict, new: dict, pou: str) -> tuple[list[dict], list[str]]:
    """Compare two graph.json payloads; return (edits, refusals).

    Refusals are the changes this tool will not perform.  They are collected
    rather than raised one at a time so a single run reports every problem.
    """
    edits: list[dict] = []
    refusals: list[str] = []

    # The top-level fields describe the POU itself, not its diagram, and none of
    # them round-trip.  Without this check an edit to `desc` looks like it
    # worked -- import reports success, the manifest takes the new hash, and the
    # text is gone at the next export, having never reached the project.
    # POU DESC is set with `xcskr_tool.py set-attrs --kind pou`.
    for field in ("pou", "pou_type", "language", "desc"):
        if old.get(field) != new.get(field):
            hint = "，POU 的 DESC 用 xcskr_tool.py set-attrs --kind pou 改" if field == "desc" else ""
            refusals.append(
                f"{pou}: 改了只读字段 {field}（{old.get(field)!r} -> {new.get(field)!r}）{hint}"
            )

    old_blocks = {block["name"]: block for block in old.get("blocks", [])}
    new_blocks = {block["name"]: block for block in new.get("blocks", [])}

    for name in new_blocks.keys() - old_blocks.keys():
        refusals.append(f"{pou}: 新增了块 {name}；块不能凭空创建，请用 xcskr_tool.py copy-block 从参考工程复制")
    for name in old_blocks.keys() - new_blocks.keys():
        refusals.append(f"{pou}: 删除了块 {name}；本工具不删块，请在 GUI 中删除")

    for name in sorted(old_blocks.keys() & new_blocks.keys()):
        ob, nb = old_blocks[name], new_blocks[name]
        for field, label in (("type", "TYPE"), ("rect", "RECT_POSITION")):
            if ob.get(field) != nb.get(field):
                refusals.append(f"{pou}.{name}: 改了只读字段 {label}（{ob.get(field)!r} -> {nb.get(field)!r}）")
        if bool(ob.get("deactive")) != bool(nb.get("deactive")):
            edits.append({"op": "block_deactive", "block": name, "value": bool(nb.get("deactive"))})

        old_pins = {graph_pin_key(pin): pin for pin in ob.get("pins", [])}
        new_pins = {graph_pin_key(pin): pin for pin in nb.get("pins", [])}
        for key in new_pins.keys() - old_pins.keys():
            refusals.append(f"{pou}.{name}: 新增了引脚 {key[0]}:{key[1]}；引脚表由块类型决定，不能增删")
        for key in old_pins.keys() - new_pins.keys():
            refusals.append(f"{pou}.{name}: 删除了引脚 {key[0]}:{key[1]}；引脚表由块类型决定，不能增删")
        for key in sorted(old_pins.keys() & new_pins.keys()):
            op_, np_ = old_pins[key], new_pins[key]
            if op_.get("datatype") != np_.get("datatype"):
                refusals.append(f"{pou}.{name}.{key[1]}: 改了只读字段 DATATYPE")
            if op_.get("bind") != np_.get("bind"):
                edits.append({"op": "pin_bind", "block": name, "dir": key[0], "pin": key[1], "value": np_.get("bind")})
            if str(op_.get("init", "")) != str(np_.get("init", "")):
                edits.append({"op": "pin_init", "block": name, "dir": key[0], "pin": key[1], "value": str(np_.get("init", ""))})
            if bool(op_.get("negated")) != bool(np_.get("negated")):
                edits.append({"op": "pin_negated", "block": name, "dir": key[0], "pin": key[1], "value": bool(np_.get("negated"))})

    old_lines = {line["name"]: line for line in old.get("lines", [])}
    new_lines = {line["name"]: line for line in new.get("lines", [])}
    for name in sorted(new_lines.keys() - old_lines.keys()):
        edits.append({"op": "line_add", "line": new_lines[name]})
    for name in sorted(old_lines.keys() - new_lines.keys()):
        edits.append({"op": "line_remove", "line": name})
    for name in sorted(old_lines.keys() & new_lines.keys()):
        ol, nl = old_lines[name], new_lines[name]
        if ol != nl:
            edits.append({"op": "line_update", "line": nl})
    return edits, refusals


PIN_TAG = {"in": "BLOCK_PIN_INPUT", "out": "BLOCK_PIN_OUTPUT"}


def apply_pin_edit(block_raw: str, direction: str, pin_name: str, op: str, value: object) -> str:
    tag = PIN_TAG[direction]
    span = find_element_span(block_raw, tag, pin_name)
    start_tag = span.start_tag

    if op == "pin_init":
        new_start = set_start_tag_attr(start_tag, "INIT_VALUE", str(value))
        return replace_slice(block_raw, span.start, span.start + span.tag_end, new_start)

    if op == "pin_negated":
        new_start = set_start_tag_attr(start_tag, "NEGATED", yes_no(bool(value)))
        return replace_slice(block_raw, span.start, span.start + span.tag_end, new_start)

    if op != "pin_bind":
        raise ValueError(f"unknown pin edit {op!r}")

    if value is None:
        conn_type, conn_value = "", ""
    elif isinstance(value, dict) and "var" in value:
        conn_type, conn_value = xt.CONNECTION_TYPE_VARIABLE, str(value["var"])
    elif isinstance(value, dict) and "line" in value:
        conn_type, conn_value = xt.CONNECTION_TYPE_LINE, str(value["line"])
    else:
        raise ValueError(f"引脚 {pin_name} 的 bind 取值无法识别：{value!r}；只接受 null / {{\"var\":…}} / {{\"line\":…}}")

    if not conn_type:
        # Unbind: drop the child and collapse back to the self-closing form the
        # GUI writes for an unconnected pin.
        if span.self_closing:
            return block_raw
        collapsed = start_tag[:-1].rstrip() + " />"
        return replace_slice(block_raw, span.start, span.end, collapsed)

    child = f'<CONTROL_BLOCK_CONNECTION CONNECTION_TYPE="{conn_type}" CONNECTION_VALUE="{xt.xml_attr_encode(conn_value)}" />'
    if span.self_closing:
        opened = start_tag[:-2].rstrip() + ">"
        return replace_slice(block_raw, span.start, span.end, f"{opened}{child}</{tag}>")
    existing = re.search(r"<CONTROL_BLOCK_CONNECTION\b[^>]*?/>", span.raw, flags=re.DOTALL)
    if existing is None:
        new_raw = span.raw[: span.tag_end] + child + span.raw[span.tag_end :]
    else:
        new_raw = replace_slice(span.raw, existing.start(), existing.end(), child)
    return replace_slice(block_raw, span.start, span.end, new_raw)


def line_element(line: dict) -> str:
    return (
        f'<CONTROL_LOGIC_LINE DEACTIVE="{yes_no(bool(line.get("deactive")))}"'
        f' FROM_POWERRAIL="{"YES" if line.get("from_powerrail") else "NO"}"'
        f' LINE_POSITION="{xt.xml_attr_encode(str(line.get("position", "")))}"'
        f' NAME="{xt.xml_attr_encode(str(line.get("name", "")))}" POSITION_TYPE="0" />'
    )


def apply_graph_edits(pou_raw: str, edits: list[dict]) -> str:
    """Apply graph edits to one POU's raw XML.

    Edits are grouped per block so each block subtree is located once; a pin
    edit shifts offsets inside its block, so the block raw text is rewritten as
    a unit and spliced back.
    """
    section_match = re.search(r"<(SECTION_LOGIC_(?:LD|FBD))\b[^>]*>", pou_raw)
    if section_match is None:
        raise ValueError("POU 里没有 SECTION_LOGIC_LD / SECTION_LOGIC_FBD 段")
    section_tag = section_match.group(1)
    section_close = f"</{section_tag}>"
    section_close_at = pou_raw.find(section_close, section_match.end())
    if section_close_at < 0:
        raise ValueError(f"{section_tag} 缺少结束标签")

    by_block: dict[str, list[dict]] = {}
    line_edits: list[dict] = []
    for edit in edits:
        if edit["op"].startswith("line_"):
            line_edits.append(edit)
        else:
            by_block.setdefault(edit["block"], []).append(edit)

    for block_name, block_edits in by_block.items():
        span = find_element_span(pou_raw, "CONTROL_LOGIC_BLOCK", block_name)
        block_raw = span.raw
        for edit in block_edits:
            if edit["op"] == "block_deactive":
                head = find_element_span(block_raw, "CONTROL_LOGIC_BLOCK", block_name)
                new_start = set_start_tag_attr(head.start_tag, "DEACTIVE", yes_no(bool(edit["value"])))
                block_raw = replace_slice(block_raw, 0, head.tag_end, new_start)
            else:
                block_raw = apply_pin_edit(block_raw, edit["dir"], edit["pin"], edit["op"], edit["value"])
        pou_raw = replace_slice(pou_raw, span.start, span.end, block_raw)

    for edit in line_edits:
        if edit["op"] == "line_remove":
            span = find_element_span(pou_raw, "CONTROL_LOGIC_LINE", edit["line"])
            trimmed = pou_raw[: span.start].rstrip(" \t")
            trailing = pou_raw[span.end :]
            if trimmed.endswith("\n") and trailing.startswith("\n"):
                trailing = trailing[1:]
            pou_raw = trimmed + trailing
        elif edit["op"] == "line_update":
            span = find_element_span(pou_raw, "CONTROL_LOGIC_LINE", edit["line"]["name"])
            pou_raw = replace_slice(pou_raw, span.start, span.end, line_element(edit["line"]))
        elif edit["op"] == "line_add":
            close_at = pou_raw.find(section_close)
            indent_match = re.search(r"\n([ \t]*)<CONTROL_LOGIC_(?:BLOCK|LINE)\b", pou_raw)
            indent = indent_match.group(1) if indent_match else "    "
            insert = f"\n{indent}{line_element(edit['line'])}"
            pou_raw = replace_slice(pou_raw, close_at, close_at, insert.lstrip("\n") if pou_raw[:close_at].endswith("\n") else insert)
    return pou_raw


# --------------------------------------------------------------------------
# read-only views and the symbol table
# --------------------------------------------------------------------------


def struct_index(structs: list[dict]) -> dict[str, dict]:
    return {struct["name"]: struct for struct in structs}


def base_datatype(datatype: str) -> tuple[str, bool]:
    """Split `Motor_Data[16]` into ("Motor_Data", True)."""
    match = xt.ARRAY_DATATYPE_RE.match(datatype or "")
    if match:
        return match.group(1), True
    return (datatype or "").strip(), False


def build_symbols(variables: list[dict], structs: list[dict]) -> dict[str, dict]:
    """Flatten every variable into dotted paths, arrays normalized to `[]`.

    Array elements are written expanded in the file but only the parent member
    carries a DESC, so normalizing `WhlX_m[3]` to `WhlX_m[]` is what makes a
    hover over an indexed member show anything at all.
    """
    index = struct_index(structs)
    symbols: dict[str, dict] = {}

    def walk(path: str, datatype: str, desc: str, depth: int, owner: str) -> None:
        if len(symbols) >= MAX_SYMBOLS or depth > MAX_SYMBOL_DEPTH:
            return
        base, is_array = base_datatype(datatype)
        key = path + "[]" if is_array else path
        symbols[key] = {
            "path": key,
            "datatype": datatype,
            "desc": desc,
            "unit": unit_of(path.rsplit(".", 1)[-1], desc),
            "struct": base if base in index else "",
            "root": owner,
        }
        struct = index.get(base)
        if struct is None:
            return
        for member in struct["members"]:
            member_name = member["name"]
            if ARRAY_INDEX_RE.search(member_name):
                continue  # expanded array child; the parent already covered it
            walk(f"{key}.{member_name}", member.get("datatype", ""), member.get("desc", ""), depth + 1, owner)

    for var in variables:
        walk(var["name"], var.get("datatype", ""), var.get("desc", ""), 0, var["name"])
    return symbols


def collect_function_block_interfaces(root) -> dict[str, dict]:
    """Pin declarations, in order, for every function block defined in the project.

    Order is the whole point: a Kecon ST call reads like named arguments, so the
    order looks optional.  It is not -- listing pins out of declaration order
    fails the build with one FBDError id=769 per call site, carrying no line
    number and naming no pin.  Shipping the order in the symbol table lets an
    editor expand a correct call instead of leaving it to memory.
    """
    blocks: dict[str, dict] = {}
    for elem in root.iter(xt.POU_TAGS["function-block"]):
        name = xt.attr(elem, "NAME")
        if not name:
            continue
        sections = {"input": "SECTION_VAR_INPUT", "output": "SECTION_VAR_OUTPUT", "internal": "SECTION_VAR_INTERNAL"}
        record: dict[str, object] = {"name": name, "desc": xt.attr(elem, "DESC")}
        for key, tag in sections.items():
            record[key + "s"] = [
                {
                    "name": xt.attr(pin, "NAME"),
                    "datatype": xt.attr(pin, "DATATYPE"),
                    "desc": xt.attr(pin, "DESC"),
                    "unit": unit_of(xt.attr(pin, "NAME"), xt.attr(pin, "DESC")),
                }
                for pin in elem.findall("./" + tag)
            ]
        blocks[name] = record
    return blocks


def render_declarations(variables: list[dict], structs: list[dict]) -> str:
    """A pseudo-ST declaration file: gives a plain editor something to complete against."""
    out: list[str] = [
        "(* ============================================================ *)",
        "(* 声明速查（导出产物，只读）                                        *)",
        "(* 由 xcskr_workspace.py export-workspace 生成，改这里不会回灌到工程。 *)",
        "(* 存在的意义：让编辑器的词法补全能补出变量名与成员名。               *)",
        "(* ============================================================ *)",
        "",
        "TYPE",
    ]
    for struct in structs:
        out.append(f"    (* {struct['desc']} *)" if struct.get("desc") else "")
        out.append(f"    {struct['name']} : STRUCT")
        for member in struct["members"]:
            if ARRAY_INDEX_RE.search(member["name"]):
                continue
            desc = member.get("desc", "")
            comment = f"  (* {desc} *)" if desc else ""
            out.append(f"        {member['name']} : {member.get('datatype', '')};{comment}")
        out.append("    END_STRUCT")
        out.append("")
    out.append("END_TYPE")
    out.append("")
    out.append("VAR_GLOBAL")
    for var in variables:
        desc = var.get("desc", "")
        comment = f"  (* {desc} *)" if desc else ""
        out.append(f"    {var['name']} : {var.get('datatype', '')};{comment}")
    out.append("END_VAR")
    out.append("")
    return "\n".join(out)


def render_variables_md(variables: list[dict]) -> str:
    out = ["# 变量总表（导出产物，只读）", "", f"共 {len(variables)} 个顶层变量。改动请用 `xcskr_tool.py add-variable` / `set-attrs`。", "", "| 变量 | 类型 | 说明 |", "|---|---|---|"]
    for var in variables:
        desc = (var.get("desc") or "").replace("|", "\\|")
        out.append(f"| `{var['name']}` | `{var.get('datatype', '')}` | {desc} |")
    out.append("")
    return "\n".join(out)


def render_structs_md(structs: list[dict]) -> str:
    total = sum(len(struct["members"]) for struct in structs)
    out = [
        "# 结构体总表（导出产物，只读）",
        "",
        f"共 {len(structs)} 个结构体、{total} 个成员（含数组展开子项）。",
        "数组成员在工程文件里是展开写的，且只有父成员带 DESC——下表只列父成员。",
        "",
    ]
    for struct in structs:
        out.append(f"## {struct['name']}")
        if struct.get("desc"):
            out.append("")
            out.append(struct["desc"])
        out.append("")
        out.append("| 成员 | 类型 | 单位 | 说明 |")
        out.append("|---|---|---|---|")
        for member in struct["members"]:
            if ARRAY_INDEX_RE.search(member["name"]):
                continue
            desc = (member.get("desc") or "").replace("|", "\\|")
            unit = unit_of(member["name"], member.get("desc", ""))
            out.append(f"| `{member['name']}` | `{member.get('datatype', '')}` | {unit} | {desc} |")
        out.append("")
    return "\n".join(out)


def render_tasks_md(tasks: list[dict]) -> str:
    out = [
        "# 任务与执行顺序（导出产物，只读）",
        "",
        "程序按文档顺序执行，所以下表的顺序是功能性的，不是排版。",
        "优先级：启动 > 事件 > 周期 > 主任务，高优先级任务会抢占低优先级任务。",
        "",
    ]
    for task in tasks:
        cycle = f"，周期 {task['cycle_ms']} ms" if task.get("cycle_ms") else ""
        out.append(f"## {task.get('kind', '')} 任务 ID={task.get('id', '')}{cycle}")
        if task.get("desc"):
            out.append("")
            out.append(task["desc"])
        out.append("")
        for i, program in enumerate(task.get("programs", []), 1):
            lang = xt.LOGIC_LANG_HINTS.get(program.get("logic_lang", ""), "")
            out.append(f"{i}. `{program['name']}` （{lang}）{('— ' + program['desc']) if program.get('desc') else ''}")
        out.append("")
    return "\n".join(out)


def render_hardware_tsv(rows: list[dict]) -> str:
    columns = ["name", "datatype", "enable", "desc"]
    out = ["\t".join(columns)]
    for row in rows:
        out.append("\t".join(str(row.get(column, "")).replace("\t", " ") for column in columns))
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def collect_workspace_items(root, text: str) -> list[dict]:
    """Decide the file for every POU, carrying execution order into the name."""
    items: list[dict] = []
    graphic = xt.collect_graphic_pous(root)
    graphic_by_key = {(record["pou_type"], record["name"]): record for record in graphic["pous"]}

    seen_dirs: dict[str, int] = {}
    scheme = xt.collect_control_scheme(root, text, "none", None, Path("."))
    for task in scheme["tasks"]:
        directory = task_dir_name(task, seen_dirs)
        for order, program in enumerate(task.get("programs", []), 1):
            name = program["name"]
            key = ("program", name)
            safe = xt.safe_filename(name)
            if key in graphic_by_key:
                rel = f"{DIR_PROGRAMS}/{directory}/{order:02d}_{safe}.graph.json"
                items.append({"kind": "graph", "pou_type": "program", "pou": name, "file": rel})
            else:
                rel = f"{DIR_PROGRAMS}/{directory}/{order:02d}_{safe}.st"
                items.append({"kind": "st", "pou_type": "program", "pou": name, "file": rel})

    for pou_type in ("function-block", "function"):
        tag = xt.POU_TAGS[pou_type]
        for elem in root.iter(tag):
            name = xt.attr(elem, "NAME")
            safe = xt.safe_filename(name)
            if (pou_type, name) in graphic_by_key:
                rel = f"{DIR_FUNCTION_BLOCKS}/{safe}.graph.json"
                items.append({"kind": "graph", "pou_type": pou_type, "pou": name, "file": rel})
            else:
                rel = f"{DIR_FUNCTION_BLOCKS}/{safe}.st"
                items.append({"kind": "st", "pou_type": pou_type, "pou": name, "file": rel})
    return items


def export_workspace(project: Path, workspace: Path, encoding: str, force: bool) -> int:
    text = xt.read_text(project, encoding)
    root = xt.parse_xml(text)
    manifest_path = workspace / MANIFEST_NAME
    previous: list[str] = []

    if manifest_path.exists():
        previous = [item["file"] for item in
                    json.loads(read_workspace_file(manifest_path)).get("items", [])]

    if manifest_path.exists():
        old = json.loads(read_workspace_file(manifest_path))
        dirty = [
            item["file"]
            for item in old.get("items", [])
            if (workspace / item["file"]).exists() and sha256_path(workspace / item["file"]) != item["sha256"]
        ]
        if dirty and not force:
            print("ERROR: 工作区里有尚未回灌的改动，导出会覆盖它们：", file=sys.stderr)
            for name in dirty:
                print(f"  {name}", file=sys.stderr)
            print("先跑 import-workspace 回灌，或确认要丢弃后加 --force。", file=sys.stderr)
            return 2
        if dirty and force:
            # --force means "overwrite them", not "they were worthless".  A whole
            # session's editing can sit in these files, and once the export runs
            # the only copy is gone.  Park them where they can be diffed back in.
            attic = workspace / DISCARDED_DIR / next_attic_name(workspace)
            for name in dirty:
                target = attic / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(workspace / name, target)
            print(f"Discarded={len(dirty)} -> {attic}")
            for name in dirty:
                print(f"  {name}")

    items = collect_workspace_items(root, text)
    graphic = xt.collect_graphic_pous(root)
    graphic_by_key = {(record["pou_type"], record["name"]): record for record in graphic["pous"]}

    for item in items:
        target = workspace / item["file"]
        if item["kind"] == "st":
            # raw_st_for_pou already unescapes the attribute; decoding twice
            # would turn a literal &amp;amp; in the source into a bare &.
            content = xt.raw_st_for_pou(text, xt.pou_tag(item["pou_type"]), item["pou"])
            write_workspace_st(target, content)
        else:
            record = graphic_by_key[(item["pou_type"], item["pou"])]
            write_json_file(target, graph_to_json(record))
        item["sha256"] = sha256_path(target)

    # Reordering or renaming a POU changes its `NN_` prefix, so the previous
    # export's file is left behind under the old name.  An orphan is worse than
    # clutter: `import-workspace` only walks the manifest, so edits made to the
    # stale copy are silently ignored -- changed nothing, reported nothing.
    # Only files this tool wrote before (they were in the previous manifest) are
    # removed; anything a human added is left alone.
    current = {item["file"] for item in items}
    for name in previous:
        if name in current:
            continue
        stale = workspace / name
        if stale.exists():
            stale.unlink()
            print(f"Pruned={name}")

    # read-only views
    variables = xt.collect_variables(root)
    structs = xt.collect_user_structs(root)
    scheme = xt.collect_control_scheme(root, text, "none", None, Path("."))
    readonly = workspace / DIR_READONLY
    write_workspace_file(readonly / "变量.md", render_variables_md(variables))
    write_workspace_file(readonly / "结构体.md", render_structs_md(structs))
    write_workspace_file(readonly / "任务.md", render_tasks_md(scheme["tasks"]))
    write_workspace_file(readonly / "硬件标签.tsv", render_hardware_tsv(xt.collect_hardware_tag_rows(root)))
    write_workspace_st(readonly / "声明.st", render_declarations(variables, structs))
    symbols = build_symbols(variables, structs)
    function_blocks = collect_function_block_interfaces(root)
    write_json_file(
        readonly / "符号表.json",
        {
            "schema": SCHEMA_VERSION,
            "_说明": [
                "导出产物，供编辑器做悬停提示与补全，改这里不会回灌到工程。",
                "symbols 的键是点分路径，数组下标一律归一化成 []（工程里数组成员是展开写的，",
                "且只有父成员带 DESC，不归一化就会让 CFG.WhlX_m[3] 这种悬停查不到东西）。",
                "function_blocks 的引脚按声明顺序排列——顺序不是可选的，错了编译会报 FBDError 769。",
            ],
            "symbols": symbols,
            "function_blocks": function_blocks,
        },
    )

    manifest = {
        "schema": SCHEMA_VERSION,
        "project_name": project.name,
        "project_sha256": sha256_path(project),
        "project_encoding": encoding,
        "newline_style": xt.project_newline_style(text),
        "items": items,
    }
    write_json_file(manifest_path, manifest)
    write_workspace_file(workspace / "README.md", render_workspace_readme(project, items, symbols))

    st_count = sum(1 for item in items if item["kind"] == "st")
    graph_count = len(items) - st_count
    print(f"Workspace={workspace}")
    print(f"Exported={len(items)} (st={st_count}, graph={graph_count})")
    print(f"Symbols={len(symbols)}")
    print(f"ProjectSha256={manifest['project_sha256'][:16]}")
    return 0


def render_workspace_readme(project: Path, items: list[dict], symbols: dict) -> str:
    return "\n".join(
        [
            f"# {project.name} 文本工作区",
            "",
            "由 `xcskr_workspace.py export-workspace` 生成。**编辑这里的 `.st` 与 `.graph.json`，",
            "然后跑 `import-workspace` 回灌到 `.xcskr`。**",
            "",
            "## 铁律",
            "",
            "1. **回灌时 xRobotDesigner 必须是关闭的。** GUI 打开工程后内存里是一份副本，",
            "   点一次保存就整份覆盖，会把回灌的改动无声冲掉。VSCode 不占锁，不用关。",
            "2. `只读/` 下的文件是导出产物，改了不会回灌，每次导出都会被重写。",
            "3. `manifest.json` 记着导出那一刻工程文件的 sha256。工程若被改过，回灌会直接拒绝，",
            "   要求重新导出——这是防止覆盖别人改动的唯一闸门，不要绕过它。",
            "4. **组态改动一次做完再导出。** 顺序是「组态改完 → 导出 → 改 ST → 回灌」。",
            "   中途插一条组态改动，工程的 sha 就变了，回灌会被闸门拒绝，而这时唯一的出路",
            "   是 `export-workspace --force`，它会覆盖工作区里还没回灌的 ST。",
            f"   真走到这一步也不会丢：`--force` 会先把要覆盖的文件抄进 `{DISCARDED_DIR}/NNN/`，",
            "   diff 回来即可。那个目录是本地救援用的，不进 git。",
            "",
            "## 目录",
            "",
            f"- `{DIR_PROGRAMS}/<任务>/NN_<名>.st` —— 程序，`NN` 是任务内执行顺序（顺序是功能性的）",
            f"- `{DIR_PROGRAMS}/<任务>/NN_<名>.graph.json` —— 图形程序（LD/FBD）",
            f"- `{DIR_FUNCTION_BLOCKS}/` —— 功能块",
            f"- `{DIR_READONLY}/` —— 变量、结构体、任务、硬件标签、声明速查、符号表",
            "",
            f"当前：{len(items)} 个 POU 文件，{len(symbols)} 条符号。",
            "",
            "## 图形程序能改什么",
            "",
            "\n".join(f"- {line}" for line in GRAPH_NOTE),
            "",
        ]
    )


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------


def import_workspace(project: Path, workspace: Path, encoding: str, dry_run: bool, no_backup: bool) -> int:
    manifest_path = workspace / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"ERROR: 找不到 {manifest_path}；先跑 export-workspace。", file=sys.stderr)
        return 2
    manifest = json.loads(read_workspace_file(manifest_path))
    if manifest.get("schema") != SCHEMA_VERSION:
        print(f"ERROR: manifest schema {manifest.get('schema')} 与本工具 {SCHEMA_VERSION} 不符，请重新导出。", file=sys.stderr)
        return 2

    current_sha = sha256_path(project)
    if current_sha != manifest.get("project_sha256"):
        print("ERROR: 工程文件在导出之后被改过（多半是 GUI 保存过），拒绝回灌。", file=sys.stderr)
        print(f"  导出时 sha256 = {manifest.get('project_sha256')}", file=sys.stderr)
        print(f"  当前   sha256 = {current_sha}", file=sys.stderr)
        print("请重新 export-workspace，并把工作区里的改动手工合并过去。", file=sys.stderr)
        return 3

    text = xt.read_text(project, encoding)
    root = xt.parse_xml(text)
    graphic_by_key = {
        (record["pou_type"], record["name"]): record for record in xt.collect_graphic_pous(root)["pous"]
    }

    changed: list[dict] = []
    missing: list[str] = []
    for item in manifest["items"]:
        path = workspace / item["file"]
        if not path.exists():
            missing.append(item["file"])
            continue
        if sha256_path(path) != item["sha256"]:
            changed.append(item)
    if missing:
        print("ERROR: 工作区缺少这些文件（被删或被改名了）：", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
        print("改名会让回灌找不到对应 POU；请恢复文件名，或重新导出。", file=sys.stderr)
        return 2

    if not changed:
        print("NoChanges=1")
        return 0

    refusals: list[str] = []
    applied: list[str] = []
    new_text = text
    for item in changed:
        path = workspace / item["file"]
        tag = xt.pou_tag(item["pou_type"])
        span = xt.find_named_span(new_text, tag, item["pou"])
        if item["kind"] == "st":
            st = read_workspace_file(path)
            new_pou = xt.replace_section_logic_raw(span.raw, st, "auto", manifest.get("newline_style", "literal"))
            applied.append(f"ST  {item['pou_type']}:{item['pou']}  ({len(st)} 字符)")
        else:
            record = graphic_by_key.get((item["pou_type"], item["pou"]))
            if record is None:
                refusals.append(f"{item['pou']}: 工程里已经不是图形程序了，请重新导出")
                continue
            old_graph = graph_to_json(record)
            new_graph = json.loads(read_workspace_file(path))
            edits, block_refusals = diff_graph(old_graph, new_graph, item["pou"])
            refusals.extend(block_refusals)
            if block_refusals or not edits:
                continue
            new_pou = apply_graph_edits(span.raw, edits)
            summary: dict[str, int] = {}
            for edit in edits:
                summary[edit["op"]] = summary.get(edit["op"], 0) + 1
            detail = ", ".join(f"{op}x{count}" for op, count in sorted(summary.items()))
            applied.append(f"图形 {item['pou_type']}:{item['pou']}  ({detail})")
        new_text = xt.replace_span(new_text, span, new_pou)

    if refusals:
        print("ERROR: 下列改动被拒绝，未写入任何内容：", file=sys.stderr)
        for note in refusals:
            print(f"  {note}", file=sys.stderr)
        return 4

    new_text = xt.remove_empty_section_logic_name_attrs(new_text)
    xt.parse_xml(new_text)

    if dry_run:
        print("DRY_RUN=OK")
        for note in applied:
            print(f"  {note}")
        print(f"WouldApply={len(applied)}")
        return 0

    backup = None if no_backup else xt.make_backup(project)
    xt.write_text(project, new_text, encoding)
    for item in changed:
        item["sha256"] = sha256_path(workspace / item["file"])
    manifest["project_sha256"] = sha256_path(project)
    write_json_file(manifest_path, manifest)

    print(f"Backup={backup}" if backup else "Backup=SKIPPED")
    for note in applied:
        print(f"  {note}")
    print(f"Applied={len(applied)}")
    print("提醒：改完请在 xRobotDesigner 里编译确认；静态检查只能证明文件结构没坏。")
    return 0



DISCARDED_DIR = ".discarded"


def next_attic_name(workspace: Path) -> str:
    """Pick the next numbered folder under `.discarded/`.

    Numbered rather than timestamped so the tool stays free of a clock -- the
    scripts here are run in tests and in cron jobs where wall time is not a
    dependable source of unique names.
    """
    root = workspace / DISCARDED_DIR
    used = []
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and child.name.isdigit():
                used.append(int(child.name))
    return f"{(max(used) + 1) if used else 1:03d}"


def status_workspace(project: Path, workspace: Path) -> int:
    manifest_path = workspace / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"ERROR: 找不到 {manifest_path}", file=sys.stderr)
        return 2
    manifest = json.loads(read_workspace_file(manifest_path))
    current = sha256_path(project)
    in_sync = current == manifest.get("project_sha256")
    print(f"Project={project}")
    print(f"ProjectChangedSinceExport={'NO' if in_sync else 'YES'}")
    rows = []
    for item in manifest["items"]:
        path = workspace / item["file"]
        if not path.exists():
            state = "缺失"
        elif sha256_path(path) != item["sha256"]:
            state = "已修改"
        else:
            state = "未改"
        if state != "未改":
            rows.append((state, item["file"]))
    print(f"ChangedFiles={len(rows)}")
    for state, name in rows:
        print(f"  {state}  {name}")
    return 0


# --------------------------------------------------------------------------
# check: validators reported as file:line:col so an editor can jump to them
# --------------------------------------------------------------------------

TOOL_SCRIPT = Path(__file__).resolve().parent / "xcskr_tool.py"

# Project-wide validators.  None of them can name a line in a .st file, so they
# are anchored on the project itself and reported as a summary; their value is
# the pass/fail, not a location.
PROJECT_VALIDATORS = [
    ("validate-datatypes", ["--strict"]),
    ("validate-st-format", ["--strict"]),
    ("validate-hardware-bindings", []),
    ("validate-canopen-command-ids", []),
    ("validate-controller-support", []),
    ("validate-desc-length", ["--strict"]),
    ("validate-desc-drift", ["--strict"]),
    ("validate-array-index", []),
    ("validate-modbus-mapping", []),
    ("validate-comment-balance", []),
]


def run_tool(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL_SCRIPT), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def problem(path: Path, line: int, severity: str, message: str) -> str:
    return f"{path}:{line}:1: {severity}: {message}"


def check_workspace(project: Path, workspace: Path, align_script: Path | None, install_dir: str | None) -> int:
    manifest_path = workspace / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"ERROR: 找不到 {manifest_path}；先跑 export-workspace。", file=sys.stderr)
        return 2
    manifest = json.loads(read_workspace_file(manifest_path))
    st_files = {
        (item["pou_type"], item["pou"]): workspace / item["file"]
        for item in manifest["items"]
        if item["kind"] == "st"
    }

    problems = 0

    # -- function block call order: the one check that knows a line -----------
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp) / "fb.json"
        args = ["validate-fb-calls", "--project", str(project), "--format", "json", "--output", str(out)]
        if install_dir:
            args += ["--install-dir", install_dir]
        result = run_tool(args)
        if out.exists():
            for row in json.loads(out.read_text(encoding="utf-8")):
                target = st_files.get((row.get("pou_type", ""), row.get("pou", "")))
                message = f"功能块 {row.get('block', '')} 调用引脚顺序错误：{row.get('problem', '')}"
                if target is None:
                    print(problem(project, 1, "error", f"{row.get('pou', '')}: {message}"))
                else:
                    print(problem(target, int(row.get("line", 1) or 1), "error", message))
                problems += 1
        elif result.returncode not in (0, 1):
            print(problem(project, 1, "error", f"validate-fb-calls 执行失败：{result.stderr.strip()[:200]}"))
            problems += 1

    # -- comment alignment: counts per file, line numbers only for overflow ---
    if align_script is not None and align_script.exists():
        for target in sorted(st_files.values()):
            if not target.exists() or target.stat().st_size == 0:
                continue
            result = subprocess.run(
                [sys.executable, str(align_script), "--check", str(target)],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            for raw in result.stdout.splitlines():
                match = re.search(r":\s*(\d+)\s*行注释需要调整", raw)
                if match and int(match.group(1)):
                    print(problem(target, 1, "warning", f"{match.group(1)} 行注释需要对齐（跑「对齐注释」任务修复）"))
                    problems += 1
                overflow = re.search(r"警告 第 (\d+) 行 (.+)", raw)
                if overflow:
                    print(problem(target, int(overflow.group(1)), "warning", overflow.group(2).strip()))
                    problems += 1

    # -- project-wide validators ---------------------------------------------
    print("")
    print("=== 工程级校验 ===")
    for name, extra in PROJECT_VALIDATORS:
        args = [name, "--project", str(project), *extra]
        if install_dir and name == "validate-controller-support":
            args += ["--install-dir", install_dir]
        result = run_tool(args)
        state = "OK" if result.returncode == 0 else "FAIL"
        print(f"  {name:34} {state}")
        if result.returncode != 0:
            for raw in (result.stdout + result.stderr).splitlines()[:12]:
                print(f"      {raw}")
            print(problem(project, 1, "error", f"{name} 未通过"))
            problems += 1

    print("")
    print(f"Problems={problems}")
    if problems:
        print("提醒：静态检查只能证明文件结构没坏；最终以 xRobotDesigner 里编译为准。")
    return 1 if problems else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", required=True, type=Path, help="目标 .xcskr 工程")
    common.add_argument("--workspace", required=True, type=Path, help="文本工作区目录")
    common.add_argument("--encoding", default=xt.DEFAULT_ENCODING, help="工程文件编码，默认 gbk")

    p = sub.add_parser("export-workspace", parents=[common], help="把工程摊成可编辑的文本工作区")
    p.add_argument("--force", action="store_true", help="即使工作区有未回灌的改动也覆盖")
    p.set_defaults(func=lambda a: export_workspace(a.project, a.workspace, a.encoding, a.force))

    p = sub.add_parser("import-workspace", parents=[common], help="把工作区的改动回灌进工程（单次写入）")
    p.add_argument("--dry-run", action="store_true", help="只报告将要改什么，不写文件")
    p.add_argument("--no-backup", action="store_true", help="不生成时间戳备份")
    p.set_defaults(func=lambda a: import_workspace(a.project, a.workspace, a.encoding, a.dry_run, a.no_backup))

    p = sub.add_parser("status-workspace", parents=[common], help="列出工作区里改过的文件与工程是否漂移")
    p.set_defaults(func=lambda a: status_workspace(a.project, a.workspace))

    p = sub.add_parser(
        "check-workspace",
        parents=[common],
        help="跑全套校验，能定位到行的按 文件:行:列 输出，供编辑器的问题面板跳转",
    )
    p.add_argument("--align-script", type=Path, help="align_st_comments.py 路径，给出后一并检查注释对齐")
    p.add_argument("--install-dir", help="xRobotDesigner 安装目录，用于功能块库与控制器能力表")
    p.set_defaults(func=lambda a: check_workspace(a.project, a.workspace, a.align_script, a.install_dir))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
