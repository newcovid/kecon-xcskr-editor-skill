from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "xcskr_tool.py"
FIXTURE_XML = """<?xml version="1.0" encoding="GBK"?>
<PROJECT NAME="DemoProject" OTHER_NAME="IVC200" VERSION="107">
  <FUNCTION_BLOCK_LIST>
    <FUNCTION_BLOCK NAME="FB_SCALE" DESC="generic function block" LOGIC_LANG="2">
      <SECTION_LOGIC_ST CONTENT="Scale := InValue;" />
      <SECTION_VAR_INPUT NAME="InValue" DATATYPE="INT" DESC="input value" INIT_VALUE="" VISIBLE="YES" />
      <SECTION_VAR_OUTPUT NAME="Scale" DATATYPE="INT" DESC="scaled output" INIT_VALUE="" VISIBLE="YES" />
      <SECTION_VAR_INTERNAL NAME="Offset" DATATYPE="INT" DESC="internal offset" INIT_VALUE="0" VISIBLE="YES" />
    </FUNCTION_BLOCK>
  </FUNCTION_BLOCK_LIST>
  <GLOBAL_TAG_CONFIG>
    <VARIABLE NAME="SystemReady" DATATYPE="BOOL" DESC="system ready flag" INIT_VALUE="OFF" READONLY="NO" VISIBLE="YES" />
    <VARIABLE NAME="StatusWords" DATATYPE="UINT[2]" DESC="status words" INIT_VALUE="" READONLY="NO" VISIBLE="YES">
      <VARIABLE_MEMBER NAME="StatusWords[0]" DATATYPE="UINT" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
      <VARIABLE_MEMBER NAME="StatusWords[1]" DATATYPE="UINT" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
    </VARIABLE>
  </GLOBAL_TAG_CONFIG>
  <HARDWARE>
    <HARDWARE_NET ID="0">
      <HARDWARE_DEVICE_UPLINK_PORT NAME="Ethernet" DISPLAY="Ethernet" PHYSICAL_ID="16">
        <HARDWARE_ROBOT_CONTROLLER NAME="Controller">
          <CONTROL_SCHEME>
            <MAIN_TASK ID="1" CYCLE_TIME="10">
              <PROGRAM NAME="MainProgram" DESC="main task program" ID="0" LOGIC_LANG="2">
                <SECTION_LOGIC_ST CONTENT="FB_SCALE(InValue:=1, Scale=>StatusWords[0]);" />
              </PROGRAM>
            </MAIN_TASK>
            <EVENT_TASK ID="2" EVENT_TYPE="rising">
              <TRIG_CONDITION TAG_NAME="DI0" CONDITION="RISING" />
              <PROGRAM NAME="EventProgram" DESC="event task program" ID="1" LOGIC_LANG="2">
                <SECTION_LOGIC_ST CONTENT="SystemReady := TRUE;" />
              </PROGRAM>
            </EVENT_TASK>
            <CYCLE_TASK ID="3" CYCLE_TIME="20">
              <PROGRAM NAME="CycleProgram" DESC="cycle task program" ID="2" LOGIC_LANG="2">
                <SECTION_LOGIC_ST CONTENT="StatusWords[1] := StatusWords[0];" />
              </PROGRAM>
            </CYCLE_TASK>
          </CONTROL_SCHEME>
        </HARDWARE_ROBOT_CONTROLLER>
      </HARDWARE_DEVICE_UPLINK_PORT>
      <HARDWARE_DEVICE_DOWNLINK_PORT ID="5" NAME="CAN1" DISPLAY="CAN1" PHYSICAL_ID="64" PROTOCOL="4" TYPE="3">
        <HARDWARE_NET>
          <HARDWARE_DEVICE_UPLINK_PORT ADDRESS="1" NAME="Axis1">
            <HARDWARE_PROPERTY ID="CAN_DEVICE_TYPE" VALUE="servo" />
            <HARDWARE_CAN_DEVICE_MOTOR>
              <HARDWARE_CAN_DEVICE_SLAVE DEVICE_NAME="Axis1" NODE_ID="1">
                <HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_Position_6004" HARDWARE_GROUP_ENABLE="YES" INDEX_ID="24580" SUB_INDEX_ID="0" CMD_ACCESS_TYPE="ro" OUTPUT_LENGTH="4" CYCLE_TIME="10">
                  <HARDWARE_CAN_CMD ID="cmd1">
                    <HARDWARE_CHANNEL_TAG NAME="Axis1_Position_6004" DATATYPE="BYTE[4]" DESC="axis position" ENABLE="YES" INIT_VALUE="" READONLY="NO" VISIBLE="YES">
                      <VARIABLE_MEMBER NAME="Axis1_Position_6004[0]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                      <VARIABLE_MEMBER NAME="Axis1_Position_6004[1]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                      <VARIABLE_MEMBER NAME="Axis1_Position_6004[2]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                      <VARIABLE_MEMBER NAME="Axis1_Position_6004[3]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                    </HARDWARE_CHANNEL_TAG>
                  </HARDWARE_CAN_CMD>
                </HARDWARE_CAN_CMD_GROUP>
              </HARDWARE_CAN_DEVICE_SLAVE>
            </HARDWARE_CAN_DEVICE_MOTOR>
          </HARDWARE_DEVICE_UPLINK_PORT>
        </HARDWARE_NET>
      </HARDWARE_DEVICE_DOWNLINK_PORT>
      <HARDWARE_DEVICE_DOWNLINK_PORT ID="8" NAME="CAN4" DISPLAY="CAN2" PHYSICAL_ID="67" PROTOCOL="4" TYPE="5">
        <HARDWARE_CAN_SLAVER_OBJECT INDEX="8192" DESC="Status_TPDO" DATATYPE="uint32" ARRAY_FLAG="YES" ARRAY_SIZE="2" ENABLE="YES" PDO_INDEX="6656" PDO_DESC="Transmit PDO 1">
          <HARDWARE_MODBUS_TAG_MAPPING OFFSET="0" TAG_NAME="StatusWords[0]" />
          <HARDWARE_MODBUS_TAG_MAPPING OFFSET="1" TAG_NAME="StatusWords[1]" />
        </HARDWARE_CAN_SLAVER_OBJECT>
      </HARDWARE_DEVICE_DOWNLINK_PORT>
    </HARDWARE_NET>
  </HARDWARE>
  <SYS_DATA_TYPE />
  <USER_DATA_TYPE>
    <USER_STRUCT NAME="DriveStatus" DESC="drive status structure">
      <USER_STRUCT_MEMBER NAME="Ready" DATATYPE="BOOL" DESC="ready flag" INIT_VALUE="" VISIBLE="YES" />
      <USER_STRUCT_MEMBER NAME="Position" DATATYPE="DINT" DESC="position value" INIT_VALUE="0" VISIBLE="YES" />
    </USER_STRUCT>
  </USER_DATA_TYPE>
</PROJECT>
"""


