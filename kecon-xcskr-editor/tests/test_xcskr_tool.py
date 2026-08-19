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
            <MAIN_TASK DESC="" ID="1" NAME="">
              <PROGRAM NAME="MainProgram" DESC="main task program" ID="0" LOGIC_LANG="2">
                <SECTION_LOGIC_ST CONTENT="FB_SCALE(InValue:=1, Scale=>StatusWords[0]);" />
              </PROGRAM>
            </MAIN_TASK>
            <EVENT_TASK DESC="" EVENT_NAME="DI0 rising edge" ID="2">
              <PROGRAM NAME="EventProgram" DESC="event task program" ID="1" LOGIC_LANG="2">
                <SECTION_LOGIC_ST CONTENT="SystemReady := TRUE;" />
              </PROGRAM>
              <TRIG_CONDITION ENABLE_UPLIMIT="NO" EVENT_TRIGGER="0" LOWCOMPARE="-1" LOWLIMIT="" OPERATORCOMPARE="-1" UPCOMPARE="-1" UPLIMIT="" VAR="DI0" />
            </EVENT_TASK>
            <CYCLE_TASK CYCLE="20" DESC="serial devices" ID="3">
              <PROGRAM NAME="CycleProgram" DESC="cycle task program" ID="2" LOGIC_LANG="2">
                <SECTION_LOGIC_ST CONTENT="StatusWords[1] := StatusWords[0];" />
              </PROGRAM>
              <PROGRAM NAME="LadderProgram" DESC="ld program" ID="3" LOGIC_LANG="0">
                <SECTION_LOGIC_LD>
                  <CONTROL_LOGIC_BLOCK DEACTIVE="" DESC="" NAME="_MODULE0" POSITION_TYPE="1" RECT_POSITION="60,200,240,300" SHOWEN="" TYPE="UINT2BYTE">
                    <BLOCK_PIN_INPUT DATATYPE="BOOL" DESC="" ENABLED="YES" INIT_VALUE="" NAME="EN" VISIBLE="YES"/>
                    <BLOCK_PIN_INPUT DATATYPE="UINT" DESC="" ENABLED="YES" INIT_VALUE="0" NAME="IN" NEGATED="" VISIBLE="YES">
                      <CONTROL_BLOCK_CONNECTION CONNECTION_TYPE="1" CONNECTION_VALUE="StatusWords[0]"/>
                    </BLOCK_PIN_INPUT>
                    <BLOCK_PIN_OUTPUT DATATYPE="BYTE" DESC="high byte" ENABLED="YES" INIT_VALUE="0" NAME="Q_H" NEGATED="" VISIBLE="YES">
                      <CONTROL_BLOCK_CONNECTION CONNECTION_TYPE="2" CONNECTION_VALUE="_LINE0"/>
                    </BLOCK_PIN_OUTPUT>
                    <BLOCK_PIN_OUTPUT DATATYPE="BYTE" DESC="low byte" ENABLED="YES" INIT_VALUE="0" NAME="Q_L" NEGATED="" VISIBLE="YES"/>
                  </CONTROL_LOGIC_BLOCK>
                  <CONTROL_LOGIC_BLOCK DEACTIVE="" DESC="" NAME="_MODULE1" POSITION_TYPE="1" RECT_POSITION="300,200,480,300" SHOWEN="" TYPE="MOV">
                    <BLOCK_PIN_INPUT DATATYPE="BOOL" DESC="" ENABLED="YES" INIT_VALUE="" NAME="EN" VISIBLE="YES"/>
                    <BLOCK_PIN_INPUT DATATYPE="BYTE" DESC="" ENABLED="YES" INIT_VALUE="0" NAME="IN" NEGATED="" VISIBLE="YES">
                      <CONTROL_BLOCK_CONNECTION CONNECTION_TYPE="2" CONNECTION_VALUE="_LINE0"/>
                    </BLOCK_PIN_INPUT>
                    <BLOCK_PIN_INPUT DATATYPE="BYTE" DESC="" ENABLED="YES" INIT_VALUE="0" NAME="IN2" NEGATED="" VISIBLE="YES"/>
                    <BLOCK_PIN_OUTPUT DATATYPE="BYTE" DESC="" ENABLED="YES" INIT_VALUE="0" NAME="OUT" NEGATED="" VISIBLE="YES"/>
                  </CONTROL_LOGIC_BLOCK>
                  <CONTROL_LOGIC_LINE DEACTIVE="" FROM_POWERRAIL="NO" LINE_POSITION="240,250,270,250,300,250" NAME="_LINE0" POSITION_TYPE="0" TYPE=""/>
                </SECTION_LOGIC_LD>
              </PROGRAM>
              <PROGRAM NAME="ChassisProgram" DESC="fbd program" ID="4" LOGIC_LANG="1">
                <SECTION_LOGIC_FBD>
                  <CONTROL_LOGIC_COMMENT COLOR="32768" CONTENT="chassis block" NAME="_COMMENT0" POSITION_TYPE="1" RECT_POSITION="60,40,300,120"/>
                  <CONTROL_LOGIC_BLOCK DEACTIVE="" DESC="" NAME="_MODULE0" POSITION_TYPE="1" RECT_POSITION="240,160,600,600" SHOWEN="YES" TYPE="GenericChassis">
                    <BLOCK_PIN_INPUT DATATYPE="BOOL" DESC="" ENABLED="YES" INIT_VALUE="" NAME="EN" VISIBLE="YES"/>
                    <BLOCK_PIN_INPUT DATATYPE="REAL" DESC="linear speed" ENABLED="YES" INIT_VALUE="0.000" NAME="V_lin" NEGATED="" STRUCT="" VISIBLE="YES"/>
                    <BLOCK_PIN_OUTPUT DATATYPE="REAL" DESC="wheel speed" ENABLED="YES" INIT_VALUE="0.000" NAME="V_wheel" NEGATED="" STRUCT="" VISIBLE="YES"/>
                  </CONTROL_LOGIC_BLOCK>
                </SECTION_LOGIC_FBD>
              </PROGRAM>
            </CYCLE_TASK>
          </CONTROL_SCHEME>
          <TAGCONFIG/>
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

    def test_export_graphic_reads_ld_and_fbd_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("export-graphic", "--project", str(project), "--format", "json")
            package = json.loads(result.stdout)
            by_name = {pou["name"]: pou for pou in package["pous"]}

            self.assertEqual(by_name["LadderProgram"]["language"], "ld")
            self.assertEqual(by_name["LadderProgram"]["section"], "SECTION_LOGIC_LD")
            self.assertEqual(by_name["LadderProgram"]["logic_lang_hint"], "ld")
            self.assertEqual(by_name["LadderProgram"]["line_count"], 1)
            self.assertEqual(by_name["ChassisProgram"]["language"], "fbd")
            self.assertEqual(by_name["ChassisProgram"]["comment_count"], 1)

            module0 = next(block for block in by_name["LadderProgram"]["blocks"] if block["name"] == "_MODULE0")
            operand = next(pin for pin in module0["inputs"] if pin["name"] == "IN")
            self.assertEqual(operand["connection"]["kind"], "variable")
            self.assertEqual(operand["connection"]["value"], "StatusWords[0]")
            wire = next(pin for pin in module0["outputs"] if pin["name"] == "Q_H")
            self.assertEqual(wire["connection"]["kind"], "line")
            self.assertEqual(wire["connection"]["value"], "_LINE0")

    def test_export_ai_reports_graphic_pous(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)
            out_dir = temp_path / "pack"

            run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "none")

            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
            graphics = json.loads((out_dir / "graphics.json").read_text(encoding="utf-8"))
            self.assertEqual(index["counts"]["graphic_pous"], 2)
            languages = {pou["name"]: pou["language"] for pou in index["graphic_pous"]}
            self.assertEqual(languages, {"LadderProgram": "ld", "ChassisProgram": "fbd"})
            self.assertTrue(any(pou["blocks"] for pou in graphics["pous"]))

    def test_add_user_struct_and_variable_generate_member_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)

            run_tool(
                "add-user-struct", "--project", str(project), "--name", "WheelData",
                "--desc", "wheel data", "--member", "Enable:BOOL:participates",
                "--member", "Angle:DINT:angle in 0.01 deg", "--no-backup",
            )
            run_tool(
                "add-variable", "--project", str(project), "--name", "Wheel",
                "--datatype", "WheelData[4]", "--desc", "four wheels", "--no-backup",
            )
            run_tool(
                "add-variable", "--project", str(project), "--name", "StopReq",
                "--datatype", "BOOL", "--init-value", "OFF", "--no-backup",
            )

            out_dir = temp_path / "pack"
            run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "none")
            variables = {var["name"]: var for var in json.loads((out_dir / "variables.json").read_text(encoding="utf-8"))["variables"]}
            structs = {item["name"]: item for item in json.loads((out_dir / "user-data-types.json").read_text(encoding="utf-8"))["user_structs"]}

            self.assertEqual(len(structs["WheelData"]["members"]), 2)
            wheel = variables["Wheel"]
            self.assertEqual(len(wheel["members"]), 4)
            self.assertEqual(wheel["members"][0]["name"], "Wheel[0]")
            self.assertEqual(wheel["members"][0]["datatype"], "WheelData")
            self.assertEqual([member["name"] for member in wheel["members"][0]["members"]], ["Wheel[0].Enable", "Wheel[0].Angle"])
            self.assertEqual(variables["StopReq"]["members"], [])

            # The user variable container is TAGCONFIG, which the fixture leaves self-closing.
            raw = project.read_text(encoding="gbk")
            self.assertIn("<TAGCONFIG>", raw)
            self.assertNotIn("READONLY", raw.split("<TAGCONFIG>")[1].split("</TAGCONFIG>")[0].split("VARIABLE_MEMBER")[1].split("/>")[0])

    def test_struct_member_change_is_detected_and_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            run_tool("add-user-struct", "--project", str(project), "--name", "WheelData", "--member", "Enable:BOOL", "--no-backup")
            run_tool("add-variable", "--project", str(project), "--name", "Wheel", "--datatype", "WheelData[4]", "--no-backup")

            clean = run_tool("validate-datatypes", "--project", str(project), "--strict")
            self.assertIn("Problems=0", clean.stdout)

            run_tool("add-user-struct-member", "--project", str(project), "--struct", "WheelData", "--member", "Online:BOOL", "--no-backup")
            stale = run_tool("validate-datatypes", "--project", str(project), "--strict", check=False)
            self.assertEqual(stale.returncode, 1)
            self.assertIn("MEMBER_MISMATCH", stale.stdout)
            self.assertIn("Wheel[0].Online", stale.stdout)

            run_tool("rebuild-variable-members", "--project", str(project), "--name", "Wheel", "--no-backup")
            fixed = run_tool("validate-datatypes", "--project", str(project), "--strict")
            self.assertIn("Problems=0", fixed.stdout)

    def test_add_variable_rejects_name_and_datatype_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            clash = run_tool("add-variable", "--project", str(project), "--name", "Axis1_Position_6004", "--datatype", "BOOL", "--no-backup", check=False)
            self.assertEqual(clash.returncode, 2)
            self.assertIn("HARDWARE_CHANNEL_TAG", clash.stderr)

            unknown = run_tool("add-variable", "--project", str(project), "--name", "Foo", "--datatype", "NoSuchType[2]", "--no-backup", check=False)
            self.assertEqual(unknown.returncode, 2)
            self.assertIn("unknown DATATYPE", unknown.stderr)

            forced = run_tool("add-variable", "--project", str(project), "--name", "Foo", "--datatype", "NoSuchType[2]", "--allow-unknown-datatype", "--no-backup")
            self.assertIn("AddedVariable=Foo", forced.stdout)

            duplicate = run_tool("add-variable", "--project", str(project), "--name", "Foo", "--datatype", "BOOL", "--no-backup", check=False)
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("already exists", duplicate.stderr)

            run_tool("remove", "--project", str(project), "--kind", "variable", "--name", "Foo", "--no-backup")
            after = run_tool("validate-datatypes", "--project", str(project), "--show-all")
            self.assertNotIn("Foo", after.stdout)

    def test_set_pin_bind_and_unbind_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            before = project.read_text(encoding="gbk")

            run_tool(
                "set-pin", "--project", str(project), "--pou", "LadderProgram",
                "--block", "_MODULE0", "--pin", "IN", "--unbind", "--no-backup",
            )
            self.assertNotIn('CONNECTION_VALUE="StatusWords[0]"', project.read_text(encoding="gbk"))

            run_tool(
                "set-pin", "--project", str(project), "--pou", "LadderProgram",
                "--block", "_MODULE0", "--pin", "IN", "--bind", "StatusWords[0]", "--no-backup",
            )
            self.assertEqual(project.read_text(encoding="gbk"), before)

            rejected = run_tool(
                "set-pin", "--project", str(project), "--pou", "LadderProgram",
                "--block", "_MODULE0", "--pin", "IN", "--bind", "NotDeclared", "--no-backup", check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("--allow-unknown-operand", rejected.stderr)

    def test_connect_and_disconnect_pins(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            run_tool(
                "connect-pins", "--project", str(project), "--pou", "LadderProgram",
                "--from-block", "_MODULE0", "--from-pin", "Q_L",
                "--to-block", "_MODULE1", "--to-pin", "IN2", "--no-backup",
            )
            package = json.loads(run_tool("export-graphic", "--project", str(project), "--pou", "LadderProgram", "--format", "json").stdout)
            program = package["pous"][0]
            self.assertEqual(program["line_count"], 2)
            names = {line["NAME"] for line in program["lines"]}
            self.assertEqual(names, {"_LINE0", "_LINE1"})
            source = next(pin for block in program["blocks"] if block["name"] == "_MODULE0" for pin in block["outputs"] if pin["name"] == "Q_L")
            target = next(pin for block in program["blocks"] if block["name"] == "_MODULE1" for pin in block["inputs"] if pin["name"] == "IN2")
            self.assertEqual(source["connection"]["value"], "_LINE1")
            self.assertEqual(target["connection"]["value"], "_LINE1")
            self.assertEqual(target["connection"]["kind"], "line")

            run_tool("disconnect-line", "--project", str(project), "--pou", "LadderProgram", "--line-name", "_LINE1", "--no-backup")
            after = json.loads(run_tool("export-graphic", "--project", str(project), "--pou", "LadderProgram", "--format", "json").stdout)["pous"][0]
            self.assertEqual(after["line_count"], 1)
            self.assertEqual(after["connected_output_count"], 1)

    def test_copy_block_between_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            reference = self.make_project(temp_path)
            target = temp_path / "target.xcskr"
            shutil.copy2(reference, target)

            run_tool(
                "copy-block", "--project", str(target), "--reference", str(reference),
                "--reference-pou", "LadderProgram", "--block", "_MODULE1",
                "--pou", "ChassisProgram", "--rect-position", "700,160,880,260", "--no-backup",
            )

            package = json.loads(run_tool("export-graphic", "--project", str(target), "--pou", "ChassisProgram", "--format", "json").stdout)
            blocks = {block["name"]: block for block in package["pous"][0]["blocks"]}
            self.assertIn("_MODULE1", blocks)
            self.assertEqual(blocks["_MODULE1"]["type"], "MOV")
            self.assertEqual(blocks["_MODULE1"]["rect_position"], "700,160,880,260")
            # Connections point at lines that do not exist in the target section, so they are stripped.
            self.assertEqual(blocks["_MODULE1"]["connected_inputs"], 0)

    def program_order(self, project: Path, task_kind: str = "main") -> list[str]:
        out_dir = project.parent / "order-pack"
        run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "none")
        index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
        task = next(item for item in index["control_scheme"]["tasks"] if item["kind"] == task_kind)
        return [program["name"] for program in task["programs"]]

    def test_add_and_move_program_control_execution_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            self.assertEqual(self.program_order(project), ["MainProgram"])

            run_tool("add-program", "--project", str(project), "--name", "StateMachine", "--desc", "agv state machine", "--after", "MainProgram", "--no-backup")
            run_tool("add-program", "--project", str(project), "--name", "AlarmManager", "--no-backup")
            self.assertEqual(self.program_order(project), ["MainProgram", "StateMachine", "AlarmManager"])

            # Programs execute in document order, so placement is functional.
            run_tool("move-program", "--project", str(project), "--name", "AlarmManager", "--before", "StateMachine", "--no-backup")
            self.assertEqual(self.program_order(project), ["MainProgram", "AlarmManager", "StateMachine"])

            raw = project.read_text(encoding="gbk")
            self.assertIn('ENABLE_SHOW="YES"', raw)
            self.assertIn('NAME="StateMachine"', raw)
            # A fresh ST page starts with an empty logic section, ready for replace-st.
            run_tool("replace-st", "--project", str(project), "--pou-type", "program", "--name", "StateMachine", "--st-file", str(self.write_st(Path(temp), "State := 1;\nStep := State + 1;\n")), "--no-backup")
            extracted = run_tool("extract-st", "--project", str(project), "--pou-type", "program", "--name", "StateMachine").stdout
            self.assertIn("Step := State + 1;", extracted)

            duplicate = run_tool("add-program", "--project", str(project), "--name", "StateMachine", "--no-backup", check=False)
            self.assertEqual(duplicate.returncode, 2)

    def write_st(self, folder: Path, content: str) -> Path:
        path = folder / "body.st"
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def test_add_function_block_with_interface_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)

            run_tool(
                "add-function-block", "--project", str(project), "--name", "AlarmLatch",
                "--desc", "latch and reset one alarm",
                "--input", "Trigger:BOOL:alarm condition", "--input", "Code:UINT:alarm code",
                "--output", "Active:BOOL:alarm is active",
                "--internal", "prevReset:BOOL:previous reset state",
                "--no-backup",
            )
            run_tool(
                "add-pou-var", "--project", str(project), "--name", "AlarmLatch",
                "--var-section", "input", "--var", "Reset:BOOL:reset request", "--no-backup",
            )

            out_dir = temp_path / "pack"
            run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "none")
            blocks = {item["name"]: item for item in json.loads((out_dir / "function-blocks.json").read_text(encoding="utf-8"))["function_blocks"]}
            block = blocks["AlarmLatch"]
            self.assertEqual([var["name"] for var in block["inputs"]], ["Trigger", "Code", "Reset"])
            self.assertEqual([var["name"] for var in block["outputs"]], ["Active"])
            self.assertEqual([var["name"] for var in block["internals"]], ["prevReset"])
            # The GUI writes a per-type default initial value on interface pins.
            self.assertEqual(next(var for var in block["inputs"] if var["name"] == "Trigger")["init_value"], "OFF")
            self.assertEqual(next(var for var in block["inputs"] if var["name"] == "Code")["init_value"], "0")

            clash = run_tool("add-function-block", "--project", str(project), "--name", "AlarmLatch", "--no-backup", check=False)
            self.assertEqual(clash.returncode, 2)

    def test_cycle_and_event_tasks_are_read_and_edited(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)

            listed = json.loads(run_tool("list-tasks", "--project", str(project), "--format", "json").stdout)
            by_kind = {row["kind"]: row for row in listed}
            # Event beats cycle beats main, so the listing is ordered by priority.
            self.assertEqual([row["kind"] for row in listed], ["event", "cycle", "main"])
            # A cycle period lives in CYCLE, not CYCLE_TIME.
            self.assertEqual(by_kind["cycle"]["cycle_ms"], "20")
            self.assertEqual(by_kind["event"]["trigger"], "DI0 rising edge")

            out_dir = temp_path / "pack"
            run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "none")
            tasks = {task["kind"]: task for task in json.loads((out_dir / "index.json").read_text(encoding="utf-8"))["control_scheme"]["tasks"]}
            self.assertEqual(tasks["cycle"]["cycle_ms"], "20")
            self.assertEqual(tasks["event"]["event_name"], "DI0 rising edge")
            self.assertEqual(tasks["event"]["trigger_condition"]["VAR"], "DI0")
            self.assertIn("confirmed", tasks["event"]["trigger_condition"]["EVENT_TRIGGER_KIND"])

            run_tool("add-task", "--project", str(project), "--cycle", "100", "--desc", "slow loop", "--no-backup")
            run_tool("set-attrs", "--project", str(project), "--kind", "task", "--task-id", "3", "--attr", "CYCLE=10", "--no-backup")
            run_tool("set-attrs", "--project", str(project), "--kind", "trig-condition", "--task-id", "2", "--attr", "VAR=DI1", "--no-backup")

            after = {(row["kind"], row["id"]): row for row in json.loads(run_tool("list-tasks", "--project", str(project), "--format", "json").stdout)}
            self.assertEqual(after[("cycle", "3")]["cycle_ms"], "10")
            self.assertEqual(next(row for key, row in after.items() if row["cycle_ms"] == "100")["desc"], "slow loop")
            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))  # stale on purpose
            run_tool("export-ai", "--project", str(project), "--output-dir", str(out_dir), "--st-mode", "none")
            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
            event = next(task for task in index["control_scheme"]["tasks"] if task["kind"] == "event")
            self.assertEqual(event["trigger_condition"]["VAR"], "DI1")

            # The help is explicit that an event task holds exactly one program.
            refused = run_tool("add-program", "--project", str(project), "--name", "Second", "--task-kind", "event", "--no-backup", check=False)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("only one program", refused.stderr)

    def test_unknown_task_kind_is_still_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            # The startup task tag is undocumented; discovery must not filter on a
            # fixed tag list or such a task would vanish from the report.
            raw = project.read_text(encoding="gbk")
            raw = raw.replace(
                "          </CONTROL_SCHEME>",
                '            <STARTUP_TASK DELAY="500" ID="9">\n'
                '              <PROGRAM NAME="BootProgram" DESC="" ID="8" LOGIC_LANG="2">\n'
                '                <SECTION_LOGIC_ST CONTENT="SystemReady := FALSE;" />\n'
                "              </PROGRAM>\n"
                "            </STARTUP_TASK>\n"
                "          </CONTROL_SCHEME>",
                1,
            )
            project.write_text(raw, encoding="gbk", newline="")

            rows = json.loads(run_tool("list-tasks", "--project", str(project), "--format", "json").stdout)
            startup = next(row for row in rows if row["tag"] == "STARTUP_TASK")
            self.assertEqual(startup["programs"], 1)
            self.assertEqual(startup["order"], "BootProgram")

    def test_writes_preserve_file_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = temp_path / "lf.xcskr"
            # Real projects use bare LF; a write must not convert the whole file.
            project.write_text(FIXTURE_XML.replace("\r\n", "\n"), encoding="gbk", newline="")
            before = project.read_bytes()
            self.assertNotIn(b"\r\n", before)

            run_tool("add-variable", "--project", str(project), "--name", "LineEndingProbe", "--datatype", "BOOL", "--no-backup")
            run_tool("set-pin", "--project", str(project), "--pou", "LadderProgram", "--block", "_MODULE0", "--pin", "IN", "--unbind", "--no-backup")
            run_tool("add-program", "--project", str(project), "--name", "Probe", "--no-backup")

            after = project.read_bytes()
            self.assertNotIn(b"\r\n", after)
            self.assertGreater(len(after), len(before))

    def test_cli_help_is_generic(self) -> None:
        result = run_tool("--help")

        self.assertIn("export-ai", result.stdout)
        self.assertIn("set-attrs", result.stdout)
        self.assertNotIn("project-specific", result.stdout.lower())
        self.assertNotIn("gateway", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
