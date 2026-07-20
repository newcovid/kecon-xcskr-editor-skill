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


@dataclass(frozen=True)
class PouSpan:
    tag: str
    name: str
    start: int
    end: int
    raw: str


def read_text(path: Path, encoding: str = DEFAULT_ENCODING) -> str:
    return path.read_text(encoding=encoding)


def write_text(path: Path, text: str, encoding: str = DEFAULT_ENCODING) -> None:
    path.write_text(text, encoding=encoding)


def make_backup(path: Path) -> Path:
    backup = path.with_name(path.name + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(path, backup)
    return backup


def parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def xml_attr_encode(value: str, newline_style: str = "literal") -> str:
    value = normalize_newlines(value)
    value = (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    if newline_style == "numeric":
        return value.replace("\n", "&#10;")
    return value


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


def replace_section_logic_raw(pou_raw: str, st_text: str) -> str:
    start, end, old_raw_content = find_section_logic_raw(pou_raw)
    newline_style = "numeric" if "&#10;" in old_raw_content or "&#xA;" in old_raw_content or "&#xa;" in old_raw_content else "literal"
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
    return path.read_text(encoding=encoding)


def maybe_write_output(content: str, output: Path | None, encoding: str) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding=encoding)
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


def pin_connection(pin: ET.Element) -> dict[str, str]:
    conn = pin.find("./CONTROL_BLOCK_CONNECTION")
    return {
        "type": "" if conn is None else attr(conn, "CONNECTION_TYPE"),
        "value": "" if conn is None else attr(conn, "CONNECTION_VALUE"),
    }


def ld_pin_row(pin: ET.Element) -> dict[str, object]:
    return {
        "name": attr(pin, "NAME"),
        "datatype": attr(pin, "DATATYPE"),
        "desc": attr(pin, "DESC"),
        "enabled": attr(pin, "ENABLED"),
        "visible": attr(pin, "VISIBLE"),
        "negated": attr(pin, "NEGATED"),
        "init_value": attr(pin, "INIT_VALUE"),
        "connection": pin_connection(pin),
    }


def collect_ld_program(root: ET.Element, program_name: str | None = None) -> dict[str, object]:
    programs: list[dict[str, object]] = []
    for task in root.findall(".//CONTROL_SCHEME/*"):
        if task.tag not in {"MAIN_TASK", "EVENT_TASK", "CYCLE_TASK"}:
            continue
        for program in task.findall("./PROGRAM"):
            if program_name and attr(program, "NAME") != program_name:
                continue
            ld = program.find("./SECTION_LOGIC_LD")
            if ld is None:
                continue
            blocks: list[dict[str, object]] = []
            for block in ld.findall("./CONTROL_LOGIC_BLOCK"):
                blocks.append(
                    {
                        "name": attr(block, "NAME"),
                        "type": attr(block, "TYPE"),
                        "deactive": attr(block, "DEACTIVE"),
                        "desc": attr(block, "DESC"),
                        "position_type": attr(block, "POSITION_TYPE"),
                        "rect_position": attr(block, "RECT_POSITION"),
                        "showen": attr(block, "SHOWEN"),
                        "inputs": [ld_pin_row(pin) for pin in block.findall("./BLOCK_PIN_INPUT")],
                        "outputs": [ld_pin_row(pin) for pin in block.findall("./BLOCK_PIN_OUTPUT")],
                    }
                )
            lines = [
                {
                    "name": attr(line, "NAME"),
                    "deactive": attr(line, "DEACTIVE"),
                    "from_powerrail": attr(line, "FROM_POWERRAIL"),
                    "position_type": attr(line, "POSITION_TYPE"),
                    "type": attr(line, "TYPE"),
                    "line_position": attr(line, "LINE_POSITION"),
                }
                for line in ld.findall("./CONTROL_LOGIC_LINE")
            ]
            programs.append(
                {
                    "name": attr(program, "NAME"),
                    "desc": attr(program, "DESC"),
                    "id": attr(program, "ID"),
                    "logic_lang": attr(program, "LOGIC_LANG"),
                    "task_tag": task.tag,
                    "task_id": attr(task, "ID"),
                    "block_count": len(blocks),
                    "line_count": len(lines),
                    "active_block_count": sum(1 for block in blocks if block["deactive"] in ("", "NO")),
                    "inactive_block_count": sum(1 for block in blocks if block["deactive"] == "YES"),
                    "blocks": blocks,
                    "lines": lines,
                }
            )
    if program_name and not programs:
        raise ValueError(f"LD PROGRAM NAME={program_name!r} not found")
    return {"programs": programs}


def ld_block_summary_rows(ld_package: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for program in ld_package["programs"]:  # type: ignore[index]
        for block in program["blocks"]:  # type: ignore[index]
            inputs = block["inputs"]  # type: ignore[index]
            outputs = block["outputs"]  # type: ignore[index]
            connected_inputs = sum(1 for pin in inputs if pin["connection"]["value"])  # type: ignore[index]
            connected_outputs = sum(1 for pin in outputs if pin["connection"]["value"])  # type: ignore[index]
            rows.append(
                {
                    "program": program["name"],  # type: ignore[index]
                    "block": block["name"],  # type: ignore[index]
                    "type": block["type"],  # type: ignore[index]
                    "deactive": block["deactive"],  # type: ignore[index]
                    "inputs": len(inputs),
                    "outputs": len(outputs),
                    "connected_inputs": connected_inputs,
                    "connected_outputs": connected_outputs,
                    "rect": block["rect_position"],  # type: ignore[index]
                }
            )
    return rows


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
    new_pou = replace_section_logic_raw(span.raw, st)
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
        target.write_text(st, encoding="utf-8")
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
    task_map = {
        "MAIN_TASK": "main",
        "EVENT_TASK": "event",
        "CYCLE_TASK": "cycle",
    }
    tasks: list[dict[str, object]] = []
    programs: list[dict[str, object]] = []
    for scheme_index, scheme in enumerate(root.findall(".//CONTROL_SCHEME")):
        for task in list(scheme):
            if task.tag not in task_map:
                continue
            task_kind = task_map[task.tag]
            task_record: dict[str, object] = {
                "kind": task_kind,
                "tag": task.tag,
                "id": attr(task, "ID"),
                "name": attr(task, "NAME"),
                "cycle_time": attr(task, "CYCLE_TIME"),
                "attrs": attrs_subset(task, ["ID", "NAME", "DESC", "CYCLE_TIME", "INTERVAL", "PRIORITY", "EVENT_TYPE", "ENABLE"]),
                "trigger_condition": {},
                "programs": [],
            }
            trigger = task.find("./TRIG_CONDITION")
            if trigger is not None:
                task_record["trigger_condition"] = dict(trigger.attrib)
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
    hardware = collect_hardware_package(root)

    index = {
        "format": "kecon-xcskr-ai-pack/v1",
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
        },
        "counts": {
            "tasks": len(control["tasks"]),
            "programs": len(control["programs"]),
            "function_blocks": len(function_blocks),
            "functions": len(functions),
            "variables": len(variables),
            "user_structs": len(user_structs),
            "downlink_ports": len(hardware["downlink_ports"]),
            "stations": len(hardware["stations"]),
            "hardware_tags": len(hardware["hardware_tags"]),
            "slave_objects": len(hardware["slave_objects"]),
            "slave_mappings": len(hardware["slave_mappings"]),
        },
        "control_scheme": {"tasks": control["tasks"]},
    }

    write_json(output_dir / "index.json", index)
    write_json(output_dir / "programs.json", {"programs": control["programs"]})
    write_json(output_dir / "function-blocks.json", {"function_blocks": function_blocks})
    write_json(output_dir / "functions.json", {"functions": functions})
    write_json(output_dir / "variables.json", {"variables": variables})
    write_json(output_dir / "user-data-types.json", {"user_structs": user_structs})
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

    p = sub.add_parser("export-ld", help="export LD/FBD graphical program blocks, pins, connections, and lines")
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
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_replace_st)

    p = sub.add_parser("set-attrs", help="set attributes on selected structured project entities without hand-editing XML")
    add_common_project_arg(p)
    p.add_argument("--kind", required=True, choices=["variable", "hardware-tag", "user-struct", "user-struct-member", "pou", "pou-var", "downlink-port", "station", "slave-object", "slave-mapping"])
    p.add_argument("--name", help="entity name, or POU name for kind=pou/pou-var")
    p.add_argument("--pou-type", choices=sorted(POU_TAGS), help="required for kind=pou or kind=pou-var")
    p.add_argument("--var-section", choices=["input", "output", "internal"], help="required for kind=pou-var")
    p.add_argument("--var", help="POU variable name for kind=pou-var")
    p.add_argument("--struct", help="user structure name for kind=user-struct or kind=user-struct-member")
    p.add_argument("--member", help="user structure member name for kind=user-struct-member")
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

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