def run_tool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=check,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


class XcskrToolTests(unittest.TestCase):
    def make_project(self, folder: Path) -> Path:
        project = folder / "demo.xcskr"
        project.write_text(FIXTURE_XML, encoding="gbk")
        return project

    def test_export_ai_package_contains_core_structures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)
            out_dir = temp_path / "ai-pack"

            run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "files")

            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
            hardware = json.loads((out_dir / "hardware.json").read_text(encoding="utf-8"))
            variables = json.loads((out_dir / "variables.json").read_text(encoding="utf-8"))
            udt = json.loads((out_dir / "user-data-types.json").read_text(encoding="utf-8"))
            fb = json.loads((out_dir / "function-blocks.json").read_text(encoding="utf-8"))

            self.assertEqual(index["project"]["name"], "DemoProject")
            task_kinds = {task["kind"] for task in index["control_scheme"]["tasks"]}
            self.assertLessEqual({"main", "event", "cycle"}, task_kinds)
            self.assertTrue(any(program["name"] == "MainProgram" for task in index["control_scheme"]["tasks"] for program in task["programs"]))
            self.assertTrue(any(task["trigger_condition"] for task in index["control_scheme"]["tasks"] if task["kind"] == "event"))
            self.assertTrue(any(port["id"] == "8" and port["display"] == "CAN2" for port in hardware["downlink_ports"]))
            self.assertTrue(any(tag["name"] == "Axis1_Position_6004" and tag["index_hex"] == "0x6004" for tag in hardware["hardware_tags"]))
            self.assertTrue(any(var["name"] == "SystemReady" for var in variables["variables"]))
            struct = next(item for item in udt["user_structs"] if item["name"] == "DriveStatus")
            self.assertTrue(any(member["name"] == "Position" for member in struct["members"]))
            self.assertTrue(any(block["name"] == "FB_SCALE" and block["st_file"] for block in fb["function_blocks"]))
            self.assertIn("Scale := InValue", (out_dir / "st" / "function-blocks" / "FB_SCALE.st").read_text(encoding="utf-8"))

    def test_set_attrs_updates_structured_entities_without_xml_hand_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)
            copy_project = temp_path / "demo-copy.xcskr"
            shutil.copy2(project, copy_project)

            run_tool(
                "set-attrs",
                "--project",
                str(copy_project),
                "--kind",
                "variable",
                "--name",
                "SystemReady",
                "--attr",
                "DESC=unit test variable description",
                "--no-backup",
            )
            run_tool(
                "set-attrs",
                "--project",
                str(copy_project),
                "--kind",
                "pou",
                "--pou-type",
                "program",
                "--name",
                "CycleProgram",
                "--attr",
                "DESC=unit test cycle program",
                "--no-backup",
            )
            run_tool(
                "set-attrs",
                "--project",
                str(copy_project),
                "--kind",
                "user-struct-member",
                "--struct",
                "DriveStatus",
                "--member",
                "Ready",
                "--attr",
                "DESC=unit test member description",
                "--no-backup",
            )
            run_tool(
                "set-attrs",
                "--project",
                str(copy_project),
                "--kind",
                "hardware-tag",
                "--name",
                "Axis1_Position_6004",
                "--attr",
                "DESC=unit test hardware tag",
                "--no-backup",
            )
            run_tool(
                "set-attrs",
                "--project",
                str(copy_project),
                "--kind",
                "slave-object",
                "--port-id",
                "8",
                "--index",
                "8192",
                "--attr",
                "DESC=unit test slave object",
                "--no-backup",
            )
            run_tool(
                "set-attrs",
                "--project",
                str(copy_project),
                "--kind",
                "slave-mapping",
                "--port-id",
                "8",
                "--index",
                "8192",
                "--offset",
                "0",
                "--attr",
                "TAG_NAME=StatusWords[1]",
                "--no-backup",
            )

            out_dir = temp_path / "pack-after"
            run_tool("export-ai", "--project", str(copy_project), "--output-dir", str(out_dir), "--st-mode", "none")
            variables = json.loads((out_dir / "variables.json").read_text(encoding="utf-8"))
            programs = json.loads((out_dir / "programs.json").read_text(encoding="utf-8"))
            udt = json.loads((out_dir / "user-data-types.json").read_text(encoding="utf-8"))
            hardware = json.loads((out_dir / "hardware.json").read_text(encoding="utf-8"))

            self.assertEqual(next(var for var in variables["variables"] if var["name"] == "SystemReady")["desc"], "unit test variable description")
            self.assertEqual(next(program for program in programs["programs"] if program["name"] == "CycleProgram")["desc"], "unit test cycle program")
            struct = next(item for item in udt["user_structs"] if item["name"] == "DriveStatus")
            self.assertEqual(next(member for member in struct["members"] if member["name"] == "Ready")["desc"], "unit test member description")
            self.assertEqual(next(tag for tag in hardware["hardware_tags"] if tag["name"] == "Axis1_Position_6004")["desc"], "unit test hardware tag")
            self.assertEqual(next(obj for obj in hardware["slave_objects"] if obj["index"] == "8192")["desc"], "unit test slave object")
            self.assertEqual(next(mapping for mapping in hardware["slave_mappings"] if mapping["index"] == "8192" and mapping["offset"] == "0")["tag_name"], "StatusWords[1]")

    def test_cli_help_is_generic(self) -> None:
        result = run_tool("--help")

        self.assertIn("export-ai", result.stdout)
        self.assertIn("set-attrs", result.stdout)
        self.assertNotIn("project-specific", result.stdout.lower())
        self.assertNotIn("gateway", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
