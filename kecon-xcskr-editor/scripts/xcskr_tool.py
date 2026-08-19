#!/usr/bin/env python3
"""Kecon xRobotDesigner .xcskr inspection and safe-edit utility.

Observed .xcskr projects are GBK-encoded XML files.  xRobotDesigner stores
ST source code in XML attributes named SECTION_LOGIC_ST CONTENT.  In raw
XML, line breaks inside ST can be literal LF characters saved by the GUI or
numeric character references such as &#10;.  Re-serializing the whole document
through an XML library can flatten ST code and make the IDE show empty or
one-line logic.

This tool therefore uses XML parsing for inspection, but raw XML span
replacement for ST/POU edits.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ENCODING = "gbk"
POU_TAGS = {
    "program": "PROGRAM",
    "function-block": "FUNCTION_BLOCK",
    "function": "FUNCTION",
}

# Graphical logic sections.  LOGIC_LANG on a POU is only a hint; the authoritative
# language is the section tag actually present under the POU.
GRAPHIC_SECTION_TAGS = {
    "SECTION_LOGIC_LD": "ld",
    "SECTION_LOGIC_FBD": "fbd",
}
# Verified against the official Kecon sample projects: the LOGIC_LANG value of a
# POU always agrees with the logic section tag actually present under it.
LOGIC_LANG_HINTS = {
    "0": "ld",
    "1": "fbd",
    "2": "st",
}

# CONTROL_BLOCK_CONNECTION is how xRobotDesigner records a wired graphical pin.
# CONNECTION_TYPE="1" means CONNECTION_VALUE is a variable / tag operand,
# CONNECTION_TYPE="2" means it is the NAME of a CONTROL_LOGIC_LINE in the same
# section.  The CONNECTION_PIN attribute seen on some V5.1 FBD pins is empty in
# every observed project and carries no binding.
CONNECTION_TYPE_VARIABLE = "1"
CONNECTION_TYPE_LINE = "2"
CONNECTION_KINDS = {"1": "variable", "2": "line"}

# Literal a GUI-created scalar variable receives when the user keeps the default.
# Containers (arrays, structs) always get an empty INIT_VALUE.
TYPE_DEFAULT_INIT = {
    "BOOL": "OFF",
    "BYTE": "0", "WORD": "0", "DWORD": "0", "LWORD": "0",
    "SINT": "0", "USINT": "0", "INT": "0", "UINT": "0",
    "DINT": "0", "UDINT": "0", "LINT": "0", "ULINT": "0",
    "REAL": "0.000", "LREAL": "0.000",
}
AUTO_INIT = "@auto"

# IEC 61131-3 elementary types accepted for VARIABLE / USER_STRUCT_MEMBER DATATYPE.
# CANopen object dictionary types (uint8, int32, ...) live in a different namespace
# on HARDWARE_CAN_SLAVER_OBJECT and are deliberately not part of this set.
BASE_DATATYPES = {
    "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
    "SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT",
    "REAL", "LREAL",
    "TIME", "DATE", "TIME_OF_DAY", "TOD", "DATE_AND_TIME", "DT",
    "STRING", "WSTRING",
}

# Attribute defaults observed on GUI-created nodes.  Attribute order in the file is
# alphabetical, which is what xml_start() reproduces.
VARIABLE_DEFAULT_ATTRS = {
    "COLD_RETAIN": "NO",
    "DESC": "",
    "INIT_VALUE": "",
    "READONLY": "NO",
    "SYSTEM_GENERATE": "NO",
    "VISIBLE": "YES",
}
USER_STRUCT_DEFAULT_ATTRS = {
    "DESC": "",
    "READONLY": "NO",
    "VISIBLE": "YES",
}
USER_STRUCT_MEMBER_DEFAULT_ATTRS = {
    "DESC": "",
    "INIT_VALUE": "",
    "VISIBLE": "YES",
}

# The help lists four task kinds and one priority order: startup beats event,
# event beats cycle, cycle beats main.  Only the first three appear in any
# observed project, so the startup task tag is unknown and task discovery stays
# tag-agnostic rather than filtering on this map.
TASK_TAGS = {
    "main": "MAIN_TASK",
    "event": "EVENT_TASK",
    "cycle": "CYCLE_TASK",
}
TASK_KIND_BY_TAG = {tag: kind for kind, tag in TASK_TAGS.items()}
TASK_PRIORITY = {"startup": 0, "event": 1, "cycle": 2, "main": 3}

# Attributes seen on task start tags.  A cycle period is CYCLE, in milliseconds;
# an event task carries the GUI trigger label in EVENT_NAME.  Anything else in
# this list is speculative and only ever reported, never relied on.
TASK_ATTR_KEYS = [
    "ID", "NAME", "DESC", "CYCLE", "CYCLE_TIME", "INTERVAL", "PRIORITY",
    "EVENT_NAME", "EVENT_TYPE", "ENABLE", "DELAY",
]

# TRIG_CONDITION EVENT_TRIGGER values follow the order the help lists the seven
# trigger kinds in.  Only "0" is confirmed by an observed project, so the rest
# are labelled as inferred and must be set through the GUI dialog when in doubt.
EVENT_TRIGGER_KINDS = {
    "0": "开关量-上升沿 (confirmed)",
    "1": "开关量-下降沿 (inferred)",
    "2": "开关量-上升沿或下降沿 (inferred)",
    "3": "开关量-ON (inferred)",
    "4": "开关量-OFF (inferred)",
    "5": "模拟量条件 (inferred)",
    "6": "EVENT功能块 (inferred)",
}
POU_VAR_SECTIONS = {
    "input": "SECTION_VAR_INPUT",
    "output": "SECTION_VAR_OUTPUT",
    "internal": "SECTION_VAR_INTERNAL",
}
LOGIC_LANG_BY_NAME = {"ld": "0", "fbd": "1", "st": "2"}
GRAPHIC_SECTION_BY_LANG = {"ld": "SECTION_LOGIC_LD", "fbd": "SECTION_LOGIC_FBD"}

# Attribute sets a GUI-created POU carries (verified across the official samples
# and both project controllers).
PROGRAM_DEFAULT_ATTRS = {
    "DESC": "",
    "ENABLE_PSWD": "",
    "ENABLE_SHOW": "YES",
}
FUNCTION_BLOCK_DEFAULT_ATTRS = {
    "DESC": "",
    "ENABLE_PSWD": "",
}

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ARRAY_DATATYPE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*(?:\.\.\s*(\d+)\s*)?\]\s*$")
MAX_GENERATED_MEMBERS = 20000


@dataclass(frozen=True)
class PouSpan:
    tag: str
    name: str
    start: int
    end: int
    raw: str


def read_text(path: Path, encoding: str = DEFAULT_ENCODING) -> str:
    """Read a project without newline translation.

    Observed .xcskr files use bare LF.  Python's default universal-newline
    handling would silently rewrite every line ending on save, changing tens of
    thousands of bytes and the literal line breaks stored inside ST attributes,
    so both directions disable translation and the file stays byte-exact
    wherever it was not deliberately edited.
    """
    return path.read_text(encoding=encoding, newline="")


def write_text(path: Path, text: str, encoding: str = DEFAULT_ENCODING) -> None:
    path.write_text(text, encoding=encoding, newline="")


def document_eol(text: str) -> str:
    return "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"


def to_document_eol(fragment: str, text: str) -> str:
    eol = document_eol(text)
    return fragment if eol == "\n" else normalize_newlines(fragment).replace("\n", eol)


def make_backup(path: Path) -> Path:
    backup = path.with_name(path.name + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(path, backup)
    return backup


def parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def xml_attr_encode(value: str, newline_style: str = "literal") -> str:
    """Encode one attribute value, preserving the project's line break style.

    xRobotDesigner writes ST line breaks three different ways depending on
    version: literal LF, &#10;, or &#x0D;&#x0A; with tabs as &#x09;.  All three
    are read back correctly, so the safe move is to write whatever the target
    file already uses instead of churning the whole attribute.
    """
    value = normalize_newlines(value)
    value = (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    if newline_style == "crlf-numeric":
        return value.replace("\t", "&#x09;").replace("\n", "&#x0D;&#x0A;")
    if newline_style == "numeric":
        return value.replace("\n", "&#10;")
    return value


def detect_newline_style(raw_content: str) -> str:
    if "&#x0D;&#x0A;" in raw_content or "&#x0d;&#x0a;" in raw_content:
        return "crlf-numeric"
    if re.search(r"&#(10|x0*[aA]);", raw_content):
        return "numeric"
    return "literal"


def project_newline_style(text: str) -> str:
    """Dominant ST line break style of the whole project, for empty targets."""
    styles = [
        detect_newline_style(match.group(1))
        for match in re.finditer(r'<SECTION_LOGIC_ST\b[^>]*CONTENT="([^"]*)"', text, flags=re.DOTALL)
        if match.group(1)
    ]
    for candidate in ("crlf-numeric", "numeric"):
        if candidate in styles:
            return candidate
    return "literal"


def decode_xml_attr_fragment(value: str) -> str:
    return html.unescape(value)


def pou_tag(pou_type: str) -> str:
    if pou_type not in POU_TAGS:
        raise ValueError(f"unsupported POU type {pou_type!r}; use one of {sorted(POU_TAGS)}")
    return POU_TAGS[pou_type]


def iter_named_spans(text: str, tag: str) -> Iterable[PouSpan]:
    pattern = re.compile(rf"<{tag}\b[^>]*\bNAME=\"([^\"]*)\"[^>]*>")
    close = f"</{tag}>"
    for match in pattern.finditer(text):
        end = text.find(close, match.end())
        if end < 0:
            raise ValueError(f"{tag} NAME={match.group(1)!r} close tag not found")
        span_end = end + len(close)
        yield PouSpan(tag=tag, name=match.group(1), start=match.start(), end=span_end, raw=text[match.start():span_end])


def find_named_span(text: str, tag: str, name: str) -> PouSpan:
    for span in iter_named_spans(text, tag):
        if span.name == name:
            return span
    raise ValueError(f"{tag} NAME={name!r} not found")


def find_section_logic_raw(pou_raw: str) -> tuple[int, int, str]:
    match = re.search(
        r"<SECTION_LOGIC_ST\b([^>]*)\bCONTENT=\"([^\"]*)\"([^>]*)/>",
        pou_raw,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("SECTION_LOGIC_ST CONTENT not found in POU")
    return match.start(), match.end(), match.group(2)


def replace_section_logic_raw(pou_raw: str, st_text: str, newline_style: str = "auto", fallback_style: str = "literal") -> str:
    start, end, old_raw_content = find_section_logic_raw(pou_raw)
    if newline_style == "auto":
        newline_style = detect_newline_style(old_raw_content) if old_raw_content else fallback_style
    replacement = f'<SECTION_LOGIC_ST CONTENT="{xml_attr_encode(st_text, newline_style)}" />'
    return pou_raw[:start] + replacement + pou_raw[end:]


def remove_empty_section_logic_name_attrs(text: str) -> str:
    return re.sub(
        r"(<SECTION_LOGIC_ST\b[^>]*?)\s+NAME=\"\"(\s*/>)",
        r"\1\2",
        text,
        flags=re.DOTALL,
    )


def replace_span(text: str, span: PouSpan, replacement: str) -> str:
    return text[:span.start] + replacement + text[span.end:]


def read_st_file(path: Path, encoding: str) -> str:
    return path.read_text(encoding=encoding, newline="")


def maybe_write_output(content: str, output: Path | None, encoding: str) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding=encoding, newline="")
    else:
        sys.stdout.write(content)
        if content and not content.endswith("\n"):
            sys.stdout.write("\n")


def format_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    if not rows:
        return ""
    widths = {col: max(len(col), *(len(str(row.get(col, ""))) for row in rows)) for col in columns}
    out = ["  ".join(col.ljust(widths[col]) for col in columns)]
    out.append("  ".join("-" * widths[col] for col in columns))
    for row in rows:
        out.append("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))
    return "\n".join(out)


def collect_pou_rows(root: ET.Element) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for kind, tag in POU_TAGS.items():
        for elem in root.findall(f".//{tag}"):
            sec = elem.find(".//SECTION_LOGIC_ST")
            content = "" if sec is None else sec.get("CONTENT", "")
            rows.append(
                {
                    "type": kind,
                    "name": elem.get("NAME", ""),
                    "logic_lang": elem.get("LOGIC_LANG", ""),
                    "st_len": len(content),
                    "st_lines": content.count("\n") + (1 if content else 0),
                    "inputs": len(elem.findall("SECTION_VAR_INPUT")),
                    "outputs": len(elem.findall("SECTION_VAR_OUTPUT")),
                    "internals": len(elem.findall("SECTION_VAR_INTERNAL")),
                }
            )
    return rows


def graphic_pin_connection(pin: ET.Element) -> dict[str, object]:
    """Return every connection representation observed on a graphical pin.

    xRobotDesigner does not use a single encoding for a wired pin:
    * a CONNECTION_PIN attribute on the pin start tag (seen on V5.1 FBD blocks),
    * a CONTROL_BLOCK_CONNECTION child with CONNECTION_TYPE / CONNECTION_VALUE.
    Both are reported verbatim so callers never have to guess which one a given
    project version uses.  The value key holds the first non-empty of the two.
    """
    conn = pin.find("./CONTROL_BLOCK_CONNECTION")
    child_attrs = {} if conn is None else dict(conn.attrib)
    child_value = child_attrs.get("CONNECTION_VALUE", "")
    connection_pin = attr(pin, "CONNECTION_PIN")
    conn_type = child_attrs.get("CONNECTION_TYPE", "")
    return {
        "type": conn_type,
        "kind": CONNECTION_KINDS.get(conn_type, ""),
        "value": child_value or connection_pin,
        "connection_pin_attr": connection_pin,
        "child_connection": child_attrs,
    }


def pin_connection(pin: ET.Element) -> dict[str, object]:
    """Backwards-compatible alias of graphic_pin_connection."""
    return graphic_pin_connection(pin)


def graphic_pin_row(pin: ET.Element, direction: str = "") -> dict[str, object]:
    return {
        "direction": direction,
        "name": attr(pin, "NAME"),
        "datatype": attr(pin, "DATATYPE"),
        "desc": attr(pin, "DESC"),
        "enabled": attr(pin, "ENABLED"),
        "visible": attr(pin, "VISIBLE"),
        "negated": attr(pin, "NEGATED"),
        "init_value": attr(pin, "INIT_VALUE"),
        "struct": attr(pin, "STRUCT"),
        "min_size": attr(pin, "MIN_SIZE"),
        "connection": graphic_pin_connection(pin),
        "attrs": dict(pin.attrib),
    }


def ld_pin_row(pin: ET.Element) -> dict[str, object]:
    """Backwards-compatible alias of graphic_pin_row."""
    return graphic_pin_row(pin)


def graphic_section_of(pou: ET.Element) -> tuple[str, ET.Element] | None:
    for section_tag in GRAPHIC_SECTION_TAGS:
        section = pou.find("./" + section_tag)
        if section is not None:
            return section_tag, section
    return None


def graphic_block_record(block: ET.Element) -> dict[str, object]:
    inputs = [graphic_pin_row(pin, "input") for pin in block.findall("./BLOCK_PIN_INPUT")]
    outputs = [graphic_pin_row(pin, "output") for pin in block.findall("./BLOCK_PIN_OUTPUT")]
    return {
        "name": attr(block, "NAME"),
        "type": attr(block, "TYPE"),
        "deactive": attr(block, "DEACTIVE"),
        "desc": attr(block, "DESC"),
        "position_type": attr(block, "POSITION_TYPE"),
        "rect_position": attr(block, "RECT_POSITION"),
        "showen": attr(block, "SHOWEN"),
        "attrs": dict(block.attrib),
        "inputs": inputs,
        "outputs": outputs,
        "connected_inputs": sum(1 for pin in inputs if pin["connection"]["value"]),
        "connected_outputs": sum(1 for pin in outputs if pin["connection"]["value"]),
    }


def collect_graphic_pous(
    root: ET.Element,
    pou_name: str | None = None,
    pou_type: str | None = None,
) -> dict[str, object]:
    """Collect every POU that carries an LD or FBD section.

    Covers PROGRAM under CONTROL_SCHEME tasks as well as FUNCTION_BLOCK and
    FUNCTION POUs, because graphical logic is not limited to programs.
    """
    parent = {child: elem for elem in root.iter() for child in elem}
    task_map = dict(TASK_KIND_BY_TAG)
    wanted_tags = [POU_TAGS[pou_type]] if pou_type else list(POU_TAGS.values())
    kind_by_tag = {tag: kind for kind, tag in POU_TAGS.items()}

    pous: list[dict[str, object]] = []
    for tag in wanted_tags:
        for pou in root.iter(tag):
            name = attr(pou, "NAME")
            if pou_name and name != pou_name:
                continue
            found = graphic_section_of(pou)
            if found is None:
                continue
            section_tag, section = found
            blocks = [graphic_block_record(block) for block in section.findall("./CONTROL_LOGIC_BLOCK")]
            lines = [dict(line.attrib) for line in section.findall("./CONTROL_LOGIC_LINE")]
            comments = [dict(comment.attrib) for comment in section.findall("./CONTROL_LOGIC_COMMENT")]
            task = parent.get(pou)
            task_tag = task.tag if task is not None and task.tag in task_map else ""
            record: dict[str, object] = {
                "pou_type": kind_by_tag[tag],
                "name": name,
                "desc": attr(pou, "DESC"),
                "id": attr(pou, "ID"),
                "logic_lang": attr(pou, "LOGIC_LANG"),
                "logic_lang_hint": LOGIC_LANG_HINTS.get(attr(pou, "LOGIC_LANG"), ""),
                "section": section_tag,
                "language": GRAPHIC_SECTION_TAGS[section_tag],
                "task_tag": task_tag,
                "task_kind": task_map.get(task_tag, ""),
                "task_id": attr(task, "ID") if task is not None else "",
                "block_count": len(blocks),
                "line_count": len(lines),
                "comment_count": len(comments),
                "active_block_count": sum(1 for block in blocks if block["deactive"] in ("", "NO")),
                "inactive_block_count": sum(1 for block in blocks if block["deactive"] == "YES"),
                "input_pin_count": sum(len(block["inputs"]) for block in blocks),
                "output_pin_count": sum(len(block["outputs"]) for block in blocks),
                "connected_input_count": sum(int(block["connected_inputs"]) for block in blocks),
                "connected_output_count": sum(int(block["connected_outputs"]) for block in blocks),
                "blocks": blocks,
                "lines": lines,
                "comments": comments,
            }
            pous.append(record)
    if pou_name and not pous:
        raise ValueError(
            "graphical POU NAME=" + repr(pou_name) + " not found (no SECTION_LOGIC_LD / SECTION_LOGIC_FBD)"
        )
    return {"pous": pous, "programs": [record for record in pous if record["pou_type"] == "program"]}


def collect_ld_program(root: ET.Element, program_name: str | None = None) -> dict[str, object]:
    """Backwards-compatible wrapper: LD/FBD programs only."""
    package = collect_graphic_pous(root, pou_name=program_name, pou_type="program")
    return {"programs": package["programs"]}


def graphic_block_rows(package: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pou in package.get("pous", package.get("programs", [])):
        for block in pou["blocks"]:
            rows.append(
                {
                    "pou": pou["name"],
                    "program": pou["name"],
                    "pou_type": pou["pou_type"],
                    "lang": pou["language"],
                    "block": block["name"],
                    "type": block["type"],
                    "deactive": block["deactive"],
                    "inputs": len(block["inputs"]),
                    "outputs": len(block["outputs"]),
                    "connected_inputs": block["connected_inputs"],
                    "connected_outputs": block["connected_outputs"],
                    "rect": block["rect_position"],
                }
            )
    return rows


def graphic_pin_rows(package: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pou in package.get("pous", package.get("programs", [])):
        for block in pou["blocks"]:
            for pin in list(block["inputs"]) + list(block["outputs"]):
                rows.append(
                    {
                        "pou": pou["name"],
                        "block": block["name"],
                        "dir": pin["direction"],
                        "pin": pin["name"],
                        "datatype": pin["datatype"],
                        "enabled": pin["enabled"],
                        "negated": pin["negated"],
                        "init_value": pin["init_value"],
                        "connection": pin["connection"]["value"],
                        "conn_kind": pin["connection"]["kind"],
                        "desc": pin["desc"],
                    }
                )
    return rows


def ld_block_summary_rows(ld_package: dict[str, object]) -> list[dict[str, object]]:
    """Backwards-compatible alias of graphic_block_rows."""
    return graphic_block_rows(ld_package)


def raw_st_content_by_name(text: str, tag: str) -> dict[str, str]:
    contents: dict[str, str] = {}
    for span in iter_named_spans(text, tag):
        try:
            _, _, raw_content = find_section_logic_raw(span.raw)
        except ValueError:
            continue
        contents[span.name] = raw_content
    return contents


def has_raw_st_line_breaks(raw_content: str) -> bool:
    lowered = raw_content.lower()
    return "\n" in raw_content or "\r" in raw_content or "&#10;" in raw_content or "&#xa;" in lowered


def collect_downlink_rows(root: ET.Element) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for port in root.findall(".//HARDWARE_DEVICE_DOWNLINK_PORT"):
        objects = port.findall(".//HARDWARE_CAN_SLAVER_OBJECT")
        mappings = port.findall(".//HARDWARE_MODBUS_TAG_MAPPING")
        rows.append(
            {
                "id": port.get("ID", ""),
                "name": port.get("NAME", ""),
                "display": port.get("DISPLAY", ""),
                "physical_id": port.get("PHYSICAL_ID", ""),
                "protocol": port.get("PROTOCOL", ""),
                "type": port.get("TYPE", ""),
                "objects": len(objects),
                "mappings": len(mappings),
            }
        )
    return rows


def collect_slave_object_rows(root: ET.Element, port_id: str | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for port in root.findall(".//HARDWARE_DEVICE_DOWNLINK_PORT"):
        if port_id and port.get("ID") != port_id:
            continue
        for obj in port.findall(".//HARDWARE_CAN_SLAVER_OBJECT"):
            index_raw = obj.get("INDEX", "")
            try:
                index_hex = f"0x{int(index_raw):04X}"
            except ValueError:
                index_hex = ""
            mappings = obj.findall("./HARDWARE_MODBUS_TAG_MAPPING")
            first = mappings[0].get("TAG_NAME", "") if mappings else ""
            rows.append(
                {
                    "port_id": port.get("ID", ""),
                    "port_enable": port.get("ENABLE", ""),
                    "port_display": port.get("DISPLAY", ""),
                    "index": index_raw,
                    "hex": index_hex,
                    "desc": obj.get("DESC", ""),
                    "datatype": obj.get("DATATYPE", ""),
                    "array": obj.get("ARRAY_SIZE", "") if obj.get("ARRAY_FLAG") == "YES" else "",
                    "enable": obj.get("ENABLE", ""),
                    "pdo_index": obj.get("PDO_INDEX", ""),
                    "pdo_desc": obj.get("PDO_DESC", ""),
                    "mappings": len(mappings),
                    "first_mapping": first,
                }
            )
    return rows


def collect_hardware_tag_rows(root: ET.Element, pattern: str | None = None) -> list[dict[str, object]]:
    regex = re.compile(pattern) if pattern else None
    rows: list[dict[str, object]] = []
    parent = {child: elem for elem in root.iter() for child in elem}
    for tag in root.iter("HARDWARE_CHANNEL_TAG"):
        name = tag.get("NAME", "")
        if regex and not regex.search(name):
            continue
        cmd = parent.get(tag)
        group = parent.get(cmd) if cmd is not None else None
        slave = parent.get(group) if group is not None else None
        rows.append(
            {
                "name": name,
                "datatype": tag.get("DATATYPE", ""),
                "enable": tag.get("ENABLE", ""),
                "access": "" if group is None else group.get("CMD_ACCESS_TYPE", ""),
                "index": "" if group is None else group.get("INDEX_ID", ""),
                "sub": "" if group is None else group.get("SUB_INDEX_ID", ""),
                "length": "" if group is None else group.get("OUTPUT_LENGTH", ""),
                "device": "" if slave is None else slave.get("DEVICE_NAME", ""),
                "node": "" if slave is None else slave.get("NODE_ID", ""),
            }
        )
    return rows


def nearest_ancestor(parent: dict[ET.Element, ET.Element], elem: ET.Element, tag: str) -> ET.Element | None:
    node = parent.get(elem)
    while node is not None:
        if node.tag == tag:
            return node
        node = parent.get(node)
    return None


def first_child(elem: ET.Element, tag: str) -> ET.Element | None:
    return next((child for child in elem if child.tag == tag), None)


def collect_canopen_command_id_rows(root: ET.Element, enabled_only: bool = False) -> list[dict[str, object]]:
    """Collect non-empty HARDWARE_CAN_CMD IDs under CANopen master slave nodes."""

    parent = {child: elem for elem in root.iter() for child in elem}
    rows: list[dict[str, object]] = []
    for cmd in root.iter("HARDWARE_CAN_CMD"):
        cmd_id = cmd.get("ID", "")
        if not cmd_id:
            continue
        group = nearest_ancestor(parent, cmd, "HARDWARE_CAN_CMD_GROUP")
        slave = nearest_ancestor(parent, cmd, "HARDWARE_CAN_DEVICE_SLAVE")
        uplink = nearest_ancestor(parent, cmd, "HARDWARE_DEVICE_UPLINK_PORT")
        downlink = nearest_ancestor(parent, cmd, "HARDWARE_DEVICE_DOWNLINK_PORT")
        if group is None or slave is None:
            continue
        channel_tag = first_child(cmd, "HARDWARE_CHANNEL_TAG")
        group_enable = group.get("HARDWARE_GROUP_ENABLE", "")
        if enabled_only and group_enable != "YES":
            continue
        rows.append(
            {
                "cmd_id": cmd_id,
                "port_id": "" if downlink is None else downlink.get("ID", ""),
                "port_name": "" if downlink is None else downlink.get("NAME", ""),
                "port_display": "" if downlink is None else downlink.get("DISPLAY", ""),
                "station": "" if uplink is None else uplink.get("ADDRESS", ""),
                "device": slave.get("DEVICE_NAME", ""),
                "node": slave.get("NODE_ID", ""),
                "group_enable": group_enable,
                "tag_enable": "" if channel_tag is None else channel_tag.get("ENABLE", ""),
                "tag_name": "" if channel_tag is None else channel_tag.get("NAME", ""),
                "index": group.get("INDEX_ID", ""),
                "sub": group.get("SUB_INDEX_ID", ""),
                "mode": group.get("MODE", ""),
                "cycle": group.get("CYCLE_TIME", ""),
            }
        )
    return rows


def output_rows(rows: list[dict[str, object]], columns: list[str], fmt: str, output: Path | None, encoding: str) -> None:
    if fmt == "json":
        content = json.dumps(rows, ensure_ascii=False, indent=2)
        maybe_write_output(content + "\n", output, encoding)
        return
    if fmt == "csv":
        if output is None:
            writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        else:
            with output.open("w", encoding=encoding, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        return
    maybe_write_output(format_table(rows, columns) + "\n", output, encoding)


def cmd_summary(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    print(f"Project={args.project}")
    print(f"Encoding={args.encoding}")
    print(f"RawBytes={args.project.stat().st_size}")
    print(f"RawLines={text.count(chr(10)) + 1}")
    print(f"POUs={len(collect_pou_rows(root))}")
    ports = collect_downlink_rows(root)
    print(f"DownlinkPorts={len(ports)}")
    print(f"SlaveObjects={sum(int(row['objects']) for row in ports)}")
    print(f"SlaveMappings={sum(int(row['mappings']) for row in ports)}")
    return 0


def cmd_list_pous(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows = collect_pou_rows(root)
    output_rows(rows, ["type", "name", "logic_lang", "st_len", "st_lines", "inputs", "outputs", "internals"], args.format, args.output, args.output_encoding)
    return 0


def cmd_export_ld(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    try:
        ld_package = collect_ld_program(root, args.program)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        maybe_write_output(json.dumps(ld_package, ensure_ascii=False, indent=2) + "\n", args.output, args.output_encoding)
        return 0
    rows = ld_block_summary_rows(ld_package)
    output_rows(rows, ["program", "block", "type", "deactive", "inputs", "outputs", "connected_inputs", "connected_outputs", "rect"], args.format, args.output, args.output_encoding)
    return 0


def cmd_extract_st(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    span = find_named_span(text, pou_tag(args.pou_type), args.name)
    _, _, raw_content = find_section_logic_raw(span.raw)
    st = decode_xml_attr_fragment(raw_content)
    maybe_write_output(st, args.output, args.output_encoding)
    return 0


def cmd_replace_st(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    span = find_named_span(text, pou_tag(args.pou_type), args.name)
    st = read_st_file(args.st_file, args.st_encoding)
    new_pou = replace_section_logic_raw(
        span.raw, st, args.newline_style, project_newline_style(text)
    )
    new_text = replace_span(text, span, new_pou)
    new_text = remove_empty_section_logic_name_attrs(new_text)
    parse_xml(new_text)
    if args.dry_run:
        print("DRY_RUN=OK")
        print(f"Target={args.pou_type}:{args.name}")
        print(f"NewSTLength={len(st)}")
        print(f"NewSTLines={st.count(chr(10)) + (1 if st else 0)}")
        return 0
    backup = None if args.no_backup else make_backup(args.project)
    write_text(args.project, new_text, args.encoding)
    print(f"Backup={backup}" if backup else "Backup=SKIPPED")
    print(f"ReplacedST={args.pou_type}:{args.name}")
    return 0


def cmd_copy_pou(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    ref_text = read_text(args.reference, args.encoding)
    tag = pou_tag(args.pou_type)
    ref_span = find_named_span(ref_text, tag, args.name)
    target_span = find_named_span(text, tag, args.target_name or args.name)
    replacement = ref_span.raw
    if args.target_name and args.target_name != args.name:
        replacement = re.sub(r'\bNAME="' + re.escape(args.name) + r'"', f'NAME="{args.target_name}"', replacement, count=1)
    new_text = replace_span(text, target_span, replacement)
    parse_xml(new_text)
    if args.dry_run:
        print("DRY_RUN=OK")
        print(f"CopyPOU={args.pou_type}:{args.name} -> {args.target_name or args.name}")
        return 0
    backup = None if args.no_backup else make_backup(args.project)
    write_text(args.project, new_text, args.encoding)
    print(f"Backup={backup}" if backup else "Backup=SKIPPED")
    print(f"CopiedPOU={args.pou_type}:{args.name}")
    return 0


def cmd_validate_st_format(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    issues: list[str] = []
    rows: list[dict[str, object]] = []
    for kind, tag in POU_TAGS.items():
        raw_content_by_name = raw_st_content_by_name(text, tag)
        for elem in root.findall(f".//{tag}"):
            name = elem.get("NAME", "")
            sec = elem.find(".//SECTION_LOGIC_ST")
            if sec is None:
                continue
            raw_content = raw_content_by_name.get(name, "")
            content = decode_xml_attr_fragment(raw_content) if raw_content else sec.get("CONTENT", "")
            has_line_breaks = has_raw_st_line_breaks(raw_content)
            lines = content.count("\n") + (1 if content else 0)
            statements = content.count(";")
            status = "OK"
            if statements >= args.min_statements and not has_line_breaks:
                status = "WARN"
                issues.append(f"{kind}:{name} has {statements} statements but no raw ST line breaks")
            rows.append({"type": kind, "name": name, "st_len": len(content), "st_lines": lines, "statements": statements, "raw_line_breaks": has_line_breaks, "status": status})
    output_rows(rows, ["type", "name", "st_len", "st_lines", "statements", "raw_line_breaks", "status"], args.format, args.output, args.output_encoding)
    if issues:
        print("ST_FORMAT=WARN")
        for issue in issues:
            print(f" - {issue}")
        return 1 if args.strict else 0
    print("ST_FORMAT=OK")
    return 0


def cmd_list_downlinks(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows = collect_downlink_rows(root)
    output_rows(rows, ["id", "name", "display", "physical_id", "protocol", "type", "objects", "mappings"], args.format, args.output, args.output_encoding)
    return 0


def cmd_list_slave_objects(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows = collect_slave_object_rows(root, args.port_id)
    output_rows(rows, ["port_id", "port_enable", "port_display", "index", "hex", "desc", "datatype", "array", "enable", "pdo_index", "pdo_desc", "mappings", "first_mapping"], args.format, args.output, args.output_encoding)
    return 0


def cmd_export_slave_mappings(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows: list[dict[str, object]] = []
    for port in root.findall(".//HARDWARE_DEVICE_DOWNLINK_PORT"):
        if args.port_id and port.get("ID") != args.port_id:
            continue
        for obj in port.findall(".//HARDWARE_CAN_SLAVER_OBJECT"):
            for mapping in obj.findall("./HARDWARE_MODBUS_TAG_MAPPING"):
                rows.append(
                    {
                        "port_id": port.get("ID", ""),
                        "port_display": port.get("DISPLAY", ""),
                        "index": obj.get("INDEX", ""),
                        "hex": f"0x{int(obj.get('INDEX', '0')):04X}" if obj.get("INDEX", "").isdigit() else "",
                        "offset": mapping.get("OFFSET", ""),
                        "sub": str(int(mapping.get("OFFSET", "0")) + 1) if mapping.get("OFFSET", "").isdigit() else "",
                        "tag_name": mapping.get("TAG_NAME", ""),
                        "datatype": obj.get("DATATYPE", ""),
                        "pdo_index": obj.get("PDO_INDEX", ""),
                        "pdo_desc": obj.get("PDO_DESC", ""),
                    }
                )
    output_rows(rows, ["port_id", "port_display", "index", "hex", "offset", "sub", "tag_name", "datatype", "pdo_index", "pdo_desc"], args.format, args.output, args.output_encoding)
    return 0


def cmd_list_hardware_tags(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows = collect_hardware_tag_rows(root, args.pattern)
    output_rows(rows, ["name", "datatype", "enable", "access", "index", "sub", "length", "device", "node"], args.format, args.output, args.output_encoding)
    return 0


def cmd_validate_canopen_command_ids(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows = collect_canopen_command_id_rows(root, args.enabled_only)
    seen: dict[tuple[str, str] | tuple[str], list[dict[str, object]]] = {}
    for row in rows:
        if args.scope == "port":
            key: tuple[str, str] | tuple[str] = (str(row["port_id"]), str(row["cmd_id"]))
        else:
            key = (str(row["cmd_id"]),)
        seen.setdefault(key, []).append(row)
    duplicate_rows = [row for group in seen.values() if len(group) > 1 for row in group]
    columns = [
        "cmd_id",
        "port_id",
        "port_name",
        "port_display",
        "station",
        "device",
        "node",
        "group_enable",
        "tag_enable",
        "tag_name",
        "index",
        "sub",
        "mode",
        "cycle",
    ]
    if duplicate_rows:
        print("CANOPEN_COMMAND_IDS=FAIL")
        print(f"Checked={len(rows)}")
        print(f"DuplicateRows={len(duplicate_rows)}")
        output_rows(duplicate_rows, columns, args.format, args.output, args.output_encoding)
        return 1
    print("CANOPEN_COMMAND_IDS=OK")
    print(f"Checked={len(rows)}")
    if args.show_all:
        output_rows(rows, columns, args.format, args.output, args.output_encoding)
    return 0


def attr(elem: ET.Element, key: str) -> str:
    return elem.get(key, "")


def attrs_subset(elem: ET.Element, keys: list[str]) -> dict[str, str]:
    return {key.lower(): elem.get(key, "") for key in keys if elem.get(key, "") != ""}


def int_hex(value: str, width: int = 4) -> str:
    try:
        return f"0x{int(value):0{width}X}"
    except (TypeError, ValueError):
        return ""


def safe_filename(name: str, fallback: str = "unnamed") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" ._")
    return cleaned or fallback


def relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def direct_var_rows(elem: ET.Element, tag: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for child in elem.findall(tag):
        rows.append(
            {
                "name": attr(child, "NAME"),
                "datatype": attr(child, "DATATYPE"),
                "desc": attr(child, "DESC"),
                "init_value": attr(child, "INIT_VALUE"),
                "visible": attr(child, "VISIBLE"),
            }
        )
    return rows


def variable_member_tree(elem: ET.Element) -> dict[str, object]:
    return {
        "name": attr(elem, "NAME"),
        "datatype": attr(elem, "DATATYPE"),
        "desc": attr(elem, "DESC"),
        "init_value": attr(elem, "INIT_VALUE"),
        "readonly": attr(elem, "READONLY"),
        "visible": attr(elem, "VISIBLE"),
        "members": [variable_member_tree(child) for child in elem.findall("./VARIABLE_MEMBER")],
    }


def collect_variables(root: ET.Element) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    for container_path in [".//GLOBAL_TAG_CONFIG", ".//TAGCONFIG"]:
        for container in root.findall(container_path):
            for var in container.findall("./VARIABLE"):
                if id(var) in seen:
                    continue
                seen.add(id(var))
                rows.append(
                    {
                        "name": attr(var, "NAME"),
                        "datatype": attr(var, "DATATYPE"),
                        "desc": attr(var, "DESC"),
                        "init_value": attr(var, "INIT_VALUE"),
                        "retain": attr(var, "RETAIN"),
                        "cold_retain": attr(var, "COLD_RETAIN"),
                        "readonly": attr(var, "READONLY"),
                        "visible": attr(var, "VISIBLE"),
                        "enable": attr(var, "ENABLE"),
                        "use": attr(var, "USE"),
                        "type": attr(var, "TYPE"),
                        "members": [variable_member_tree(member) for member in var.findall("./VARIABLE_MEMBER")],
                    }
                )
    return rows


def collect_user_structs(root: ET.Element) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for struct in root.findall(".//USER_DATA_TYPE/USER_STRUCT"):
        rows.append(
            {
                "name": attr(struct, "NAME"),
                "desc": attr(struct, "DESC"),
                "members": [
                    {
                        "name": attr(member, "NAME"),
                        "datatype": attr(member, "DATATYPE"),
                        "desc": attr(member, "DESC"),
                        "init_value": attr(member, "INIT_VALUE"),
                        "visible": attr(member, "VISIBLE"),
                    }
                    for member in struct.findall("./USER_STRUCT_MEMBER")
                ],
            }
        )
    return rows


def raw_st_for_pou(text: str, tag: str, name: str) -> str:
    try:
        span = find_named_span(text, tag, name)
        _, _, raw_content = find_section_logic_raw(span.raw)
    except ValueError:
        return ""
    return decode_xml_attr_fragment(raw_content)


def add_st_payload(
    record: dict[str, object],
    text: str,
    tag: str,
    name: str,
    st_mode: str,
    st_dir: Path | None,
    output_dir: Path,
    subdir: str,
) -> None:
    st = raw_st_for_pou(text, tag, name)
    record["st_len"] = len(st)
    record["st_lines"] = st.count("\n") + (1 if st else 0)
    if st_mode == "inline":
        record["st"] = st
    elif st_mode == "files" and st_dir is not None:
        target = st_dir / subdir / f"{safe_filename(name)}.st"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(st, encoding="utf-8", newline="")
        record["st_file"] = relative_posix(target, output_dir)
    else:
        record["st_file"] = ""


def collect_function_like_pous(
    root: ET.Element,
    text: str,
    kind: str,
    tag: str,
    st_mode: str,
    st_dir: Path | None,
    output_dir: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    subdir = "function-blocks" if kind == "function-block" else "functions"
    for elem in root.findall(f".//{tag}"):
        name = attr(elem, "NAME")
        record: dict[str, object] = {
            "type": kind,
            "name": name,
            "desc": attr(elem, "DESC"),
            "logic_lang": attr(elem, "LOGIC_LANG"),
            "inputs": direct_var_rows(elem, "./SECTION_VAR_INPUT"),
            "outputs": direct_var_rows(elem, "./SECTION_VAR_OUTPUT"),
            "internals": direct_var_rows(elem, "./SECTION_VAR_INTERNAL"),
        }
        add_st_payload(record, text, tag, name, st_mode, st_dir, output_dir, subdir)
        rows.append(record)
    return rows


def collect_control_scheme(root: ET.Element, text: str, st_mode: str, st_dir: Path | None, output_dir: Path) -> dict[str, object]:
    tasks: list[dict[str, object]] = []
    programs: list[dict[str, object]] = []
    for scheme_index, scheme in enumerate(root.findall(".//CONTROL_SCHEME")):
        for task in list(scheme):
            # A task is any _TASK element, or anything already holding programs.
            # Filtering on a fixed tag list would drop the startup task, and
            # requiring programs would drop a task that was just created.
            if not is_task_element(task):
                continue
            task_kind = TASK_KIND_BY_TAG.get(task.tag, task.tag.lower())
            task_record: dict[str, object] = {
                "kind": task_kind,
                "tag": task.tag,
                "id": attr(task, "ID"),
                "name": attr(task, "NAME"),
                "desc": attr(task, "DESC"),
                "cycle_ms": attr(task, "CYCLE"),
                "cycle_time": attr(task, "CYCLE"),
                "event_name": attr(task, "EVENT_NAME"),
                "priority": TASK_PRIORITY.get(task_kind, 9),
                "known_kind": task.tag in TASK_KIND_BY_TAG,
                "attrs": attrs_subset(task, TASK_ATTR_KEYS),
                "trigger_condition": {},
                "programs": [],
            }
            trigger = task.find("./TRIG_CONDITION")
            if trigger is not None:
                trigger_attrs = dict(trigger.attrib)
                trigger_attrs["EVENT_TRIGGER_KIND"] = EVENT_TRIGGER_KINDS.get(
                    trigger_attrs.get("EVENT_TRIGGER", ""), "unknown"
                )
                task_record["trigger_condition"] = trigger_attrs
            for program in task.findall("./PROGRAM"):
                name = attr(program, "NAME")
                program_record: dict[str, object] = {
                    "type": "program",
                    "name": name,
                    "desc": attr(program, "DESC"),
                    "id": attr(program, "ID"),
                    "logic_lang": attr(program, "LOGIC_LANG"),
                    "task_kind": task_kind,
                    "task_id": attr(task, "ID"),
                    "task_tag": task.tag,
                    "scheme_index": scheme_index,
                }
                add_st_payload(program_record, text, "PROGRAM", name, st_mode, st_dir, output_dir, f"programs/{task_kind}-{attr(task, 'ID') or scheme_index}")
                programs.append(program_record)
                task_record["programs"].append(
                    {
                        "name": name,
                        "desc": attr(program, "DESC"),
                        "id": attr(program, "ID"),
                        "logic_lang": attr(program, "LOGIC_LANG"),
                        "st_file": program_record.get("st_file", ""),
                        "st_len": program_record.get("st_len", 0),
                        "st_lines": program_record.get("st_lines", 0),
                    }
                )
            tasks.append(task_record)
    return {"tasks": tasks, "programs": programs}


def collect_hardware_package(root: ET.Element) -> dict[str, object]:
    parent = {child: elem for elem in root.iter() for child in elem}
    downlinks: list[dict[str, object]] = []
    stations: list[dict[str, object]] = []
    slave_objects: list[dict[str, object]] = []
    slave_mappings: list[dict[str, object]] = []
    hardware_tags: list[dict[str, object]] = []

    for port in root.findall(".//HARDWARE_DEVICE_DOWNLINK_PORT"):
        port_record = {
            "id": attr(port, "ID"),
            "name": attr(port, "NAME"),
            "display": attr(port, "DISPLAY"),
            "physical_id": attr(port, "PHYSICAL_ID"),
            "protocol": attr(port, "PROTOCOL"),
            "type": attr(port, "TYPE"),
            "enable": attr(port, "ENABLE"),
            "object_count": len(port.findall(".//HARDWARE_CAN_SLAVER_OBJECT")),
            "mapping_count": len(port.findall(".//HARDWARE_MODBUS_TAG_MAPPING")),
        }
        downlinks.append(port_record)
        for station in port.findall("./HARDWARE_NET/HARDWARE_DEVICE_UPLINK_PORT"):
            slave = station.find(".//HARDWARE_CAN_DEVICE_SLAVE")
            station_record = {
                "port_id": attr(port, "ID"),
                "port_display": attr(port, "DISPLAY"),
                "address": attr(station, "ADDRESS"),
                "name": attr(station, "NAME"),
                "display": attr(station, "DISPLAY"),
                "node_id": "" if slave is None else attr(slave, "NODE_ID"),
                "device_name": "" if slave is None else attr(slave, "DEVICE_NAME"),
                "properties": {attr(prop, "ID"): attr(prop, "VALUE") for prop in station.findall("./HARDWARE_PROPERTY")},
            }
            stations.append(station_record)
        for obj in port.findall("./HARDWARE_CAN_SLAVER_OBJECT"):
            object_record = {
                "port_id": attr(port, "ID"),
                "port_display": attr(port, "DISPLAY"),
                "index": attr(obj, "INDEX"),
                "index_hex": int_hex(attr(obj, "INDEX")),
                "desc": attr(obj, "DESC"),
                "datatype": attr(obj, "DATATYPE"),
                "array_size": attr(obj, "ARRAY_SIZE") if attr(obj, "ARRAY_FLAG") == "YES" else "",
                "enable": attr(obj, "ENABLE"),
                "pdo_index": attr(obj, "PDO_INDEX"),
                "pdo_index_hex": int_hex(attr(obj, "PDO_INDEX")),
                "pdo_desc": attr(obj, "PDO_DESC"),
                "mapping_count": len(obj.findall("./HARDWARE_MODBUS_TAG_MAPPING")),
            }
            slave_objects.append(object_record)
            for mapping in obj.findall("./HARDWARE_MODBUS_TAG_MAPPING"):
                slave_mappings.append(
                    {
                        "port_id": attr(port, "ID"),
                        "index": attr(obj, "INDEX"),
                        "index_hex": int_hex(attr(obj, "INDEX")),
                        "offset": attr(mapping, "OFFSET"),
                        "sub": str(int(attr(mapping, "OFFSET")) + 1) if attr(mapping, "OFFSET").isdigit() else "",
                        "tag_name": attr(mapping, "TAG_NAME"),
                        "datatype": attr(obj, "DATATYPE"),
                        "pdo_index": attr(obj, "PDO_INDEX"),
                        "pdo_desc": attr(obj, "PDO_DESC"),
                    }
                )

    for tag in root.iter("HARDWARE_CHANNEL_TAG"):
        cmd = parent.get(tag)
        group = parent.get(cmd) if cmd is not None else None
        slave = parent.get(group) if group is not None else None
        station = nearest_ancestor(parent, tag, "HARDWARE_DEVICE_UPLINK_PORT")
        port = nearest_ancestor(parent, tag, "HARDWARE_DEVICE_DOWNLINK_PORT")
        index = "" if group is None else attr(group, "INDEX_ID")
        sub = "" if group is None else attr(group, "SUB_INDEX_ID")
        hardware_tags.append(
            {
                "name": attr(tag, "NAME"),
                "datatype": attr(tag, "DATATYPE"),
                "desc": attr(tag, "DESC"),
                "enable": attr(tag, "ENABLE"),
                "init_value": attr(tag, "INIT_VALUE"),
                "readonly": attr(tag, "READONLY"),
                "visible": attr(tag, "VISIBLE"),
                "access": "" if group is None else attr(group, "CMD_ACCESS_TYPE"),
                "index": index,
                "index_hex": int_hex(index),
                "sub": sub,
                "length": "" if group is None else attr(group, "OUTPUT_LENGTH"),
                "cycle": "" if group is None else attr(group, "CYCLE_TIME"),
                "group_enable": "" if group is None else attr(group, "HARDWARE_GROUP_ENABLE"),
                "cmd_id": "" if cmd is None else attr(cmd, "ID"),
                "device": "" if slave is None else attr(slave, "DEVICE_NAME"),
                "node": "" if slave is None else attr(slave, "NODE_ID"),
                "station": "" if station is None else attr(station, "ADDRESS"),
                "port_id": "" if port is None else attr(port, "ID"),
                "port_display": "" if port is None else attr(port, "DISPLAY"),
                "members": [variable_member_tree(member) for member in tag.findall("./VARIABLE_MEMBER")],
            }
        )

    return {
        "downlink_ports": downlinks,
        "stations": stations,
        "slave_objects": slave_objects,
        "slave_mappings": slave_mappings,
        "hardware_tags": hardware_tags,
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_export_ai(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    st_dir = output_dir / "st" if args.st_mode == "files" else None

    control = collect_control_scheme(root, text, args.st_mode, st_dir, output_dir)
    function_blocks = collect_function_like_pous(root, text, "function-block", "FUNCTION_BLOCK", args.st_mode, st_dir, output_dir)
    functions = collect_function_like_pous(root, text, "function", "FUNCTION", args.st_mode, st_dir, output_dir)
    variables = collect_variables(root)
    user_structs = collect_user_structs(root)
    graphics = collect_graphic_pous(root)
    hardware = collect_hardware_package(root)

    index = {
        "format": "kecon-xcskr-ai-pack/v2",
        "project": {
            "path": str(args.project),
            "name": attr(root, "NAME"),
            "other_name": attr(root, "OTHER_NAME"),
            "version": attr(root, "VERSION"),
            "last_save_version": attr(root, "LAST_SAVE_VERISON") or attr(root, "LAST_SAVE_VERSION"),
            "encoding": args.encoding,
            "raw_bytes": args.project.stat().st_size,
        },
        "files": {
            "hardware": "hardware.json",
            "programs": "programs.json",
            "function_blocks": "function-blocks.json",
            "functions": "functions.json",
            "variables": "variables.json",
            "user_data_types": "user-data-types.json",
            "graphics": "graphics.json",
        },
        "counts": {
            "tasks": len(control["tasks"]),
            "programs": len(control["programs"]),
            "function_blocks": len(function_blocks),
            "functions": len(functions),
            "variables": len(variables),
            "user_structs": len(user_structs),
            "graphic_pous": len(graphics["pous"]),
            "downlink_ports": len(hardware["downlink_ports"]),
            "stations": len(hardware["stations"]),
            "hardware_tags": len(hardware["hardware_tags"]),
            "slave_objects": len(hardware["slave_objects"]),
            "slave_mappings": len(hardware["slave_mappings"]),
        },
        "control_scheme": {"tasks": control["tasks"]},
        "graphic_pous": [
            {
                "name": pou["name"],
                "pou_type": pou["pou_type"],
                "language": pou["language"],
                "section": pou["section"],
                "task_kind": pou["task_kind"],
                "block_count": pou["block_count"],
                "line_count": pou["line_count"],
                "comment_count": pou["comment_count"],
                "input_pin_count": pou["input_pin_count"],
                "output_pin_count": pou["output_pin_count"],
                "connected_input_count": pou["connected_input_count"],
                "connected_output_count": pou["connected_output_count"],
            }
            for pou in graphics["pous"]
        ],
    }

    write_json(output_dir / "index.json", index)
    write_json(output_dir / "programs.json", {"programs": control["programs"]})
    write_json(output_dir / "function-blocks.json", {"function_blocks": function_blocks})
    write_json(output_dir / "functions.json", {"functions": functions})
    write_json(output_dir / "variables.json", {"variables": variables})
    write_json(output_dir / "user-data-types.json", {"user_structs": user_structs})
    write_json(output_dir / "graphics.json", graphics)
    write_json(output_dir / "hardware.json", hardware)
    print("AI_EXPORT=OK")
    print(f"OutputDir={output_dir}")
    print(f"Index={output_dir / 'index.json'}")
    return 0


START_TAG_RE_TEMPLATE = r"<{tag}\b[^>]*>"
ATTR_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_:\.-]*)="([^"]*)"')


def parse_start_tag_attrs(start_tag: str) -> dict[str, str]:
    return {match.group(1): html.unescape(match.group(2)) for match in ATTR_RE.finditer(start_tag)}


def find_start_tag_span(text: str, tag: str, predicate, offset: int = 0) -> tuple[int, int, dict[str, str]]:
    pattern = re.compile(START_TAG_RE_TEMPLATE.format(tag=re.escape(tag)), flags=re.DOTALL)
    for match in pattern.finditer(text):
        attrs_map = parse_start_tag_attrs(match.group(0))
        if predicate(attrs_map):
            return offset + match.start(), offset + match.end(), attrs_map
    raise ValueError(f"{tag} matching selector not found")


def find_element_span(text: str, tag: str, predicate, offset: int = 0) -> tuple[int, int, str, dict[str, str]]:
    pattern = re.compile(START_TAG_RE_TEMPLATE.format(tag=re.escape(tag)), flags=re.DOTALL)
    close = f"</{tag}>"
    for match in pattern.finditer(text):
        start_tag = match.group(0)
        attrs_map = parse_start_tag_attrs(start_tag)
        if not predicate(attrs_map):
            continue
        if start_tag.rstrip().endswith("/>"):
            return offset + match.start(), offset + match.end(), text[match.start():match.end()], attrs_map
        close_pos = text.find(close, match.end())
        if close_pos < 0:
            raise ValueError(f"{tag} matching close tag not found")
        end = close_pos + len(close)
        return offset + match.start(), offset + end, text[match.start():end], attrs_map
    raise ValueError(f"{tag} matching selector not found")


def patch_start_tag_attrs(start_tag: str, updates: dict[str, str]) -> str:
    patched = start_tag
    for key, value in updates.items():
        encoded = xml_attr_encode(value)
        pattern = re.compile(rf'(\b{re.escape(key)}=")([^"]*)(")')
        if pattern.search(patched):
            patched = pattern.sub(rf"\g<1>{encoded}\3", patched, count=1)
            continue
        insert_at = patched.rfind("/>") if patched.rstrip().endswith("/>") else patched.rfind(">")
        if insert_at < 0:
            raise ValueError("invalid start tag")
        patched = patched[:insert_at].rstrip() + f' {key}="{encoded}"' + patched[insert_at:]
    return patched


def parse_attr_updates(pairs: list[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--attr must use KEY=VALUE form: {pair!r}")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--attr key is empty: {pair!r}")
        updates[key] = value
    return updates


def patch_selected_attrs(text: str, args: argparse.Namespace, updates: dict[str, str]) -> tuple[str, str]:
    if args.kind == "variable":
        start, end, _ = find_start_tag_span(text, "VARIABLE", lambda attrs_map: attrs_map.get("NAME") == args.name)
        target = f"variable:{args.name}"
    elif args.kind == "hardware-tag":
        start, end, _ = find_start_tag_span(text, "HARDWARE_CHANNEL_TAG", lambda attrs_map: attrs_map.get("NAME") == args.name)
        target = f"hardware-tag:{args.name}"
    elif args.kind == "user-struct":
        start, end, _ = find_start_tag_span(text, "USER_STRUCT", lambda attrs_map: attrs_map.get("NAME") == args.struct)
        target = f"user-struct:{args.struct}"
    elif args.kind == "user-struct-member":
        struct_start, _, struct_raw, _ = find_element_span(text, "USER_STRUCT", lambda attrs_map: attrs_map.get("NAME") == args.struct)
        local_start, local_end, _ = find_start_tag_span(struct_raw, "USER_STRUCT_MEMBER", lambda attrs_map: attrs_map.get("NAME") == args.member, offset=struct_start)
        start, end = local_start, local_end
        target = f"user-struct-member:{args.struct}.{args.member}"
    elif args.kind == "pou":
        tag = pou_tag(args.pou_type)
        span = find_named_span(text, tag, args.name)
        local_start, local_end, _ = find_start_tag_span(span.raw, tag, lambda attrs_map: attrs_map.get("NAME") == args.name, offset=span.start)
        start, end = local_start, local_end
        target = f"pou:{args.pou_type}:{args.name}"
    elif args.kind == "pou-var":
        tag = pou_tag(args.pou_type)
        section_tags = {
            "input": "SECTION_VAR_INPUT",
            "output": "SECTION_VAR_OUTPUT",
            "internal": "SECTION_VAR_INTERNAL",
        }
        section_tag = section_tags[args.var_section]
        span = find_named_span(text, tag, args.name)
        local_start, local_end, _ = find_start_tag_span(span.raw, section_tag, lambda attrs_map: attrs_map.get("NAME") == args.var, offset=span.start)
        start, end = local_start, local_end
        target = f"pou-var:{args.pou_type}:{args.name}:{args.var_section}:{args.var}"
    elif args.kind == "downlink-port":
        if not args.port_id:
            raise ValueError("--port-id is required for downlink-port")
        start, end, _ = find_start_tag_span(text, "HARDWARE_DEVICE_DOWNLINK_PORT", lambda attrs_map: attrs_map.get("ID") == args.port_id)
        target = f"downlink-port:{args.port_id}"
    elif args.kind == "station":
        if not args.port_id:
            raise ValueError("--port-id is required for station")
        if not args.address and not args.name:
            raise ValueError("--address or --name is required for station")
        port_start, _, port_raw, _ = find_element_span(text, "HARDWARE_DEVICE_DOWNLINK_PORT", lambda attrs_map: attrs_map.get("ID") == args.port_id)
        local_start, local_end, _ = find_start_tag_span(
            port_raw,
            "HARDWARE_DEVICE_UPLINK_PORT",
            lambda attrs_map: (args.address and attrs_map.get("ADDRESS") == args.address) or (args.name and attrs_map.get("NAME") == args.name),
            offset=port_start,
        )
        start, end = local_start, local_end
        target = f"station:{args.port_id}:{args.address or args.name}"
    elif args.kind == "slave-object":
        if not args.port_id or not args.index:
            raise ValueError("--port-id and --index are required for slave-object")
        port_start, _, port_raw, _ = find_element_span(text, "HARDWARE_DEVICE_DOWNLINK_PORT", lambda attrs_map: attrs_map.get("ID") == args.port_id)
        local_start, _, object_raw, _ = find_element_span(
            port_raw,
            "HARDWARE_CAN_SLAVER_OBJECT",
            lambda attrs_map: attrs_map.get("INDEX") == args.index,
            offset=port_start,
        )
        object_tag_start, object_tag_end, _ = find_start_tag_span(
            object_raw,
            "HARDWARE_CAN_SLAVER_OBJECT",
            lambda attrs_map: attrs_map.get("INDEX") == args.index,
            offset=local_start,
        )
        start, end = object_tag_start, object_tag_end
        target = f"slave-object:{args.port_id}:{args.index}"
    elif args.kind == "slave-mapping":
        if not args.port_id or not args.index or args.offset is None:
            raise ValueError("--port-id, --index, and --offset are required for slave-mapping")
        port_start, _, port_raw, _ = find_element_span(text, "HARDWARE_DEVICE_DOWNLINK_PORT", lambda attrs_map: attrs_map.get("ID") == args.port_id)
        object_start, _, object_raw, _ = find_element_span(
            port_raw,
            "HARDWARE_CAN_SLAVER_OBJECT",
            lambda attrs_map: attrs_map.get("INDEX") == args.index,
            offset=port_start,
        )
        local_start, local_end, _ = find_start_tag_span(
            object_raw,
            "HARDWARE_MODBUS_TAG_MAPPING",
            lambda attrs_map: attrs_map.get("OFFSET") == args.offset,
            offset=object_start,
        )
        start, end = local_start, local_end
        target = f"slave-mapping:{args.port_id}:{args.index}:{args.offset}"
    elif args.kind == "task":
        if not args.task_id and not args.task_kind:
            raise ValueError("--task-id or --task-kind is required for kind=task")
        task_start, _, task_raw, task_tag = find_task_span(text, args.task_id, args.task_kind)
        local_start, local_end, attrs_map = find_start_tag_span(
            task_raw, task_tag, lambda _: True, offset=task_start
        )
        start, end = local_start, local_end
        target = f"task:{task_tag}:{attrs_map.get('ID', '')}"
    elif args.kind == "trig-condition":
        if not args.task_id and not args.task_kind:
            raise ValueError("--task-id or --task-kind is required for kind=trig-condition")
        task_start, task_end, _, _ = find_task_span(text, args.task_id, args.task_kind)
        local_start, local_end, _ = find_start_tag_span(
            text[task_start:task_end], "TRIG_CONDITION", lambda _: True, offset=task_start
        )
        start, end = local_start, local_end
        target = f"trig-condition:{args.task_id or args.task_kind}"
    elif args.kind == "block":
        if not args.name or not args.block:
            raise ValueError("--name (POU name) and --block are required for kind=block")
        tag = pou_tag(args.pou_type or "program")
        span = find_named_span(text, tag, args.name)
        local_start, local_end, _ = find_start_tag_span(
            span.raw, "CONTROL_LOGIC_BLOCK", lambda attrs_map: attrs_map.get("NAME") == args.block, offset=span.start
        )
        start, end = local_start, local_end
        target = f"block:{args.name}:{args.block}"
    else:
        raise ValueError(f"unsupported kind: {args.kind}")

    patched_tag = patch_start_tag_attrs(text[start:end], updates)
    return text[:start] + patched_tag + text[end:], target


def cmd_set_attrs(args: argparse.Namespace) -> int:
    updates = parse_attr_updates(args.attr)
    text = read_text(args.project, args.encoding)
    new_text, target = patch_selected_attrs(text, args, updates)
    parse_xml(new_text)
    if args.dry_run:
        print("DRY_RUN=OK")
        print(f"Target={target}")
        print(f"Attrs={','.join(updates)}")
        return 0
    backup = None if args.no_backup else make_backup(args.project)
    write_text(args.project, new_text, args.encoding)
    print(f"Backup={backup}" if backup else "Backup=SKIPPED")
    print(f"SetAttrs={target}")
    return 0


def indent_step(text: str) -> str:
    """Infer one indentation level from the document itself.

    Project files written by xRobotDesigner use four spaces, but the step is
    read from the first indented line so generated XML always matches whatever
    the target file already uses.
    """
    match = re.search(r">\r?\n([ \t]+)<", text)
    return match.group(1) if match else "    "


def xml_start_tag(tag: str, attrs: dict[str, str], self_close: bool = True) -> str:
    """Render one start tag with alphabetically ordered attributes.

    xRobotDesigner writes attributes in alphabetical order and uses no space
    before the self-closing slash; reproducing that keeps diffs against
    GUI-saved files readable.
    """
    parts = "".join(
        ' {0}="{1}"'.format(key, xml_attr_encode(str(value)))
        for key, value in sorted(attrs.items())
    )
    return "<" + tag + parts + ("/>" if self_close else ">")


def parse_datatype(datatype: str) -> tuple[str, int | None, int]:
    """Split a DATATYPE string into (base type, element count, first index).

    Accepts a scalar type, T[N] (indices 0..N-1) and T[lo..hi].
    """
    raw = (datatype or "").strip()
    match = ARRAY_DATATYPE_RE.match(raw)
    if not match:
        return raw, None, 0
    base = match.group(1)
    first = int(match.group(2))
    if match.group(3) is None:
        count, low = first, 0
    else:
        low, count = first, int(match.group(3)) - first + 1
    if count < 1 or count > 4096:
        raise ValueError(f"unsupported array length in DATATYPE {datatype!r}")
    return base, count, low


def collect_struct_defs(root: ET.Element) -> dict[str, list[dict[str, str]]]:
    structs: dict[str, list[dict[str, str]]] = {}
    for struct in root.findall(".//USER_DATA_TYPE/USER_STRUCT"):
        structs[attr(struct, "NAME")] = [
            {
                "name": attr(member, "NAME"),
                "datatype": attr(member, "DATATYPE"),
                "desc": attr(member, "DESC"),
                "init_value": attr(member, "INIT_VALUE"),
                "visible": attr(member, "VISIBLE") or "YES",
            }
            for member in struct.findall("./USER_STRUCT_MEMBER")
        ]
    return structs


def detect_member_readonly(root: ET.Element) -> str | None:
    """Mirror whatever READONLY convention the project already uses on members.

    Returns the value to write on array element members, or None when the
    project omits the attribute (which is what the official samples do).
    """
    for container in root.findall(".//TAGCONFIG"):
        for member in container.iter("VARIABLE_MEMBER"):
            name = attr(member, "NAME")
            if name.split(".")[-1].endswith("]"):
                return member.attrib.get("READONLY")
    return None


def resolve_member_readonly(root: ET.Element, choice: str) -> str | None:
    if choice == "yes":
        return "NO"
    if choice == "no":
        return None
    return detect_member_readonly(root)


def resolve_element_init(value: str | None) -> str:
    if value is None:
        return ""
    return AUTO_INIT if value == "auto" else value


def existing_names(root: ET.Element) -> dict[str, set[str]]:
    return {
        "variable": {attr(elem, "NAME") for elem in root.iter("VARIABLE")},
        "hardware_tag": {attr(elem, "NAME") for elem in root.iter("HARDWARE_CHANNEL_TAG")},
        "user_struct": {attr(elem, "NAME") for elem in root.iter("USER_STRUCT")},
    }


def check_identifier(name: str, what: str) -> None:
    if not IDENTIFIER_RE.match(name or ""):
        raise ValueError(f"{what} name {name!r} must match [A-Za-z_][A-Za-z0-9_]*")


def check_identifier_loose(name: str, what: str) -> None:
    """POU display names may contain Chinese and punctuation; only reject XML-hostile ones."""
    if not name or name.strip() != name:
        raise ValueError(f"{what} name {name!r} must not be empty or padded with spaces")
    for bad in ('"', "<", ">", "&"):
        if bad in name:
            raise ValueError(f"{what} name {name!r} must not contain {bad!r}")


def check_datatype(datatype: str, structs: dict[str, list[dict[str, str]]], allow_unknown: bool) -> str:
    base, _, _ = parse_datatype(datatype)
    if base in BASE_DATATYPES or base in structs:
        return ""
    message = f"unknown DATATYPE base {base!r}; not an IEC elementary type and not a USER_STRUCT in this project"
    if allow_unknown:
        return message
    raise ValueError(message + " (use --allow-unknown-datatype to force)")


def render_variable_member(
    name: str,
    datatype: str,
    structs: dict[str, list[dict[str, str]]],
    indent: str,
    *,
    is_array_element: bool,
    desc: str = "",
    init_value: str = "",
    visible: str = "YES",
    cold_retain: str = "NO",
    readonly: str | None = None,
    depth: int = 0,
    counter: list[int] | None = None,
    step: str = "    ",
) -> str:
    """Render one VARIABLE_MEMBER subtree.

    The official Kecon sample projects never write READONLY on VARIABLE_MEMBER,
    while some projects created by xRobotDesigner V5.1 write it on array element
    members only.  The caller decides via readonly: None omits the attribute,
    a string writes it on array elements.  Struct field members never carry it.
    """
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_GENERATED_MEMBERS:
        raise ValueError(f"member expansion exceeds {MAX_GENERATED_MEMBERS} nodes; refusing to generate")
    if depth > 8:
        raise ValueError(f"user data type nesting deeper than 8 levels at {name!r}")

    base, count, low = parse_datatype(datatype)
    attrs = {
        "COLD_RETAIN": cold_retain,
        "DATATYPE": datatype,
        "DESC": desc,
        "INIT_VALUE": init_value,
        "NAME": name,
        "VISIBLE": visible,
    }
    if init_value == AUTO_INIT:
        init_value = "" if (count is not None or base in structs) else TYPE_DEFAULT_INIT.get(base, "")
        attrs["INIT_VALUE"] = init_value
    if is_array_element and readonly is not None:
        attrs["READONLY"] = readonly

    children: list[str] = []
    if count is not None:
        for index in range(low, low + count):
            children.append(
                render_variable_member(
                    f"{name}[{index}]",
                    base,
                    structs,
                    indent + step,
                    is_array_element=True,
                    init_value=init_value,
                    visible=visible,
                    cold_retain=cold_retain,
                    readonly=readonly,
                    depth=depth + 1,
                    counter=counter,
                    step=step,
                )
            )
    elif base in structs:
        for field in structs[base]:
            children.append(
                render_variable_member(
                    f"{name}.{field['name']}",
                    field["datatype"],
                    structs,
                    indent + step,
                    is_array_element=False,
                    desc=field["desc"],
                    init_value=field["init_value"],
                    visible=field["visible"],
                    cold_retain=cold_retain,
                    readonly=readonly,
                    depth=depth + 1,
                    counter=counter,
                    step=step,
                )
            )

    if not children:
        return indent + xml_start_tag("VARIABLE_MEMBER", attrs, True)
    body = "\n".join(children)
    return (
        indent
        + xml_start_tag("VARIABLE_MEMBER", attrs, False)
        + "\n"
        + body
        + "\n"
        + indent
        + "</VARIABLE_MEMBER>"
    )


def render_variable_children(
    name: str,
    datatype: str,
    structs: dict[str, list[dict[str, str]]],
    indent: str,
    *,
    element_init: str = "",
    visible: str = "YES",
    cold_retain: str = "NO",
    readonly: str | None = None,
    step: str = "    ",
) -> tuple[str, int]:
    counter = [0]
    base, count, low = parse_datatype(datatype)
    children: list[str] = []
    if count is not None:
        for index in range(low, low + count):
            children.append(
                render_variable_member(
                    f"{name}[{index}]",
                    base,
                    structs,
                    indent,
                    is_array_element=True,
                    init_value=element_init,
                    visible=visible,
                    cold_retain=cold_retain,
                    readonly=readonly,
                    counter=counter,
                    step=step,
                )
            )
    elif base in structs:
        for field in structs[base]:
            children.append(
                render_variable_member(
                    f"{name}.{field['name']}",
                    field["datatype"],
                    structs,
                    indent,
                    is_array_element=False,
                    desc=field["desc"],
                    init_value=field["init_value"],
                    visible=field["visible"],
                    cold_retain=cold_retain,
                    readonly=readonly,
                    counter=counter,
                    step=step,
                )
            )
    return "\n".join(children), counter[0]


def render_variable(
    name: str,
    datatype: str,
    structs: dict[str, list[dict[str, str]]],
    indent: str,
    attrs: dict[str, str],
    *,
    element_init: str = "",
    member_readonly: str | None = None,
    step: str = "    ",
) -> tuple[str, int]:
    body, generated = render_variable_children(
        name,
        datatype,
        structs,
        indent + step,
        element_init=element_init,
        visible=attrs.get("VISIBLE", "YES"),
        cold_retain=attrs.get("COLD_RETAIN", "NO"),
        readonly=member_readonly,
        step=step,
    )
    if not body:
        return indent + xml_start_tag("VARIABLE", attrs, True), 0
    xml = (
        indent
        + xml_start_tag("VARIABLE", attrs, False)
        + "\n"
        + body
        + "\n"
        + indent
        + "</VARIABLE>"
    )
    return xml, generated


def render_user_struct(name: str, attrs: dict[str, str], members: list[dict[str, str]], indent: str, step: str = "    ") -> str:
    if not members:
        return indent + xml_start_tag("USER_STRUCT", attrs, True)
    lines = [indent + xml_start_tag("USER_STRUCT", attrs, False)]
    for member in members:
        lines.append(indent + step + xml_start_tag("USER_STRUCT_MEMBER", member, True))
    lines.append(indent + "</USER_STRUCT>")
    return "\n".join(lines)


def expand_self_closing(text: str, tag: str, predicate=None) -> tuple[str, bool]:
    """Turn a self-closing container into an open/close pair so children fit."""
    predicate = predicate or (lambda attrs_map: True)
    start, end, raw, _ = find_element_span(text, tag, predicate)
    if not raw.rstrip().endswith("/>"):
        return text, False
    line_start = text.rfind("\n", 0, start) + 1
    indent = text[line_start:start]
    if indent.strip():
        indent = ""
    open_tag = raw.rstrip()[:-2].rstrip() + ">"
    replacement = open_tag + "\n" + indent + "</" + tag + ">"
    return text[:start] + replacement + text[end:], True


def insert_container_child(text: str, tag: str, build_child, predicate=None) -> str:
    """Insert one rendered child as the last child of the named container."""
    predicate = predicate or (lambda attrs_map: True)
    text, _ = expand_self_closing(text, tag, predicate)
    start, end, _, _ = find_element_span(text, tag, predicate)
    close = "</" + tag + ">"
    close_index = text.rfind(close, start, end)
    if close_index < 0:
        raise ValueError(f"{tag} close tag not found")
    line_start = text.rfind("\n", start, close_index) + 1
    close_indent = text[line_start:close_index]
    if close_indent.strip():
        close_indent = ""
    child_indent = close_indent + indent_step(text)
    first_child = re.search(r"\n([ \t]*)<", text[start:line_start])
    if first_child:
        child_indent = first_child.group(1)
    child = to_document_eol(build_child(child_indent), text)
    eol = document_eol(text)
    return text[:line_start] + child + eol + text[line_start:]


def remove_element(text: str, tag: str, predicate) -> str:
    start, end, _, _ = find_element_span(text, tag, predicate)
    line_start = text.rfind("\n", 0, start) + 1
    if not text[line_start:start].strip():
        start = line_start
    if text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:]


def finish_write(args: argparse.Namespace, new_text: str, message: str) -> int:
    parse_xml(new_text)
    if args.dry_run:
        print("DRY_RUN=OK")
        print(message)
        return 0
    backup = None if args.no_backup else make_backup(args.project)
    write_text(args.project, new_text, args.encoding)
    print(f"Backup={backup}" if backup else "Backup=SKIPPED")
    print(message)
    return 0


def parse_member_specs(specs: list[str] | None, members_json: Path | None, encoding: str) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    for spec in specs or []:
        parts = spec.split(":", 2)
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f"--member must use NAME:DATATYPE[:DESC] form: {spec!r}")
        members.append(
            {
                "NAME": parts[0].strip(),
                "DATATYPE": parts[1].strip(),
                "DESC": parts[2] if len(parts) > 2 else "",
                "INIT_VALUE": "",
                "VISIBLE": "YES",
            }
        )
    if members_json:
        payload = json.loads(members_json.read_text(encoding=encoding))
        rows = payload["members"] if isinstance(payload, dict) else payload
        for row in rows:
            members.append(
                {
                    "NAME": str(row["name"]),
                    "DATATYPE": str(row["datatype"]),
                    "DESC": str(row.get("desc", "")),
                    "INIT_VALUE": str(row.get("init_value", "")),
                    "VISIBLE": str(row.get("visible", "YES")),
                }
            )
    return members


def expected_member_tree(
    name: str,
    datatype: str,
    structs: dict[str, list[dict[str, str]]],
    depth: int = 0,
) -> list[tuple[str, str]]:
    """Flatten the VARIABLE_MEMBER tree a variable of this datatype should own."""
    if depth > 8:
        raise ValueError(f"user data type nesting deeper than 8 levels at {name!r}")
    out: list[tuple[str, str]] = []
    base, count, low = parse_datatype(datatype)
    if count is not None:
        for index in range(low, low + count):
            child = f"{name}[{index}]"
            out.append((child, base))
            out.extend(expected_member_tree(child, base, structs, depth + 1))
    elif base in structs:
        for field in structs[base]:
            child = f"{name}.{field['name']}"
            out.append((child, field["datatype"]))
            out.extend(expected_member_tree(child, field["datatype"], structs, depth + 1))
    return out


def actual_member_tree(elem: ET.Element) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for member in elem.findall("./VARIABLE_MEMBER"):
        out.append((attr(member, "NAME"), attr(member, "DATATYPE")))
        out.extend(actual_member_tree(member))
    return out


def variables_using_struct(root: ET.Element, struct_name: str) -> list[str]:
    users: list[str] = []
    for var in root.iter("VARIABLE"):
        base, _, _ = parse_datatype(attr(var, "DATATYPE"))
        if base == struct_name:
            users.append(attr(var, "NAME"))
    return users


def cmd_add_user_struct(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    structs = collect_struct_defs(root)
    names = existing_names(root)
    check_identifier(args.name, "user struct")
    if args.name in names["user_struct"]:
        if not args.replace:
            raise ValueError(f"USER_STRUCT {args.name!r} already exists; pass --replace to overwrite")
        text = remove_element(text, "USER_STRUCT", lambda attrs_map: attrs_map.get("NAME") == args.name)

    members = parse_member_specs(args.member, args.members_json, args.input_encoding)
    if not members:
        raise ValueError("at least one --member or --members-json entry is required")
    warnings: list[str] = []
    seen: set[str] = set()
    for member in members:
        check_identifier(member["NAME"], "struct member")
        if member["NAME"] in seen:
            raise ValueError(f"duplicate struct member {member['NAME']!r}")
        seen.add(member["NAME"])
        note = check_datatype(member["DATATYPE"], structs, args.allow_unknown_datatype)
        if note:
            warnings.append(f"{member['NAME']}: {note}")

    struct_attrs = dict(USER_STRUCT_DEFAULT_ATTRS)
    struct_attrs["NAME"] = args.name
    if args.desc is not None:
        struct_attrs["DESC"] = args.desc
    struct_attrs.update(parse_attr_updates(args.attr or []))

    new_text = insert_container_child(
        text,
        "USER_DATA_TYPE",
        lambda indent: render_user_struct(args.name, struct_attrs, members, indent, indent_step(text)),
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    return finish_write(args, new_text, f"AddedUserStruct={args.name} members={len(members)}")


def cmd_add_user_struct_member(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    structs = collect_struct_defs(root)
    if args.struct not in structs:
        raise ValueError(f"USER_STRUCT {args.struct!r} not found")
    members = parse_member_specs(args.member, args.members_json, args.input_encoding)
    if not members:
        raise ValueError("at least one --member or --members-json entry is required")
    existing = {member["name"] for member in structs[args.struct]}
    for member in members:
        check_identifier(member["NAME"], "struct member")
        if member["NAME"] in existing:
            raise ValueError(f"struct member {member['NAME']!r} already exists in {args.struct!r}")
        note = check_datatype(member["DATATYPE"], structs, args.allow_unknown_datatype)
        if note:
            print(f"WARNING: {member['NAME']}: {note}")

    new_text = text
    for member in members:
        new_text = insert_container_child(
            new_text,
            "USER_STRUCT",
            lambda indent, member=member: indent + xml_start_tag("USER_STRUCT_MEMBER", member, True),
            predicate=lambda attrs_map: attrs_map.get("NAME") == args.struct,
        )

    users = variables_using_struct(root, args.struct)
    if users:
        print(f"WARNING: variables using {args.struct} still hold the old member tree: {', '.join(users)}")
        print("WARNING: run rebuild-variable-members for each of them before compiling")
    return finish_write(args, new_text, f"AddedStructMembers={args.struct} count={len(members)}")


def cmd_add_variable(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    structs = collect_struct_defs(root)
    names = existing_names(root)
    check_identifier(args.name, "variable")
    if args.name in names["hardware_tag"]:
        raise ValueError(f"{args.name!r} already exists as a HARDWARE_CHANNEL_TAG; PLC names must stay unique")
    if args.name in names["variable"]:
        if not args.replace:
            raise ValueError(f"VARIABLE {args.name!r} already exists; pass --replace to overwrite")
        text = remove_element(text, "VARIABLE", lambda attrs_map: attrs_map.get("NAME") == args.name)
    note = check_datatype(args.datatype, structs, args.allow_unknown_datatype)
    if note:
        print(f"WARNING: {note}")

    attrs = dict(VARIABLE_DEFAULT_ATTRS)
    if args.template:
        _, _, template_attrs = find_start_tag_span(
            text, "VARIABLE", lambda attrs_map: attrs_map.get("NAME") == args.template
        )
        attrs = dict(template_attrs)
    attrs["NAME"] = args.name
    attrs["DATATYPE"] = args.datatype
    if args.desc is not None:
        attrs["DESC"] = args.desc
    if args.init_value is not None:
        attrs["INIT_VALUE"] = args.init_value
    if args.readonly is not None:
        attrs["READONLY"] = args.readonly
    if args.visible is not None:
        attrs["VISIBLE"] = args.visible
    if args.cold_retain is not None:
        attrs["COLD_RETAIN"] = args.cold_retain
    attrs.update(parse_attr_updates(args.attr or []))

    container = "GLOBAL_TAG_CONFIG" if args.container == "global" else "TAGCONFIG"
    if not root.findall(f".//{container}"):
        raise ValueError(f"container {container} not found in project")

    generated = [0]

    member_readonly = resolve_member_readonly(root, args.member_readonly)

    def build(indent: str) -> str:
        xml, count = render_variable(
            args.name,
            args.datatype,
            structs,
            indent,
            attrs,
            element_init=resolve_element_init(args.element_init),
            member_readonly=member_readonly,
            step=indent_step(text),
        )
        generated[0] = count
        return xml

    new_text = insert_container_child(text, container, build)
    return finish_write(
        args,
        new_text,
        f"AddedVariable={args.name} datatype={args.datatype} container={container} members={generated[0]}",
    )


def cmd_rebuild_variable_members(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    structs = collect_struct_defs(root)
    start, end, raw, attrs = find_element_span(
        text, "VARIABLE", lambda attrs_map: attrs_map.get("NAME") == args.name
    )
    datatype = attrs.get("DATATYPE", "")
    check_datatype(datatype, structs, args.allow_unknown_datatype)
    line_start = text.rfind("\n", 0, start) + 1
    indent = text[line_start:start]
    if indent.strip():
        indent = ""
    start_tag_match = re.match(START_TAG_RE_TEMPLATE.format(tag="VARIABLE"), raw, flags=re.DOTALL)
    if start_tag_match is None:
        raise ValueError("VARIABLE start tag not found")
    start_tag = start_tag_match.group(0)
    open_tag = start_tag.rstrip()[:-2].rstrip() + ">" if start_tag.rstrip().endswith("/>") else start_tag

    body, generated = render_variable_children(
        args.name,
        datatype,
        structs,
        indent + "    ",
        element_init=resolve_element_init(args.element_init),
        visible=attrs.get("VISIBLE", "YES"),
        cold_retain=attrs.get("COLD_RETAIN", "NO"),
        readonly=resolve_member_readonly(root, args.member_readonly),
        step=indent_step(text),
    )
    if body:
        replacement = open_tag + "\n" + body + "\n" + indent + "</VARIABLE>"
    else:
        replacement = start_tag if start_tag.rstrip().endswith("/>") else open_tag[:-1].rstrip() + "/>"
    new_text = text[:start] + replacement + text[end:]
    return finish_write(args, new_text, f"RebuiltVariableMembers={args.name} datatype={datatype} members={generated}")


def cmd_remove_entity(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    if args.kind == "variable":
        tag, key = "VARIABLE", args.name
    else:
        tag, key = "USER_STRUCT", args.name
    if tag == "USER_STRUCT":
        root = parse_xml(text)
        users = variables_using_struct(root, args.name)
        if users and not args.force:
            raise ValueError(
                f"USER_STRUCT {args.name!r} is used by variables {', '.join(users)}; pass --force to remove anyway"
            )
    new_text = remove_element(text, tag, lambda attrs_map: attrs_map.get("NAME") == key)
    return finish_write(args, new_text, f"Removed={args.kind}:{key}")


def cmd_validate_datatypes(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    structs = collect_struct_defs(root)
    rows: list[dict[str, object]] = []
    problems = 0

    for struct_name, members in structs.items():
        for member in members:
            base, _, _ = parse_datatype(member["datatype"])
            known = base in BASE_DATATYPES or base in structs
            if not known:
                problems += 1
            rows.append(
                {
                    "entity": "user-struct-member",
                    "name": f"{struct_name}.{member['name']}",
                    "datatype": member["datatype"],
                    "status": "OK" if known else "UNKNOWN_TYPE",
                    "detail": "" if known else f"base {base} is neither elementary nor a USER_STRUCT",
                }
            )

    for var in root.iter("VARIABLE"):
        name = attr(var, "NAME")
        datatype = attr(var, "DATATYPE")
        try:
            base, count, low = parse_datatype(datatype)
        except ValueError as exc:
            problems += 1
            rows.append({"entity": "variable", "name": name, "datatype": datatype, "status": "BAD_ARRAY", "detail": str(exc)})
            continue
        known = base in BASE_DATATYPES or base in structs
        status = "OK"
        detail = ""
        if not known:
            status, detail = "UNKNOWN_TYPE", f"base {base} is neither elementary nor a USER_STRUCT"
        else:
            expected = expected_member_tree(name, datatype, structs)
            actual = actual_member_tree(var)
            expected_map = dict(expected)
            actual_map = dict(actual)
            missing = [key for key in expected_map if key not in actual_map]
            extra = [key for key in actual_map if key not in expected_map]
            retyped = [
                key
                for key, value in expected_map.items()
                if key in actual_map and actual_map[key] != value
            ]
            if missing or extra or retyped:
                status = "MEMBER_MISMATCH"
                notes = []
                if missing:
                    notes.append(f"missing {len(missing)} (e.g. {missing[0]})")
                if extra:
                    notes.append(f"stale {len(extra)} (e.g. {extra[0]})")
                if retyped:
                    notes.append(f"datatype drift {len(retyped)} (e.g. {retyped[0]})")
                detail = "; ".join(notes) + "; run rebuild-variable-members"
        if status != "OK":
            problems += 1
        rows.append({"entity": "variable", "name": name, "datatype": datatype, "status": status, "detail": detail})

    shown = rows if args.show_all else [row for row in rows if row["status"] != "OK"]
    output_rows(shown,["entity", "name", "datatype", "status", "detail"], args.format, args.output, args.output_encoding)
    print(f"Checked={len(rows)} Problems={problems}")
    return 1 if (problems and args.strict) else 0


def cmd_export_graphic(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    try:
        package = collect_graphic_pous(root, getattr(args, "pou", None) or getattr(args, "program", None), args.pou_type)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        maybe_write_output(json.dumps(package, ensure_ascii=False, indent=2) + "\n", args.output, args.output_encoding)
        return 0
    if args.level == "pin":
        rows = graphic_pin_rows(package)
        columns = ["pou", "block", "dir", "pin", "datatype", "enabled", "negated", "init_value", "connection", "conn_kind", "desc"]
    else:
        rows = graphic_block_rows(package)
        columns = ["pou", "pou_type", "lang", "block", "type", "deactive", "inputs", "outputs", "connected_inputs", "connected_outputs", "rect"]
    output_rows(rows, columns, args.format, args.output, args.output_encoding)
    return 0


def pou_local_var_names(root: ET.Element, pou_tag_name: str, pou_name: str) -> set[str]:
    """Names a graphical pin inside this POU may reference locally.

    FUNCTION_BLOCK and FUNCTION POUs declare their own interface and internal
    variables; LD/FBD pins inside them bind to those names, not to globals.
    """
    names: set[str] = set()
    for pou in root.iter(pou_tag_name):
        if attr(pou, "NAME") != pou_name:
            continue
        for section in ("SECTION_VAR_INPUT", "SECTION_VAR_OUTPUT", "SECTION_VAR_INTERNAL"):
            for var in pou.findall("./" + section):
                names.add(attr(var, "NAME"))
    return names


def find_graphic_section_span(text: str, pou_tag_name: str, pou_name: str) -> tuple[int, int, str, str]:
    """Locate the LD/FBD section element of one POU: (start, end, raw, section tag)."""
    span = find_named_span(text, pou_tag_name, pou_name)
    for section_tag in GRAPHIC_SECTION_TAGS:
        if ("<" + section_tag) not in span.raw:
            continue
        start, end, raw, _ = find_element_span(
            span.raw, section_tag, lambda attrs_map: True, offset=span.start
        )
        return start, end, raw, section_tag
    raise ValueError(f"{pou_tag_name} {pou_name!r} has no SECTION_LOGIC_LD / SECTION_LOGIC_FBD")


def find_graphic_pin_element(
    text: str,
    pou_tag_name: str,
    pou_name: str,
    block_name: str,
    pin_name: str,
    pin_dir: str,
) -> tuple[int, int, str, str]:
    """Locate one BLOCK_PIN_INPUT / BLOCK_PIN_OUTPUT element: (start, end, raw, tag)."""
    section_start, _, section_raw, _ = find_graphic_section_span(text, pou_tag_name, pou_name)
    block_start, _, block_raw, _ = find_element_span(
        section_raw,
        "CONTROL_LOGIC_BLOCK",
        lambda attrs_map: attrs_map.get("NAME") == block_name,
        offset=section_start,
    )
    directions = ["BLOCK_PIN_INPUT", "BLOCK_PIN_OUTPUT"]
    if pin_dir == "input":
        directions = ["BLOCK_PIN_INPUT"]
    elif pin_dir == "output":
        directions = ["BLOCK_PIN_OUTPUT"]
    for tag in directions:
        try:
            start, end, raw, _ = find_element_span(
                block_raw, tag, lambda attrs_map: attrs_map.get("NAME") == pin_name, offset=block_start
            )
        except ValueError:
            continue
        return start, end, raw, tag
    raise ValueError(f"pin {pin_name!r} not found on block {block_name!r} of {pou_name!r}")


def line_indent_at(text: str, index: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    indent = text[line_start:index]
    return indent if not indent.strip() else ""


KEEP_CONNECTION = object()


def rebuild_pin(pin_raw: str, indent: str, updates: dict[str, str], connection: object, step: str = "    ") -> str:
    """Re-render one pin element with patched attributes and connection child.

    connection is KEEP_CONNECTION to leave the existing child alone, None to drop
    it, or a (CONNECTION_TYPE, CONNECTION_VALUE) tuple to write one.
    """
    start_tag_match = re.match(START_TAG_RE_TEMPLATE.format(tag=r"BLOCK_PIN_(?:INPUT|OUTPUT)"), pin_raw, flags=re.DOTALL)
    if start_tag_match is None:
        raise ValueError("pin start tag not found")
    start_tag = start_tag_match.group(0)
    tag = re.match(r"<([A-Z_]+)", start_tag).group(1)
    if updates:
        start_tag = patch_start_tag_attrs(start_tag, updates)

    if connection is KEEP_CONNECTION:
        existing = re.search(r"<CONTROL_BLOCK_CONNECTION\b[^>]*>", pin_raw)
        child = existing.group(0) if existing else ""
    elif connection is None:
        child = ""
    else:
        conn_type, conn_value = connection  # type: ignore[misc]
        child = xml_start_tag(
            "CONTROL_BLOCK_CONNECTION",
            {"CONNECTION_TYPE": conn_type, "CONNECTION_VALUE": conn_value},
            True,
        )

    if not child:
        open_tag = start_tag.rstrip()
        if open_tag.endswith("/>"):
            return open_tag
        return open_tag[:-1].rstrip() + "/>"
    open_tag = start_tag.rstrip()
    if open_tag.endswith("/>"):
        open_tag = open_tag[:-2].rstrip() + ">"
    return open_tag + "\n" + indent + step + child + "\n" + indent + "</" + tag + ">"


def section_line_names(section_raw: str) -> list[str]:
    return re.findall(r"<CONTROL_LOGIC_LINE\b[^>]*\bNAME=\"([^\"]*)\"", section_raw)


def next_free_name(existing: list[str], prefix: str) -> str:
    used = set(existing)
    index = 0
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def insert_into_section(text: str, section_start: int, section_end: int, section_tag: str, xml: str, before_lines: bool) -> str:
    """Insert one rendered child into a graphical section.

    Blocks come before lines in GUI-written files, so a new block is inserted in
    front of the first CONTROL_LOGIC_LINE and a new line is appended at the end.
    """
    section_raw = text[section_start:section_end]
    close = "</" + section_tag + ">"
    anchor_rel = -1
    if before_lines:
        first_line = re.search(r"<CONTROL_LOGIC_LINE\b", section_raw)
        if first_line:
            anchor_rel = first_line.start()
    at_close = anchor_rel < 0
    if at_close:
        anchor_rel = section_raw.rfind(close)
    anchor = section_start + anchor_rel
    line_start = text.rfind("\n", 0, anchor) + 1
    indent = line_indent_at(text, anchor)
    if at_close:
        # Anchored on the section close tag, so children sit one level deeper.
        indent = indent + indent_step(text)
    body = "\n".join(indent + part if part.strip() else part for part in xml.split("\n"))
    body = to_document_eol(body, text)
    return text[:line_start] + body + document_eol(text) + text[line_start:]


def cmd_set_pin(args: argparse.Namespace) -> int:
    updates = parse_attr_updates(args.attr or [])
    for flag, key in (
        (args.init_value, "INIT_VALUE"),
        (args.enabled, "ENABLED"),
        (args.negated, "NEGATED"),
        (args.visible, "VISIBLE"),
        (args.desc, "DESC"),
    ):
        if flag is not None:
            updates[key] = flag

    bound = [item for item in (args.bind, args.bind_line) if item is not None]
    if len(bound) > 1:
        raise ValueError("--bind and --bind-line are mutually exclusive")
    if args.unbind and bound:
        raise ValueError("--unbind cannot be combined with --bind / --bind-line")
    if args.unbind:
        connection: object = None
    elif args.bind is not None:
        connection = (CONNECTION_TYPE_VARIABLE, args.bind)
    elif args.bind_line is not None:
        connection = (CONNECTION_TYPE_LINE, args.bind_line)
    else:
        connection = KEEP_CONNECTION
    if not updates and connection is KEEP_CONNECTION:
        raise ValueError("nothing to change; pass --bind/--bind-line/--unbind or an attribute option")

    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    if args.bind is not None and not args.allow_unknown_operand:
        known = existing_names(root)
        operand = args.bind.split("[")[0].split(".")[0]
        local = pou_local_var_names(root, pou_tag(args.pou_type), args.pou)
        if operand not in known["variable"] and operand not in known["hardware_tag"] and operand not in local:
            raise ValueError(
                f"operand {args.bind!r} is not a VARIABLE, a HARDWARE_CHANNEL_TAG, or a local variable of "
                f"{args.pou!r} (use --allow-unknown-operand to force)"
            )

    start, end, raw, tag = find_graphic_pin_element(
        text, pou_tag(args.pou_type), args.pou, args.block, args.pin, args.pin_dir
    )
    indent = line_indent_at(text, start)
    new_pin = to_document_eol(rebuild_pin(raw, indent, updates, connection, indent_step(text)), text)
    new_text = text[:start] + new_pin + text[end:]
    detail = "keep" if connection is KEEP_CONNECTION else ("unbound" if connection is None else f"{connection[1]}")
    return finish_write(
        args,
        new_text,
        f"SetPin={args.pou}/{args.block}/{tag}:{args.pin} connection={detail} attrs={','.join(sorted(updates)) or '-'}",
    )


def cmd_connect_pins(args: argparse.Namespace) -> int:
    """Wire one output pin to one input pin through a CONTROL_LOGIC_LINE."""
    text = read_text(args.project, args.encoding)
    pou_tag_name = pou_tag(args.pou_type)
    section_start, section_end, section_raw, section_tag = find_graphic_section_span(text, pou_tag_name, args.pou)
    line_name = args.line_name or next_free_name(section_line_names(section_raw), "_LINE")
    if line_name in section_line_names(section_raw):
        raise ValueError(f"line {line_name!r} already exists in this section")

    from_start, from_end, from_raw, from_tag = find_graphic_pin_element(
        text, pou_tag_name, args.pou, args.from_block, args.from_pin, "output"
    )
    to_start, to_end, to_raw, to_tag = find_graphic_pin_element(
        text, pou_tag_name, args.pou, args.to_block, args.to_pin, "input"
    )
    if from_start == to_start:
        raise ValueError("source and target pin are the same element")

    line_position = args.line_position or ""
    if not line_position:
        line_position = approximate_line_position(text, section_start, section_end, args.from_block, args.to_block)
    line_attrs = {
        "DEACTIVE": "",
        "FROM_POWERRAIL": "NO",
        "LINE_POSITION": line_position,
        "NAME": line_name,
        "POSITION_TYPE": "0",
        "TYPE": "",
    }

    # Patch the later pin first so the earlier offsets stay valid.
    step = indent_step(text)
    edits = sorted(
        [(from_start, from_end, from_raw), (to_start, to_end, to_raw)],
        key=lambda item: item[0],
        reverse=True,
    )
    new_text = text
    for start, end, raw in edits:
        indent = line_indent_at(new_text, start)
        rebuilt = to_document_eol(rebuild_pin(raw, indent, {}, (CONNECTION_TYPE_LINE, line_name), step), new_text)
        new_text = new_text[:start] + rebuilt + new_text[end:]

    section_start, section_end, _, section_tag = find_graphic_section_span(new_text, pou_tag_name, args.pou)
    new_text = insert_into_section(
        new_text,
        section_start,
        section_end,
        section_tag,
        xml_start_tag("CONTROL_LOGIC_LINE", line_attrs, True),
        before_lines=False,
    )
    if not args.line_position:
        print("WARNING: LINE_POSITION is an approximation; open the page in xRobotDesigner and drag the wire if it looks wrong")
    return finish_write(
        args,
        new_text,
        f"Connected={args.pou}: {args.from_block}.{args.from_pin} -> {args.to_block}.{args.to_pin} via {line_name}",
    )


def approximate_line_position(text: str, section_start: int, section_end: int, from_block: str, to_block: str) -> str:
    """Build a 3-point polyline between two block rectangles.

    GUI files always store three points; the middle one is the elbow.  Pin row
    coordinates are not stored per pin, so this only approximates the routing.
    """
    section_raw = text[section_start:section_end]

    def rect(block_name: str) -> tuple[int, int, int, int]:
        _, _, attrs = find_start_tag_span(
            section_raw, "CONTROL_LOGIC_BLOCK", lambda attrs_map: attrs_map.get("NAME") == block_name
        )
        parts = [int(float(value)) for value in (attrs.get("RECT_POSITION", "0,0,0,0")).split(",")]
        while len(parts) < 4:
            parts.append(0)
        return parts[0], parts[1], parts[2], parts[3]

    fx1, fy1, fx2, fy2 = rect(from_block)
    tx1, ty1, tx2, ty2 = rect(to_block)
    start_x, start_y = fx2, (fy1 + fy2) // 2
    end_x, end_y = tx1, (ty1 + ty2) // 2
    mid_x = (start_x + end_x) // 2
    return f"{start_x},{start_y},{mid_x},{end_y},{end_x},{end_y}"


def cmd_disconnect_line(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    pou_tag_name = pou_tag(args.pou_type)
    section_start, section_end, section_raw, section_tag = find_graphic_section_span(text, pou_tag_name, args.pou)
    if args.line_name not in section_line_names(section_raw):
        raise ValueError(f"line {args.line_name!r} not found in {args.pou!r}")

    new_section = section_raw
    pattern = re.compile(
        r"[ \t]*<CONTROL_BLOCK_CONNECTION\b[^>]*CONNECTION_VALUE=\"" + re.escape(args.line_name) + r"\"[^>]*>\n?"
    )
    cleared = len(pattern.findall(new_section))
    new_section = pattern.sub("", new_section)
    line_pattern = re.compile(
        r"[ \t]*<CONTROL_LOGIC_LINE\b[^>]*\bNAME=\"" + re.escape(args.line_name) + r"\"[^>]*>\n?"
    )
    new_section = line_pattern.sub("", new_section)
    new_section = collapse_empty_pins(new_section)
    new_text = text[:section_start] + new_section + text[section_end:]
    return finish_write(args, new_text, f"DisconnectedLine={args.pou}:{args.line_name} pins={cleared}")


def collapse_empty_pins(section_raw: str) -> str:
    """Turn pin elements that no longer hold a connection child back into self-closing tags."""

    def repl(match: re.Match[str]) -> str:
        tag = match.group(1)
        start_tag = match.group(0)[: match.group(0).find(">") + 1]
        return start_tag[:-1].rstrip() + "/>"

    return re.sub(
        r"<(BLOCK_PIN_INPUT|BLOCK_PIN_OUTPUT)\b[^>]*>\s*</\1>",
        repl,
        section_raw,
    )


def reindent_block(raw: str, from_indent: str, to_indent: str) -> str:
    lines = raw.split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        stripped = line.lstrip(" \t")
        prefix = line[: len(line) - len(stripped)]
        if from_indent and prefix.startswith(from_indent):
            prefix = to_indent + prefix[len(from_indent):]
        out.append(prefix + stripped)
    return "\n".join(out)


def cmd_copy_block(args: argparse.Namespace) -> int:
    """Copy one CONTROL_LOGIC_BLOCK from a reference project into a target POU."""
    text = read_text(args.project, args.encoding)
    ref_text = read_text(args.reference, args.encoding)
    ref_tag = pou_tag(args.reference_pou_type or args.pou_type)
    ref_section_start, _, ref_section_raw, _ = find_graphic_section_span(ref_text, ref_tag, args.reference_pou)
    block_start, block_end, block_raw, _ = find_element_span(
        ref_section_raw,
        "CONTROL_LOGIC_BLOCK",
        lambda attrs_map: attrs_map.get("NAME") == args.block,
        offset=ref_section_start,
    )
    source_indent = line_indent_at(ref_text, block_start)

    section_start, section_end, section_raw, section_tag = find_graphic_section_span(
        text, pou_tag(args.pou_type), args.pou
    )
    used = re.findall(r"<CONTROL_LOGIC_BLOCK\b[^>]*\bNAME=\"([^\"]*)\"", section_raw)
    target_name = args.target_name or next_free_name(used, "_MODULE")
    if target_name in used:
        raise ValueError(f"block {target_name!r} already exists in the target section")

    new_block = block_raw
    if not args.keep_connections:
        new_block = re.sub(r"[ \t]*<CONTROL_BLOCK_CONNECTION\b[^>]*>\n?", "", new_block)
        new_block = collapse_empty_pins(new_block)
    start_tag_match = re.match(START_TAG_RE_TEMPLATE.format(tag="CONTROL_LOGIC_BLOCK"), new_block, flags=re.DOTALL)
    patched_updates = {"NAME": target_name}
    if args.rect_position:
        patched_updates["RECT_POSITION"] = args.rect_position
    patched_start = patch_start_tag_attrs(start_tag_match.group(0), patched_updates)
    new_block = patched_start + new_block[start_tag_match.end():]
    new_block = reindent_block(new_block, source_indent, "")

    new_text = insert_into_section(text, section_start, section_end, section_tag, new_block, before_lines=True)
    return finish_write(
        args,
        new_text,
        f"CopiedBlock={args.block} -> {args.pou}/{target_name} connections={'kept' if args.keep_connections else 'stripped'}",
    )


def next_program_id(root: ET.Element) -> str:
    """Program IDs are unique across the whole project, not per task."""
    used = set()
    for program in root.iter("PROGRAM"):
        value = attr(program, "ID")
        if value.isdigit():
            used.add(int(value))
    candidate = 0
    while candidate in used:
        candidate += 1
    return str(candidate)


def detect_pou_var_visible(root: ET.Element) -> str | None:
    """Mirror whether this project writes VISIBLE on POU interface variables."""
    for section_tag in POU_VAR_SECTIONS.values():
        for var in root.iter(section_tag):
            return var.attrib.get("VISIBLE")
    return "YES"


def find_task_span(text: str, task_id: str | None, task_kind: str | None) -> tuple[int, int, str, str]:
    """Locate one task element: (start, end, raw, tag)."""
    tags = [TASK_TAGS[task_kind]] if task_kind else list(TASK_TAGS.values())
    last_error = None
    for tag in tags:
        try:
            start, end, raw, _ = find_element_span(
                text, tag, lambda attrs_map: task_id is None or attrs_map.get("ID") == task_id
            )
        except ValueError as exc:
            last_error = exc
            continue
        return start, end, raw, tag
    raise ValueError(str(last_error) if last_error else "no control scheme task found")


def program_positions(text: str, task_start: int, task_end: int) -> list[dict[str, object]]:
    """List the PROGRAM elements of one task in document (execution) order."""
    task_raw = text[task_start:task_end]
    rows: list[dict[str, object]] = []
    for match in re.finditer(r"<PROGRAM\b[^>]*>", task_raw):
        attrs_map = parse_start_tag_attrs(match.group(0))
        close = task_raw.find("</PROGRAM>", match.end())
        if close < 0:
            raise ValueError("PROGRAM close tag not found")
        rows.append(
            {
                "name": attrs_map.get("NAME", ""),
                "id": attrs_map.get("ID", ""),
                "start": task_start + match.start(),
                "end": task_start + close + len("</PROGRAM>"),
            }
        )
    return rows


def resolve_insert_offset(
    text: str,
    task_start: int,
    task_end: int,
    task_tag: str,
    after: str | None,
    before: str | None,
    index: int | None,
) -> tuple[int, str]:
    """Return (insert offset, child indent) for a new PROGRAM inside a task."""
    programs = program_positions(text, task_start, task_end)
    close = text.rfind("</" + task_tag + ">", task_start, task_end)
    if close < 0:
        raise ValueError(f"{task_tag} close tag not found")

    if programs:
        indent = line_indent_at(text, int(programs[0]["start"]))
    else:
        indent = line_indent_at(text, close) + indent_step(text)

    target = None
    if after is not None:
        match = next((row for row in programs if row["name"] == after), None)
        if match is None:
            raise ValueError(f"PROGRAM {after!r} not found in this task")
        target = int(match["end"])
        line_end = text.find("\n", target)
        return (line_end + 1 if line_end >= 0 else target), indent
    if before is not None:
        match = next((row for row in programs if row["name"] == before), None)
        if match is None:
            raise ValueError(f"PROGRAM {before!r} not found in this task")
        target = int(match["start"])
    elif index is not None:
        if index < 0:
            index += len(programs)
        if index < 0 or index >= len(programs):
            target = None
        else:
            target = int(programs[index]["start"])

    if target is None:
        return text.rfind("\n", task_start, close) + 1, indent
    return text.rfind("\n", task_start, target) + 1, indent


def render_program(name: str, attrs: dict[str, str], lang: str, indent: str, step: str) -> str:
    if lang == "st":
        body = indent + step + '<SECTION_LOGIC_ST CONTENT="" />'
    else:
        section = GRAPHIC_SECTION_BY_LANG[lang]
        body = indent + step + "<" + section + ">\n" + indent + step + "</" + section + ">"
    return (
        indent
        + xml_start_tag("PROGRAM", attrs, False)
        + "\n"
        + body
        + "\n"
        + indent
        + "</PROGRAM>"
    )


def parse_pou_var_specs(
    specs: list[str] | None,
    section: str,
    visible: str | None,
    auto_init: bool,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for spec in specs or []:
        parts = spec.split(":", 2)
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f"--{section} must use NAME:DATATYPE[:DESC] form: {spec!r}")
        name = parts[0].strip()
        datatype = parts[1].strip()
        check_identifier(name, "POU variable")
        base, count, _ = parse_datatype(datatype)
        init = ""
        if auto_init and count is None:
            init = TYPE_DEFAULT_INIT.get(base, "")
        row = {"DATATYPE": datatype, "DESC": parts[2] if len(parts) > 2 else "", "INIT_VALUE": init, "NAME": name}
        if visible is not None:
            row["VISIBLE"] = visible
        rows.append(row)
    return rows


def render_function_block(
    name: str,
    attrs: dict[str, str],
    lang: str,
    sections: dict[str, list[dict[str, str]]],
    indent: str,
    step: str,
) -> str:
    lines = [indent + xml_start_tag("FUNCTION_BLOCK", attrs, False)]
    if lang == "st":
        lines.append(indent + step + '<SECTION_LOGIC_ST CONTENT="" />')
    else:
        section = GRAPHIC_SECTION_BY_LANG[lang]
        lines.append(indent + step + "<" + section + ">")
        lines.append(indent + step + "</" + section + ">")
    # GUI order: logic section, inputs, internals, outputs.
    for kind in ("input", "internal", "output"):
        for row in sections.get(kind, []):
            lines.append(indent + step + xml_start_tag(POU_VAR_SECTIONS[kind], row, True))
    lines.append(indent + "</FUNCTION_BLOCK>")
    return "\n".join(lines)


def is_task_element(elem: ET.Element) -> bool:
    return elem.tag.endswith("_TASK") or elem.find("./PROGRAM") is not None


def collect_task_rows(root: ET.Element) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scheme in root.findall(".//CONTROL_SCHEME"):
        for task in list(scheme):
            if not is_task_element(task):
                continue
            kind = TASK_KIND_BY_TAG.get(task.tag, task.tag.lower())
            trigger = task.find("./TRIG_CONDITION")
            rows.append(
                {
                    "kind": kind,
                    "tag": task.tag,
                    "id": attr(task, "ID"),
                    "priority": TASK_PRIORITY.get(kind, 9),
                    "cycle_ms": attr(task, "CYCLE"),
                    "trigger": attr(task, "EVENT_NAME")
                    or (attr(trigger, "VAR") if trigger is not None else ""),
                    "programs": len(task.findall("./PROGRAM")),
                    "order": " > ".join(attr(program, "NAME") for program in task.findall("./PROGRAM")),
                    "desc": attr(task, "DESC"),
                }
            )
    rows.sort(key=lambda row: (row["priority"], str(row["id"])))
    return rows


def cmd_list_tasks(args: argparse.Namespace) -> int:
    root = parse_xml(read_text(args.project, args.encoding))
    rows = collect_task_rows(root)
    output_rows(
        rows,
        ["kind", "tag", "id", "priority", "cycle_ms", "trigger", "programs", "order", "desc"],
        args.format,
        args.output,
        args.output_encoding,
    )
    return 0


def cmd_add_task(args: argparse.Namespace) -> int:
    """Create a CYCLE_TASK.

    Only cycle tasks are synthesized.  An event task needs a TRIG_CONDITION whose
    encoding is only partly known and whose EVENT_NAME label the GUI composes,
    and the startup task tag has never been observed, so both are left to the GUI.
    """
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    used = {attr(task, "ID") for scheme in root.findall(".//CONTROL_SCHEME") for task in list(scheme)}
    task_id = args.id
    if task_id is None:
        candidate = 1
        while str(candidate) in used:
            candidate += 1
        task_id = str(candidate)
    if task_id in used:
        raise ValueError(f"task ID {task_id!r} is already used")
    if args.cycle <= 0:
        raise ValueError("--cycle must be a positive number of milliseconds")

    attrs = {"CYCLE": str(args.cycle), "DESC": args.desc or "", "ID": task_id}

    def build(indent: str) -> str:
        return indent + xml_start_tag("CYCLE_TASK", attrs, False) + "\n" + indent + "</CYCLE_TASK>"

    new_text = insert_container_child(text, "CONTROL_SCHEME", build)
    return finish_write(args, new_text, f"AddedTask=CYCLE_TASK id={task_id} cycle={args.cycle}ms")


def cmd_add_program(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    check_identifier_loose(args.name, "program")
    if any(attr(program, "NAME") == args.name for program in root.iter("PROGRAM")):
        raise ValueError(f"PROGRAM {args.name!r} already exists")

    task_start, task_end, _, task_tag = find_task_span(text, args.task_id, args.task_kind)
    if task_tag == "EVENT_TASK" and program_positions(text, task_start, task_end):
        raise ValueError("an EVENT_TASK may hold only one program; add it to another task")
    offset, indent = resolve_insert_offset(
        text, task_start, task_end, task_tag, args.after, args.before, args.index
    )

    attrs = dict(PROGRAM_DEFAULT_ATTRS)
    attrs["NAME"] = args.name
    attrs["ID"] = args.id or next_program_id(root)
    attrs["LOGIC_LANG"] = LOGIC_LANG_BY_NAME[args.lang]
    if args.desc is not None:
        attrs["DESC"] = args.desc
    attrs.update(parse_attr_updates(args.attr or []))

    xml = to_document_eol(render_program(args.name, attrs, args.lang, indent, indent_step(text)), text)
    new_text = text[:offset] + xml + document_eol(text) + text[offset:]
    if args.lang != "st":
        print("WARNING: an empty LD/FBD page is not covered by any observed project; open it in the GUI to confirm")
    return finish_write(
        args,
        new_text,
        f"AddedProgram={args.name} id={attrs['ID']} lang={args.lang} task={task_tag}",
    )


def cmd_move_program(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    if args.after is None and args.before is None and args.index is None:
        raise ValueError("pass --after, --before, or --index to say where the program should go")
    if args.after == args.name or args.before == args.name:
        raise ValueError("a program cannot be placed relative to itself")

    span_start, span_end, span_raw, _ = find_element_span(
        text, "PROGRAM", lambda attrs_map: attrs_map.get("NAME") == args.name
    )
    line_start = text.rfind("\n", 0, span_start) + 1
    cut_start = line_start if not text[line_start:span_start].strip() else span_start
    cut_end = span_end + 1 if text[span_end:span_end + 1] == "\n" else span_end
    block = text[cut_start:cut_end]
    without = text[:cut_start] + text[cut_end:]

    task_start, task_end, _, task_tag = find_task_span(without, args.task_id, args.task_kind)
    if task_tag == "EVENT_TASK" and program_positions(without, task_start, task_end):
        raise ValueError("an EVENT_TASK may hold only one program; move it to another task")
    offset, indent = resolve_insert_offset(
        without, task_start, task_end, task_tag, args.after, args.before, args.index
    )
    source_indent = line_indent_at(text, span_start)
    if source_indent != indent:
        block = reindent_block(block.rstrip("\n"), source_indent, indent) + "\n"
        block = indent + block.lstrip(" \t")
    new_text = without[:offset] + block + without[offset:]

    order = [str(row["name"]) for row in program_positions(new_text, *find_task_span(new_text, args.task_id, args.task_kind)[:2])]
    return finish_write(args, new_text, f"MovedProgram={args.name} order={' > '.join(order)}")


def cmd_add_function_block(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    check_identifier(args.name, "function block")
    if any(attr(block, "NAME") == args.name for block in root.iter("FUNCTION_BLOCK")):
        raise ValueError(f"FUNCTION_BLOCK {args.name!r} already exists")

    visible = detect_pou_var_visible(root) if args.var_visible == "auto" else (
        None if args.var_visible == "no" else "YES"
    )
    auto_init = args.var_init != "none"
    sections = {
        "input": parse_pou_var_specs(args.input, "input", visible, auto_init),
        "internal": parse_pou_var_specs(args.internal, "internal", visible, auto_init),
        "output": parse_pou_var_specs(args.output, "output", visible, auto_init),
    }
    seen: set[str] = set()
    for rows in sections.values():
        for row in rows:
            if row["NAME"] in seen:
                raise ValueError(f"duplicate POU variable {row['NAME']!r}")
            seen.add(row["NAME"])

    attrs = dict(FUNCTION_BLOCK_DEFAULT_ATTRS)
    attrs["NAME"] = args.name
    attrs["LOGIC_LANG"] = LOGIC_LANG_BY_NAME[args.lang]
    if args.desc is not None:
        attrs["DESC"] = args.desc
    attrs.update(parse_attr_updates(args.attr or []))

    step = indent_step(text)
    new_text = insert_container_child(
        text,
        "FUNCTION_BLOCK_LIST",
        lambda indent: render_function_block(args.name, attrs, args.lang, sections, indent, step),
    )
    if args.lang != "st":
        print("WARNING: an empty LD/FBD section is not covered by any observed project; open it in the GUI to confirm")
    total = sum(len(rows) for rows in sections.values())
    return finish_write(args, new_text, f"AddedFunctionBlock={args.name} lang={args.lang} vars={total}")


def cmd_add_pou_var(args: argparse.Namespace) -> int:
    text = read_text(args.project, args.encoding)
    root = parse_xml(text)
    tag = pou_tag(args.pou_type)
    pou = next((elem for elem in root.iter(tag) if attr(elem, "NAME") == args.name), None)
    if pou is None:
        raise ValueError(f"{tag} {args.name!r} not found")
    existing = {
        attr(var, "NAME")
        for section_tag in POU_VAR_SECTIONS.values()
        for var in pou.findall("./" + section_tag)
    }
    visible = detect_pou_var_visible(root) if args.var_visible == "auto" else (
        None if args.var_visible == "no" else "YES"
    )
    rows = parse_pou_var_specs(args.var, args.var_section, visible, args.var_init != "none")
    if not rows:
        raise ValueError("at least one --var entry is required")
    for row in rows:
        if row["NAME"] in existing:
            raise ValueError(f"POU variable {row['NAME']!r} already exists in {args.name!r}")

    span = find_named_span(text, tag, args.name)
    section_tag = POU_VAR_SECTIONS[args.var_section]
    last_end = None
    for match in re.finditer(r"[ \t]*<" + section_tag + r"\b[^>]*>\n?", span.raw):
        last_end = match.end()
    if last_end is None:
        close = span.raw.rfind("</" + tag + ">")
        last_end = span.raw.rfind("\n", 0, close) + 1
        indent = line_indent_at(text, span.start) + indent_step(text)
    else:
        indent = line_indent_at(span.raw, last_end - 1) or line_indent_at(text, span.start) + indent_step(text)

    eol = document_eol(text)
    addition = "".join(
        indent + xml_start_tag(section_tag, row, True) + eol for row in rows
    )
    new_raw = span.raw[:last_end] + addition + span.raw[last_end:]
    new_text = text[:span.start] + new_raw + text[span.end:]
    return finish_write(
        args,
        new_text,
        f"AddedPouVars={args.pou_type}:{args.name}:{args.var_section} count={len(rows)}",
    )


def add_common_project_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--encoding", default=DEFAULT_ENCODING)


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["table", "json", "csv"], default="table")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-encoding", default="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kecon xRobotDesigner .xcskr helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("summary", help="print project-level summary")
    add_common_project_arg(p)
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("inspect", help="alias of summary plus POU/downlink summary")
    add_common_project_arg(p)
    p.set_defaults(func=lambda args: (cmd_summary(args) or cmd_list_pous(argparse.Namespace(**vars(args), format="table", output=None, output_encoding="utf-8")) or cmd_list_downlinks(argparse.Namespace(**vars(args), format="table", output=None, output_encoding="utf-8"))))

    p = sub.add_parser("export-ai", help="export a token-efficient AI-readable project package")
    add_common_project_arg(p)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--st-mode", choices=["none", "inline", "files"], default="files", help="store ST as separate files, inline JSON text, or metadata only")
    p.set_defaults(func=cmd_export_ai)

    p = sub.add_parser("list-pous", help="list PROGRAM/FUNCTION_BLOCK/FUNCTION entries")
    add_common_project_arg(p)
    add_output_args(p)
    p.set_defaults(func=cmd_list_pous)

    p = sub.add_parser("export-ld", help="deprecated alias of export-graphic limited to PROGRAM POUs")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--program", help="specific PROGRAM NAME to export; omit to export all LD programs")
    p.set_defaults(func=cmd_export_ld)

    p = sub.add_parser("extract-st", help="extract ST CONTENT from a named POU")
    add_common_project_arg(p)
    p.add_argument("--pou-type", required=True, choices=sorted(POU_TAGS))
    p.add_argument("--name", required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--output-encoding", default="utf-8")
    p.set_defaults(func=cmd_extract_st)

    p = sub.add_parser("replace-st", help="replace ST CONTENT of a named POU using safe raw XML patching")
    add_common_project_arg(p)
    p.add_argument("--pou-type", required=True, choices=sorted(POU_TAGS))
    p.add_argument("--name", required=True)
    p.add_argument("--st-file", required=True, type=Path)
    p.add_argument("--st-encoding", default="utf-8")
    p.add_argument("--newline-style", choices=["auto", "literal", "numeric", "crlf-numeric"], default="auto", help="line break encoding inside the ST attribute; auto keeps what the POU or project already uses")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_replace_st)

    p = sub.add_parser("set-attrs", help="set attributes on selected structured project entities without hand-editing XML")
    add_common_project_arg(p)
    p.add_argument("--kind", required=True, choices=["variable", "hardware-tag", "user-struct", "user-struct-member", "pou", "pou-var", "task", "trig-condition", "block", "downlink-port", "station", "slave-object", "slave-mapping"])
    p.add_argument("--name", help="entity name, or POU name for kind=pou/pou-var")
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), help="required for kind=pou or kind=pou-var")
    p.add_argument("--var-section", choices=["input", "output", "internal"], help="required for kind=pou-var")
    p.add_argument("--var", help="POU variable name for kind=pou-var")
    p.add_argument("--struct", help="user structure name for kind=user-struct or kind=user-struct-member")
    p.add_argument("--member", help="user structure member name for kind=user-struct-member")
    p.add_argument("--block", help="CONTROL_LOGIC_BLOCK NAME for kind=block")
    p.add_argument("--task-id", help="task ID for kind=task or kind=trig-condition")
    p.add_argument("--task-kind", choices=sorted(TASK_TAGS), help="task kind for kind=task or kind=trig-condition")
    p.add_argument("--port-id", help="downlink port ID for kind=downlink-port")
    p.add_argument("--address", help="station address for kind=station")
    p.add_argument("--index", help="CANopen slave object index in decimal for kind=slave-object/slave-mapping")
    p.add_argument("--offset", help="mapping offset for kind=slave-mapping")
    p.add_argument("--attr", action="append", required=True, help="attribute update in KEY=VALUE form; repeat for multiple attributes")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_set_attrs)

    p = sub.add_parser("copy-pou", help="replace an existing POU with the same POU from a reference project")
    add_common_project_arg(p)
    p.add_argument("--reference", required=True, type=Path)
    p.add_argument("--pou-type", required=True, choices=sorted(POU_TAGS))
    p.add_argument("--name", required=True)
    p.add_argument("--target-name")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_copy_pou)

    p = sub.add_parser("validate-st-format", help="warn when multi-statement ST lacks raw XML line breaks")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--min-statements", type=int, default=3)
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=cmd_validate_st_format)

    p = sub.add_parser("list-downlinks", help="list HARDWARE_DEVICE_DOWNLINK_PORT summaries")
    add_common_project_arg(p)
    add_output_args(p)
    p.set_defaults(func=cmd_list_downlinks)

    p = sub.add_parser("list-slave-objects", help="list CANopen slave object dictionary entries")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--port-id")
    p.set_defaults(func=cmd_list_slave_objects)

    p = sub.add_parser("export-slave-mappings", help="export CANopen slave object mapping rows")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--port-id")
    p.set_defaults(func=cmd_export_slave_mappings)

    p = sub.add_parser("list-hardware-tags", help="list generated HARDWARE_CHANNEL_TAG entries")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--pattern", help="regular expression matched against tag name")
    p.set_defaults(func=cmd_list_hardware_tags)

    p = sub.add_parser("validate-canopen-command-ids", help="validate non-empty CANopen master command IDs are unique")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--scope", choices=["project", "port"], default="project", help="check uniqueness across the project or within each downlink port")
    p.add_argument("--enabled-only", action="store_true", help="only check command groups with HARDWARE_GROUP_ENABLE=YES")
    p.add_argument("--show-all", action="store_true", help="print all checked rows when validation passes")
    p.set_defaults(func=cmd_validate_canopen_command_ids)

    p = sub.add_parser("export-graphic", help="export LD/FBD graphical logic: blocks, pins, connections, lines, comments")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--pou", help="POU name to export; omit to export every graphical POU")
    p.add_argument("--program", help="alias of --pou kept for older call sites")
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), help="restrict to one POU kind")
    p.add_argument("--level", choices=["block", "pin"], default="block", help="table/csv detail level; json always returns the full tree")
    p.set_defaults(func=cmd_export_graphic)

    p = sub.add_parser("add-user-struct", help="create a USER_STRUCT under USER_DATA_TYPE")
    add_common_project_arg(p)
    p.add_argument("--name", required=True)
    p.add_argument("--desc")
    p.add_argument("--member", action="append", help="NAME:DATATYPE[:DESC]; repeat for each member")
    p.add_argument("--members-json", type=Path, help="JSON file with a members list")
    p.add_argument("--input-encoding", default="utf-8")
    p.add_argument("--attr", action="append", help="extra USER_STRUCT attribute in KEY=VALUE form")
    p.add_argument("--allow-unknown-datatype", action="store_true")
    p.add_argument("--replace", action="store_true", help="overwrite an existing struct of the same name")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_user_struct)

    p = sub.add_parser("add-user-struct-member", help="append members to an existing USER_STRUCT")
    add_common_project_arg(p)
    p.add_argument("--struct", required=True)
    p.add_argument("--member", action="append", help="NAME:DATATYPE[:DESC]; repeat for each member")
    p.add_argument("--members-json", type=Path)
    p.add_argument("--input-encoding", default="utf-8")
    p.add_argument("--allow-unknown-datatype", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_user_struct_member)

    p = sub.add_parser("add-variable", help="create a user VARIABLE together with its VARIABLE_MEMBER tree")
    add_common_project_arg(p)
    p.add_argument("--name", required=True)
    p.add_argument("--datatype", required=True, help="BOOL, REAL, UINT[8], MyStruct, MyStruct[8], MyStruct[1..8]")
    p.add_argument("--desc")
    p.add_argument("--init-value")
    p.add_argument("--element-init", help="INIT_VALUE for generated array element members; use auto for the per-type GUI default")
    p.add_argument("--member-readonly", choices=["auto", "yes", "no"], default="auto", help="write READONLY on array element members; auto mirrors the project")
    p.add_argument("--readonly", choices=["YES", "NO"])
    p.add_argument("--visible", choices=["YES", "NO"])
    p.add_argument("--cold-retain", choices=["YES", "NO"])
    p.add_argument("--container", choices=["tagconfig", "global"], default="tagconfig", help="TAGCONFIG is where xRobotDesigner keeps user variables")
    p.add_argument("--template", help="copy the attribute set of an existing VARIABLE")
    p.add_argument("--attr", action="append", help="extra VARIABLE attribute in KEY=VALUE form")
    p.add_argument("--allow-unknown-datatype", action="store_true")
    p.add_argument("--replace", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_variable)

    p = sub.add_parser("rebuild-variable-members", help="regenerate a VARIABLE member tree from its DATATYPE and the current USER_STRUCT definitions")
    add_common_project_arg(p)
    p.add_argument("--name", required=True)
    p.add_argument("--element-init")
    p.add_argument("--member-readonly", choices=["auto", "yes", "no"], default="auto")
    p.add_argument("--allow-unknown-datatype", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_rebuild_variable_members)

    p = sub.add_parser("remove", help="delete a VARIABLE or USER_STRUCT")
    add_common_project_arg(p)
    p.add_argument("--kind", required=True, choices=["variable", "user-struct"])
    p.add_argument("--name", required=True)
    p.add_argument("--force", action="store_true", help="remove a USER_STRUCT even when variables still use it")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_remove_entity)

    p = sub.add_parser("validate-datatypes", help="check VARIABLE / USER_STRUCT datatypes and member tree consistency")
    add_common_project_arg(p)
    add_output_args(p)
    p.add_argument("--strict", action="store_true", help="exit non-zero when problems are found")
    p.add_argument("--show-all", action="store_true", help="print every checked row, not only problems")
    p.set_defaults(func=cmd_validate_datatypes)

    p = sub.add_parser("list-tasks", help="list control scheme tasks with period, trigger and program order")
    add_common_project_arg(p)
    add_output_args(p)
    p.set_defaults(func=cmd_list_tasks)

    p = sub.add_parser("add-task", help="create a CYCLE_TASK; event and startup tasks must be created in the GUI")
    add_common_project_arg(p)
    p.add_argument("--kind", choices=["cycle"], default="cycle")
    p.add_argument("--cycle", type=int, required=True, help="period in milliseconds")
    p.add_argument("--desc")
    p.add_argument("--id", help="explicit task ID; default is the next free id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_task)

    p = sub.add_parser("add-program", help="create a PROGRAM inside a control scheme task")
    add_common_project_arg(p)
    p.add_argument("--name", required=True)
    p.add_argument("--desc")
    p.add_argument("--lang", choices=["st", "ld", "fbd"], default="st")
    p.add_argument("--task-kind", choices=sorted(TASK_TAGS), help="restrict to main/event/cycle task")
    p.add_argument("--task-id", help="task ID when the project has more than one")
    p.add_argument("--after", help="place the new program after this program")
    p.add_argument("--before", help="place the new program before this program")
    p.add_argument("--index", type=int, help="place at this 0-based position in the task")
    p.add_argument("--id", help="explicit PROGRAM ID; default is the next free project-wide id")
    p.add_argument("--attr", action="append")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_program)

    p = sub.add_parser("move-program", help="reorder a PROGRAM within its task; programs execute in document order")
    add_common_project_arg(p)
    p.add_argument("--name", required=True)
    p.add_argument("--after")
    p.add_argument("--before")
    p.add_argument("--index", type=int)
    p.add_argument("--task-kind", choices=sorted(TASK_TAGS))
    p.add_argument("--task-id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_move_program)

    p = sub.add_parser("add-function-block", help="create a FUNCTION_BLOCK with its interface variables")
    add_common_project_arg(p)
    p.add_argument("--name", required=True)
    p.add_argument("--desc")
    p.add_argument("--lang", choices=["st", "ld", "fbd"], default="st")
    p.add_argument("--input", action="append", help="NAME:DATATYPE[:DESC]; repeat")
    p.add_argument("--output", action="append", help="NAME:DATATYPE[:DESC]; repeat")
    p.add_argument("--internal", action="append", help="NAME:DATATYPE[:DESC]; repeat")
    p.add_argument("--var-visible", choices=["auto", "yes", "no"], default="auto")
    p.add_argument("--var-init", choices=["auto", "none"], default="auto", help="auto fills the per-type default the GUI writes")
    p.add_argument("--attr", action="append")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_function_block)

    p = sub.add_parser("add-pou-var", help="append interface variables to an existing POU")
    add_common_project_arg(p)
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), default="function-block")
    p.add_argument("--name", required=True)
    p.add_argument("--var-section", choices=sorted(POU_VAR_SECTIONS), required=True)
    p.add_argument("--var", action="append", help="NAME:DATATYPE[:DESC]; repeat")
    p.add_argument("--var-visible", choices=["auto", "yes", "no"], default="auto")
    p.add_argument("--var-init", choices=["auto", "none"], default="auto")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_add_pou_var)

    p = sub.add_parser("set-pin", help="bind or patch one LD/FBD block pin")
    add_common_project_arg(p)
    p.add_argument("--pou", required=True, help="POU name that owns the graphical section")
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), default="program")
    p.add_argument("--block", required=True, help="CONTROL_LOGIC_BLOCK NAME, e.g. _MODULE0")
    p.add_argument("--pin", required=True)
    p.add_argument("--pin-dir", choices=["auto", "input", "output"], default="auto")
    p.add_argument("--bind", help="bind the pin to a variable or hardware tag (CONNECTION_TYPE=1)")
    p.add_argument("--bind-line", help="bind the pin to an existing CONTROL_LOGIC_LINE name (CONNECTION_TYPE=2)")
    p.add_argument("--unbind", action="store_true", help="drop the CONTROL_BLOCK_CONNECTION child")
    p.add_argument("--allow-unknown-operand", action="store_true", help="allow --bind to name something this project does not define")
    p.add_argument("--init-value")
    p.add_argument("--desc")
    p.add_argument("--enabled", choices=["YES", "NO"])
    p.add_argument("--negated", choices=["YES", "NO", ""])
    p.add_argument("--visible", choices=["YES", "NO"])
    p.add_argument("--attr", action="append", help="raw attribute update in KEY=VALUE form")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_set_pin)

    p = sub.add_parser("connect-pins", help="wire an output pin to an input pin through a new CONTROL_LOGIC_LINE")
    add_common_project_arg(p)
    p.add_argument("--pou", required=True)
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), default="program")
    p.add_argument("--from-block", required=True)
    p.add_argument("--from-pin", required=True)
    p.add_argument("--to-block", required=True)
    p.add_argument("--to-pin", required=True)
    p.add_argument("--line-name", help="explicit CONTROL_LOGIC_LINE NAME; default is the next free _LINEn")
    p.add_argument("--line-position", help="explicit LINE_POSITION polyline, 3 points as x1,y1,x2,y2,x3,y3")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_connect_pins)

    p = sub.add_parser("disconnect-line", help="remove a CONTROL_LOGIC_LINE and every pin connection referencing it")
    add_common_project_arg(p)
    p.add_argument("--pou", required=True)
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), default="program")
    p.add_argument("--line-name", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_disconnect_line)

    p = sub.add_parser("copy-block", help="copy a CONTROL_LOGIC_BLOCK from a reference project into a graphical POU")
    add_common_project_arg(p)
    p.add_argument("--reference", required=True, type=Path)
    p.add_argument("--reference-pou", required=True)
    p.add_argument("--reference-pou-type", choices=sorted(POU_TAGS))
    p.add_argument("--block", required=True, help="CONTROL_LOGIC_BLOCK NAME in the reference project")
    p.add_argument("--pou", required=True, help="target POU that already owns an LD/FBD section")
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), default="program")
    p.add_argument("--target-name", help="block NAME in the target; default is the next free _MODULEn")
    p.add_argument("--rect-position", help="RECT_POSITION for the copied block")
    p.add_argument("--keep-connections", action="store_true", help="keep CONTROL_BLOCK_CONNECTION children instead of stripping them")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_copy_block)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
