from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "xcskr_workspace.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import xcskr_workspace as ws  # noqa: E402

from test_xcskr_tool import FIXTURE_XML  # noqa: E402


# The child writes Chinese to stderr.  On Windows a piped stderr defaults to the
# ANSI code page (cp936 here), so decoding it as UTF-8 in the parent turns every
# message into U+FFFD -- and every `assertIn("<中文>", result.stderr)` then fails
# no matter what the script actually said.  Pin the child to UTF-8 so the
# refusal messages that guard the manifest gate are really being checked.
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run_ws(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=CHILD_ENV,
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WorkspaceRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.project = self.folder / "demo.xcskr"
        self.project.write_text(FIXTURE_XML, encoding="gbk", newline="")
        self.workspace = self.folder / "ws"
        self.addCleanup(self.tmp.cleanup)

    def export(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_ws(
            "export-workspace",
            "--project", str(self.project),
            "--workspace", str(self.workspace),
            *extra,
            check=False,
        )

    def do_import(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_ws(
            "import-workspace",
            "--project", str(self.project),
            "--workspace", str(self.workspace),
            *extra,
            check=False,
        )

    def program_file(self, relative: str) -> Path:
        return self.workspace / relative

    # -- export ------------------------------------------------------------

    def test_export_lays_out_programs_by_task_and_execution_order(self) -> None:
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = {
            "程序/主任务/01_MainProgram.st",
            "程序/事件任务/01_EventProgram.st",
            "程序/周期任务20ms/01_CycleProgram.st",
            "程序/周期任务20ms/02_LadderProgram.graph.json",
            "程序/周期任务20ms/03_ChassisProgram.graph.json",
            "功能块/FB_SCALE.st",
        }
        manifest = json.loads((self.workspace / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({item["file"] for item in manifest["items"]}, expected)
        for name in expected:
            self.assertTrue((self.workspace / name).exists(), name)

    def test_export_writes_readonly_views_and_symbol_table(self) -> None:
        self.export()
        for name in ("变量.md", "结构体.md", "任务.md", "硬件标签.tsv", "声明.st", "符号表.json"):
            self.assertTrue((self.workspace / "只读" / name).exists(), name)
        symbols = json.loads((self.workspace / "只读" / "符号表.json").read_text(encoding="utf-8"))["symbols"]
        # An array variable is keyed with a normalized `[]`, because the file
        # writes the elements expanded and only the parent carries a DESC.
        self.assertIn("StatusWords[]", symbols)
        self.assertNotIn("StatusWords[0]", symbols)
        self.assertEqual(symbols["StatusWords[]"]["desc"], "status words")

    def test_st_export_matches_extract_st(self) -> None:
        self.export()
        content = self.program_file("程序/主任务/01_MainProgram.st").read_text(encoding="utf-8", newline="")
        self.assertEqual(content, "FB_SCALE(InValue:=1, Scale=>StatusWords[0]);")

    # -- import ------------------------------------------------------------

    def test_import_without_changes_is_a_no_op(self) -> None:
        self.export()
        before = sha(self.project)
        result = self.do_import()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NoChanges=1", result.stdout)
        self.assertEqual(sha(self.project), before)

    def test_edit_and_revert_restores_the_project_byte_for_byte(self) -> None:
        """The round trip must not drift.

        A cosmetic rewrite (a space before `/>`, a different newline encoding)
        would make every import show up in the diff and would break the habit of
        trusting `git diff` on the project file.
        """
        self.export()
        original = self.project.read_bytes()
        # MainProgram is deliberately not used here: its fixture ST holds a bare
        # `>`, which no real project contains -- see the normalization test below.
        target = self.program_file("程序/周期任务20ms/01_CycleProgram.st")
        source = target.read_text(encoding="utf-8", newline="")

        target.write_text(source + "\nSystemReady := TRUE;", encoding="utf-8", newline="")
        self.assertEqual(self.do_import("--no-backup").returncode, 0)
        self.assertNotEqual(self.project.read_bytes(), original)

        target.write_text(source, encoding="utf-8", newline="")
        self.assertEqual(self.do_import("--no-backup").returncode, 0)
        self.assertEqual(self.project.read_bytes(), original)

    def test_import_applies_st_change(self) -> None:
        self.export()
        target = self.program_file("程序/周期任务20ms/01_CycleProgram.st")
        target.write_text("StatusWords[1] := 42;", encoding="utf-8", newline="")
        result = self.do_import("--no-backup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("StatusWords[1] := 42;", self.project.read_text(encoding="gbk", newline=""))

    def test_dry_run_reports_without_writing(self) -> None:
        self.export()
        before = sha(self.project)
        target = self.program_file("程序/周期任务20ms/01_CycleProgram.st")
        target.write_text("StatusWords[1] := 7;", encoding="utf-8", newline="")
        result = self.do_import("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY_RUN=OK", result.stdout)
        self.assertEqual(sha(self.project), before)

    def test_bare_gt_in_source_is_normalized_to_an_entity(self) -> None:
        """`>` inside an attribute value is legal, but no real project writes it.

        Counted across this project, its IVC200 sibling and the official
        GUI-authored sample: 845 occurrences of `&gt;` inside SECTION_LOGIC_ST
        CONTENT and zero bare `>`.  A rewrite therefore normalizes an
        unrealistic fixture rather than touching anything a project contains,
        and the ST reads back identically.
        """
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        source = target.read_text(encoding="utf-8", newline="")
        self.assertIn("=>", source)

        target.write_text(source + "\n", encoding="utf-8", newline="")
        self.assertEqual(self.do_import("--no-backup").returncode, 0)
        raw = self.project.read_text(encoding="gbk", newline="")
        self.assertIn("Scale=&gt;StatusWords[0]", raw)
        self.assertNotIn("Scale=>StatusWords[0]", raw)

        self.export("--force")
        again = self.program_file("程序/主任务/01_MainProgram.st").read_text(encoding="utf-8", newline="")
        self.assertEqual(again, source + "\n")

    # -- graphical logic ---------------------------------------------------

    def load_graph(self, relative: str) -> dict:
        return json.loads(self.program_file(relative).read_text(encoding="utf-8"))

    def save_graph(self, relative: str, data: dict) -> None:
        self.program_file(relative).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
        )

    def test_graph_export_carries_blocks_pins_and_wires(self) -> None:
        self.export()
        graph = self.load_graph("程序/周期任务20ms/02_LadderProgram.graph.json")
        self.assertEqual(graph["language"], "ld")
        self.assertEqual([block["name"] for block in graph["blocks"]], ["_MODULE0", "_MODULE1"])
        self.assertEqual([line["name"] for line in graph["lines"]], ["_LINE0"])
        pins = {(pin["dir"], pin["name"]): pin for pin in graph["blocks"][0]["pins"]}
        self.assertEqual(pins[("in", "IN")]["bind"], {"var": "StatusWords[0]"})
        self.assertEqual(pins[("out", "Q_H")]["bind"], {"line": "_LINE0"})
        self.assertIsNone(pins[("out", "Q_L")]["bind"])

    def test_graph_import_binds_a_variable_to_an_unbound_pin(self) -> None:
        self.export()
        relative = "程序/周期任务20ms/03_ChassisProgram.graph.json"
        graph = self.load_graph(relative)
        for pin in graph["blocks"][0]["pins"]:
            if pin["name"] == "V_lin":
                pin["bind"] = {"var": "StatusWords[0]"}
        self.save_graph(relative, graph)
        result = self.do_import("--no-backup")
        self.assertEqual(result.returncode, 0, result.stderr)

        self.export("--force")
        graph = self.load_graph(relative)
        pins = {pin["name"]: pin for pin in graph["blocks"][0]["pins"]}
        self.assertEqual(pins["V_lin"]["bind"], {"var": "StatusWords[0]"})

    def test_graph_import_unbinds_back_to_a_self_closing_pin(self) -> None:
        self.export()
        relative = "程序/周期任务20ms/02_LadderProgram.graph.json"
        graph = self.load_graph(relative)
        for pin in graph["blocks"][0]["pins"]:
            if pin["name"] == "IN":
                pin["bind"] = None
        self.save_graph(relative, graph)
        self.assertEqual(self.do_import("--no-backup").returncode, 0)

        self.export("--force")
        graph = self.load_graph(relative)
        pins = {pin["name"]: pin for pin in graph["blocks"][0]["pins"]}
        self.assertIsNone(pins["IN"]["bind"])

    def test_graph_import_sets_init_negated_and_deactive(self) -> None:
        self.export()
        relative = "程序/周期任务20ms/03_ChassisProgram.graph.json"
        graph = self.load_graph(relative)
        graph["blocks"][0]["deactive"] = True
        for pin in graph["blocks"][0]["pins"]:
            if pin["name"] == "V_lin":
                pin["init"] = "1.250"
                pin["negated"] = True
        self.save_graph(relative, graph)
        self.assertEqual(self.do_import("--no-backup").returncode, 0)

        self.export("--force")
        graph = self.load_graph(relative)
        self.assertTrue(graph["blocks"][0]["deactive"])
        pins = {pin["name"]: pin for pin in graph["blocks"][0]["pins"]}
        self.assertEqual(pins["V_lin"]["init"], "1.250")
        self.assertTrue(pins["V_lin"]["negated"])

    def test_graph_import_adds_and_removes_a_wire(self) -> None:
        self.export()
        relative = "程序/周期任务20ms/02_LadderProgram.graph.json"
        graph = self.load_graph(relative)
        graph["lines"].append(
            {"name": "_LINE9", "position": "10,10,20,10", "from_powerrail": False, "deactive": False}
        )
        self.save_graph(relative, graph)
        self.assertEqual(self.do_import("--no-backup").returncode, 0)
        self.export("--force")
        self.assertIn("_LINE9", [line["name"] for line in self.load_graph(relative)["lines"]])

        graph = self.load_graph(relative)
        graph["lines"] = [line for line in graph["lines"] if line["name"] != "_LINE9"]
        self.save_graph(relative, graph)
        self.assertEqual(self.do_import("--no-backup").returncode, 0)
        self.export("--force")
        self.assertNotIn("_LINE9", [line["name"] for line in self.load_graph(relative)["lines"]])

    # -- refusals and gates ------------------------------------------------

    def test_import_refuses_a_synthesized_block(self) -> None:
        """A block TYPE implies a fixed pin list the file does not describe."""
        self.export()
        relative = "程序/周期任务20ms/02_LadderProgram.graph.json"
        graph = self.load_graph(relative)
        graph["blocks"].append(
            {"name": "_MODULE9", "type": "OR", "desc": "", "rect": "0,0,10,10", "deactive": False, "pins": []}
        )
        self.save_graph(relative, graph)
        before = sha(self.project)
        result = self.do_import()
        self.assertEqual(result.returncode, 4)
        self.assertIn("copy-block", result.stderr)
        self.assertEqual(sha(self.project), before)

    def test_import_refuses_a_changed_graph_desc(self) -> None:
        # `desc` on a graph.json is the POU's description, not part of the
        # diagram, and it does not round-trip.  Silently ignoring an edit is the
        # worst outcome: import says OK, the manifest takes the new hash, and
        # the text vanishes at the next export without ever reaching the file.
        self.export()
        graph = self.load_graph("程序/周期任务20ms/02_LadderProgram.graph.json")
        graph["desc"] = "试车时改一下看看"
        self.save_graph("程序/周期任务20ms/02_LadderProgram.graph.json", graph)

        result = self.do_import()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("只读字段 desc", result.stderr)
        self.assertIn("set-attrs --kind pou", result.stderr)

    def test_import_refuses_readonly_graph_fields(self) -> None:
        self.export()
        relative = "程序/周期任务20ms/02_LadderProgram.graph.json"
        graph = self.load_graph(relative)
        graph["blocks"][0]["type"] = "SomethingElse"
        graph["blocks"][0]["pins"].append(
            {"dir": "in", "name": "NEW", "datatype": "BOOL", "desc": "", "bind": None, "init": "", "negated": False, "enabled": True}
        )
        self.save_graph(relative, graph)
        result = self.do_import()
        self.assertEqual(result.returncode, 4)
        self.assertIn("TYPE", result.stderr)
        self.assertIn("不能增删", result.stderr)

    def test_import_refuses_when_the_project_moved_on(self) -> None:
        """The GUI keeps its own copy in memory and overwrites on save."""
        self.export()
        self.project.write_text(
            self.project.read_text(encoding="gbk", newline="") + "\n", encoding="gbk", newline=""
        )
        target = self.program_file("程序/主任务/01_MainProgram.st")
        target.write_text("SystemReady := FALSE;", encoding="utf-8", newline="")
        result = self.do_import()
        self.assertEqual(result.returncode, 3)
        self.assertIn("拒绝回灌", result.stderr)

    def test_export_refuses_to_discard_unimported_edits(self) -> None:
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        target.write_text("SystemReady := FALSE;", encoding="utf-8", newline="")
        result = self.export()
        self.assertEqual(result.returncode, 2)
        self.assertIn("尚未回灌", result.stderr)
        self.assertEqual(target.read_text(encoding="utf-8", newline=""), "SystemReady := FALSE;")
        self.assertEqual(self.export("--force").returncode, 0)

    def test_force_export_parks_the_edits_it_is_about_to_overwrite(self) -> None:
        # --force means "overwrite them", not "they were worthless".  A whole
        # session of editing can be sitting in these files and the export is the
        # last moment they exist.  Park a copy so it can be diffed back in.
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        target.write_text("MyHardWonEdit := 1;", encoding="utf-8", newline="")

        result = self.export("--force")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Discarded=1", result.stdout)
        parked = self.workspace / ".discarded" / "001" / "程序" / "主任务" / "01_MainProgram.st"
        self.assertTrue(parked.exists(), "被覆盖的文件应当留一份")
        self.assertEqual(parked.read_text(encoding="utf-8"), "MyHardWonEdit := 1;")
        self.assertNotIn("MyHardWonEdit", target.read_text(encoding="utf-8"))

    def test_force_export_numbers_each_rescue_separately(self) -> None:
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        target.write_text("First := 1;", encoding="utf-8", newline="")
        self.export("--force")
        target.write_text("Second := 2;", encoding="utf-8", newline="")
        self.export("--force")

        first = self.workspace / ".discarded" / "001" / "程序" / "主任务" / "01_MainProgram.st"
        second = self.workspace / ".discarded" / "002" / "程序" / "主任务" / "01_MainProgram.st"
        self.assertEqual(first.read_text(encoding="utf-8"), "First := 1;")
        self.assertEqual(second.read_text(encoding="utf-8"), "Second := 2;")

    def test_export_prunes_the_file_a_reordered_program_left_behind(self) -> None:
        # A program's `NN_` prefix comes from its position in the task, so moving
        # one renames its file.  The old name must not survive: import only walks
        # the manifest, so edits to the stale copy would vanish without a word.
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        self.assertTrue(target.exists())
        orphan = target.with_name("09_Orphan.st")
        orphan.write_text("Whatever := 1;", encoding="utf-8", newline="")
        manifest = json.loads((self.workspace / "manifest.json").read_text(encoding="utf-8"))
        manifest["items"].append({"file": "程序/主任务/09_Orphan.st",
                                  "sha256": sha(orphan), "kind": "st"})
        (self.workspace / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + chr(10),
            encoding="utf-8", newline="")

        run_ws("export-workspace", "--project", str(self.project),
               "--workspace", str(self.workspace))

        self.assertFalse(orphan.exists(), "改名前的文件应当被清掉")
        self.assertTrue(target.exists(), "还在的程序不该被误删")

    def test_export_leaves_files_it_never_wrote_alone(self) -> None:
        # Pruning is scoped to what a previous export produced; a note somebody
        # dropped into the workspace is not ours to delete.
        self.export()
        note = self.workspace / "程序" / "主任务" / "现场笔记.md"
        note.write_text("试车记录", encoding="utf-8", newline="")

        run_ws("export-workspace", "--project", str(self.project),
               "--workspace", str(self.workspace))

        self.assertTrue(note.exists(), "工具没写过的文件不该被删")

    def test_import_refuses_a_renamed_workspace_file(self) -> None:
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        target.rename(target.with_name("renamed.st"))
        result = self.do_import()
        self.assertEqual(result.returncode, 2)
        self.assertIn("缺少这些文件", result.stderr)

    def test_status_reports_drift_and_changed_files(self) -> None:
        self.export()
        target = self.program_file("程序/主任务/01_MainProgram.st")
        target.write_text("SystemReady := FALSE;", encoding="utf-8", newline="")
        result = run_ws(
            "status-workspace", "--project", str(self.project), "--workspace", str(self.workspace)
        )
        self.assertIn("ProjectChangedSinceExport=NO", result.stdout)
        self.assertIn("ChangedFiles=1", result.stdout)
        self.assertIn("01_MainProgram.st", result.stdout)


class SymbolTableTests(unittest.TestCase):
    """The symbol table is what a hover tip reads, so its edge cases matter."""

    def test_array_members_inherit_the_parent_description(self) -> None:
        structs = [
            {
                "name": "Config_Data",
                "desc": "",
                "members": [
                    {"name": "WhlX_m", "datatype": "REAL[8]", "desc": "纵向坐标，单位 m", "init_value": "", "visible": "YES"},
                    # The expanded children the GUI writes carry no DESC of their own.
                    {"name": "WhlX_m[0]", "datatype": "REAL", "desc": "", "init_value": "", "visible": "YES"},
                    {"name": "WhlX_m[1]", "datatype": "REAL", "desc": "", "init_value": "", "visible": "YES"},
                ],
            }
        ]
        variables = [{"name": "CFG", "datatype": "Config_Data", "desc": "整车配置"}]
        symbols = ws.build_symbols(variables, structs)
        self.assertIn("CFG.WhlX_m[]", symbols)
        self.assertEqual(symbols["CFG.WhlX_m[]"]["desc"], "纵向坐标，单位 m")
        self.assertEqual(symbols["CFG.WhlX_m[]"]["unit"], "m")
        # The expanded children must not become symbols of their own, or a hover
        # over CFG.WhlX_m[3] would find a description-less entry.
        self.assertNotIn("CFG.WhlX_m[0]", symbols)

    def test_array_of_structs_expands_through_the_element_type(self) -> None:
        structs = [
            {
                "name": "Motor_Data",
                "desc": "",
                "members": [
                    {"name": "PosDelta_cnt", "datatype": "DINT", "desc": "本周期位置增量", "init_value": "0", "visible": "YES"}
                ],
            }
        ]
        variables = [{"name": "MOT", "datatype": "Motor_Data[16]", "desc": "16 台驱动器"}]
        symbols = ws.build_symbols(variables, structs)
        self.assertIn("MOT[]", symbols)
        self.assertIn("MOT[].PosDelta_cnt", symbols)
        self.assertEqual(symbols["MOT[].PosDelta_cnt"]["unit"], "计数")

    def test_unit_comes_from_the_description_before_the_name_suffix(self) -> None:
        self.assertEqual(ws.unit_of("Speed_mps", "线速度，单位：m/s"), "m/s")
        self.assertEqual(ws.unit_of("Angle_cdeg", ""), "0.01 度")
        # Longest suffix wins, or `_mps` would be read as `_m`.
        self.assertEqual(ws.unit_of("V_mps", ""), "m/s")
        self.assertEqual(ws.unit_of("Whatever", ""), "")

    def test_project_unit_suffixes_resolve_to_the_units_the_names_promise(self) -> None:
        # `_01rpm` is a tenth of an rpm, not a hundredth: the table used to say
        # "0.01 rpm", so every 0x60FF speed in the exported tables read 10x off.
        self.assertEqual(ws.unit_of("Spd_set_01rpm", ""), "0.1 rpm")
        # `_radps` / `_radps2` are what the project actually writes; the table
        # only had `_rads`, so these two fell through to no unit at all.
        self.assertEqual(ws.unit_of("VmaxAng_radps", ""), "rad/s")
        self.assertEqual(ws.unit_of("AngAccel_radps2", ""), "rad/s^2")
        # Matching is case-folded, so `_mA` has to be listed as `_ma`, and it
        # has to come before `_a` or milliamps would be reported as amps.
        self.assertEqual(ws.unit_of("Cur_mA", ""), "mA")


class SelfClosingStyleTests(unittest.TestCase):
    """Preserving `"/>` versus `" />` is what keeps an unchanged import silent."""

    def test_spacer_is_detected_for_both_styles(self) -> None:
        import xcskr_tool as xt

        self.assertEqual(xt.section_logic_self_closing_spacer('<SECTION_LOGIC_ST CONTENT="x"/>'), "")
        self.assertEqual(xt.section_logic_self_closing_spacer('<SECTION_LOGIC_ST CONTENT="x" />'), " ")

    def test_replace_keeps_the_style_the_element_already_used(self) -> None:
        import xcskr_tool as xt

        tight = '<PROGRAM NAME="P"><SECTION_LOGIC_ST CONTENT="a;"/></PROGRAM>'
        loose = '<PROGRAM NAME="P"><SECTION_LOGIC_ST CONTENT="a;" /></PROGRAM>'
        self.assertIn('"b;"/>', xt.replace_section_logic_raw(tight, "b;"))
        self.assertIn('"b;" />', xt.replace_section_logic_raw(loose, "b;"))


if __name__ == "__main__":
    unittest.main()
