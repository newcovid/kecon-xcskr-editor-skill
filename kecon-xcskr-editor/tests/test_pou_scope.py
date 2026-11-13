"""Regression checks for compiler-visible POU scopes, using synthetic projects."""
from __future__ import annotations

import html
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_xcskr_tool import FIXTURE_XML

SKILL = Path(__file__).resolve().parents[1]
TOOL = SKILL / "scripts/xcskr_tool.py"
WORKSPACE = SKILL / "scripts/xcskr_workspace.py"


class PouScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.project = self.folder / "scope.xcskr"

    def make(self, *, fb="Scale := InValue + Offset;", local="", globals_=""):
        source = FIXTURE_XML.replace(
            'CONTENT="Scale := InValue;"', 'CONTENT="'+html.escape(fb, quote=True)+'"', 1)
        source = source.replace('<SECTION_LOGIC_ST CONTENT="FB_SCALE', local+'<SECTION_LOGIC_ST CONTENT="FB_SCALE', 1)
        source = source.replace('</GLOBAL_TAG_CONFIG>', globals_+'</GLOBAL_TAG_CONFIG>', 1)
        self.project.write_bytes(source.encode("gbk"))
        return source.encode("gbk")

    def call(self, script, *args):
        return subprocess.run([sys.executable, str(script), *map(str,args)],
            capture_output=True, encoding="utf-8", errors="replace")

    def validate(self):
        output = self.folder / "scope.json"
        result = self.call(TOOL, "validate-pou-scope", "--project", self.project,
                           "--format", "json", "--output", output)
        self.assertTrue(output.exists(), result.stdout+result.stderr)
        return result, json.loads(output.read_text("utf-8"))

    def test_program_local_addition_is_rejected_before_write_or_backup(self):
        before = self.make()
        for section in ("internal", "input", "output"):
            with self.subTest(section=section):
                result = self.call(TOOL, "add-pou-var", "--project", self.project,
                    "--pou-type", "program", "--name", "MainProgram",
                    "--var-section", section, "--var", "Elapsed_ms:UDINT:elapsed time")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("PROGRAM-local variables", result.stdout+result.stderr)
                self.assertEqual(self.project.read_bytes(), before)
                self.assertEqual(list(self.folder.glob("*.bak*")), [])

    def test_function_block_local_addition_remains_supported(self):
        self.make()
        result = self.call(TOOL, "add-pou-var", "--project", self.project,
            "--name", "FB_SCALE", "--var-section", "internal", "--var", "Memory:REAL:state")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        result, rows = self.validate()
        self.assertEqual((result.returncode, rows), (0, []))

    def test_existing_program_declarations_are_reported_even_when_unused(self):
        local = ''.join(f'<SECTION_VAR_{section} NAME="Tmp_{section}" DATATYPE="REAL" />'
                        for section in ("INPUT", "OUTPUT", "INTERNAL"))
        self.make(local=local)
        result, rows = self.validate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual({r["variable"] for r in rows}, {"Tmp_INPUT","Tmp_OUTPUT","Tmp_INTERNAL"})
        self.assertTrue(all(r["pou"] == "MainProgram" and r["status"] == "PROGRAM_LOCAL_NOT_SUPPORTED" for r in rows))

    def test_function_block_global_read_and_write_are_reported(self):
        self.make(fb="(* header *)\nScale := InValue;\nScale := StatusWords[0];\nSystemReady := ON;")
        result, rows = self.validate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual({(r["variable"],r["line"]) for r in rows}, {("StatusWords",3),("SystemReady",4)})

    def test_declared_block_pin_shadows_same_named_project_global(self):
        self.make(globals_='<VARIABLE NAME="InValue" DATATYPE="INT" />')
        result, rows = self.validate()
        self.assertEqual((result.returncode, rows), (0, []))

    def test_struct_member_names_do_not_count_as_global_roots(self):
        self.make(fb="Scale := LocalData.SystemReady; Scale := LocalData.StatusWords[0];")
        result, rows = self.validate()
        self.assertEqual((result.returncode, rows), (0, []))

    def test_comments_strings_and_named_call_pins_do_not_count_as_global_reads(self):
        self.make(fb="(* SystemReady *)\n// StatusWords[0]\nText := '(* SystemReady';\nText := 'StatusWords';\nText := \"SystemReady\";\nOther(SystemReady=ON, StatusWords:=1);")
        result, rows = self.validate()
        self.assertEqual((result.returncode, rows), (0, []))

    def test_global_argument_values_and_parenthesized_comparisons_are_reads(self):
        self.make(fb="Other(X=SystemReady);\nIF (StatusWords[0] = 1) THEN Scale := 1; END_IF;")
        result, rows = self.validate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual({r["variable"] for r in rows}, {"SystemReady","StatusWords"})

    def test_hardware_tag_access_in_block_is_also_reported(self):
        self.make(fb="Scale := Axis1_Position_6004[0];")
        result, rows = self.validate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual([r["variable"] for r in rows], ["Axis1_Position_6004"])

    def test_program_registered_global_access_remains_supported(self):
        self.make()
        result, rows = self.validate()
        self.assertEqual((result.returncode, rows), (0, []))

    def test_identifier_matching_is_case_insensitive_and_whole_word(self):
        self.make(fb="Scale := STATUSWORDS[0]; Scale := MyStatusWords;")
        result, rows = self.validate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual([r["variable"] for r in rows], ["StatusWords"])

    def test_workspace_check_runs_scope_validator(self):
        self.make(local='<SECTION_VAR_INTERNAL NAME="Elapsed_ms" DATATYPE="UDINT" />')
        workspace = self.folder / "workspace"
        export = self.call(WORKSPACE, "export-workspace", "--project", self.project, "--workspace", workspace)
        self.assertEqual(export.returncode, 0, export.stdout+export.stderr)
        result = self.call(WORKSPACE, "check-workspace", "--project", self.project, "--workspace", workspace)
        self.assertEqual(result.returncode, 1)
        self.assertIn("validate-pou-scope", result.stdout)
        self.assertIn("POU_SCOPE=FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
