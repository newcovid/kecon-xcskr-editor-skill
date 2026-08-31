from __future__ import annotations

import json
import os
import re
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
        <HARDWARE_ROBOT_CONTROLLER NAME="Controller" TYPE="IVC300" VERSION="5.0.0">
          <GENERAL_CFG CAR_DRIVER_TYPE="23" CAR_WHEEL_COUNT="2" CAR_LENGTH="9750" CAR_WIDTH="3170" CAR_WHEEL_DIAMETER="450" />
          <WHEEL_CFG CAR_WHEEL_DIAMETER="100" CAR_WHEEL_X_POS="4250" CAR_WHEEL_Y_POS="1364" />
          <WHEEL_CFG CAR_WHEEL_DIAMETER="100" CAR_WHEEL_X_POS="4250" CAR_WHEEL_Y_POS="-1364" />
          <NAVI_CFG INIT_NAVA_MODE="5" NAVI_SUPPORT_LASER="NO" />
          <WIZARD_CONFIG CHASSIS_TYPE="Eight-DifferentialAssembly" CONTROLLER="IVC300" PATH="BaseVehicleModel/UniversalVehicle" SUPPORT_CORE_BLOCK="3" VERSION="5.0.0">
            <WIZARD_DEVICE NAME="chassis_structure" DESC="chassis" ENABLE="YES" SUB_TYPE="design_wizard">
              <WIZARD_DEVICE_PARAM NAME="chassis_type" TYPE="chassis_type" VALUE="23" />
            </WIZARD_DEVICE>
          </WIZARD_CONFIG>
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
                <HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="NO" INDEX_ID="0" SUB_INDEX_ID="0" CMD_ACCESS_TYPE="" OUTPUT_LENGTH="2" CYCLE_TIME="100">
                  <HARDWARE_CAN_CMD ID="0">
                    <HARDWARE_CHANNEL_TAG NAME="Axis1_XCS_RPDO1" DATATYPE="BYTE[2]" DESC="disabled pdo" ENABLE="NO" INIT_VALUE="" READONLY="NO" VISIBLE="YES">
                      <VARIABLE_MEMBER NAME="Axis1_XCS_RPDO1[0]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                      <VARIABLE_MEMBER NAME="Axis1_XCS_RPDO1[1]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                    </HARDWARE_CHANNEL_TAG>
                  </HARDWARE_CAN_CMD>
                </HARDWARE_CAN_CMD_GROUP>
                <HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_TPDO1" HARDWARE_GROUP_ENABLE="NO" INDEX_ID="0" SUB_INDEX_ID="0" CMD_ACCESS_TYPE="" OUTPUT_LENGTH="2" CYCLE_TIME="100">
                  <HARDWARE_CAN_CMD ID="0">
                    <HARDWARE_CHANNEL_TAG NAME="Axis1_XCS_TPDO1" DATATYPE="BYTE[2]" DESC="disabled pdo" ENABLE="NO" INIT_VALUE="" READONLY="NO" VISIBLE="YES">
                      <VARIABLE_MEMBER NAME="Axis1_XCS_TPDO1[0]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                      <VARIABLE_MEMBER NAME="Axis1_XCS_TPDO1[1]" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />
                    </HARDWARE_CHANNEL_TAG>
                  </HARDWARE_CAN_CMD>
                </HARDWARE_CAN_CMD_GROUP>
              </HARDWARE_CAN_DEVICE_SLAVE>
            </HARDWARE_CAN_DEVICE_MOTOR>
          </HARDWARE_DEVICE_UPLINK_PORT>
        </HARDWARE_NET>
        <HARDWARE_PROPERTY ID="CAN_BAUD" VALUE="0x04" />
      </HARDWARE_DEVICE_DOWNLINK_PORT>
      <HARDWARE_DEVICE_DOWNLINK_PORT ID="8" NAME="CAN4" DISPLAY="CAN2" PHYSICAL_ID="67" PROTOCOL="4" TYPE="5">
        <HARDWARE_CAN_SLAVER_OBJECT INDEX="8192" DESC="StatusTPDO" DATATYPE="uint32" ARRAY_FLAG="YES" ARRAY_SIZE="2" ENABLE="YES" PDO_INDEX="6656" PDO_DESC="Transmit PDO 1">
          <HARDWARE_MODBUS_TAG_MAPPING OFFSET="0" TAG_NAME="StatusWords[0]" />
          <HARDWARE_MODBUS_TAG_MAPPING OFFSET="1" TAG_NAME="StatusWords[1]" />
        </HARDWARE_CAN_SLAVER_OBJECT>
      </HARDWARE_DEVICE_DOWNLINK_PORT>
      <HARDWARE_DEVICE_DOWNLINK_PORT ID="11" NAME="COM2" DISPLAY="RS485-2" PHYSICAL_ID="82" PROTOCOL="1" TYPE="6" MODE="0" ADDRESS="0">
        <HARDWARE_NET>
          <HARDWARE_DEVICE_UPLINK_PORT ADDRESS="9" NAME="BatteryBms">
            <HARDWARE_OTHER_DEVICE_RTU>
              <HARDWARE_COM_CMD DEV_TYPE="0" ID="251" TYPE="0">
                <HARDWARE_CHANNEL_TAG NAME="Rt_0001" DATATYPE="UINT[2]" DESC="realtime block" ENABLE="YES" INIT_VALUE="" READONLY="NO" VISIBLE="YES">
                  <VARIABLE_MEMBER NAME="Rt_0001[0]" DATATYPE="UINT" DESC="" INIT_VALUE="0" VISIBLE="YES" />
                  <VARIABLE_MEMBER NAME="Rt_0001[1]" DATATYPE="UINT" DESC="" INIT_VALUE="0" VISIBLE="YES" />
                </HARDWARE_CHANNEL_TAG>
                <HARDWARE_FLAG_TAG NAME="Rt_0001_F" DATATYPE="BOOL" DESC="" ENABLE="YES" INIT_VALUE="OFF" VISIBLE="YES" />
                <HARDWARE_PROPERTY ID="COM_CMD_CYCLE" VALUE="200" />
                <HARDWARE_PROPERTY ID="COM_CMD_FC" VALUE="3" />
                <HARDWARE_PROPERTY ID="COM_CMD_START_ADDR" VALUE="1" />
                <HARDWARE_PROPERTY ID="COM_CMD_NUMBER" VALUE="2" />
              </HARDWARE_COM_CMD>
            </HARDWARE_OTHER_DEVICE_RTU>
          </HARDWARE_DEVICE_UPLINK_PORT>
        </HARDWARE_NET>
        <HARDWARE_PROPERTY ID="COM_BAUD" VALUE="12" />
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


# The tool prints Chinese.  On Windows a piped stdout defaults to the ANSI code
# page, so decoding it as UTF-8 here turns every message into U+FFFD and any
# assertIn("<中文>", ...) fails no matter what the tool said.  Pin the child.
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run_tool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=check,
        env=CHILD_ENV,
        text=True,
        encoding="utf-8",
        # The tool prints project text verbatim, and a Windows console running a
        # GBK codepage hands back bytes utf-8 cannot decode. Without this the
        # decode raises, stdout comes back None, and unrelated tests fail
        # depending on the console codepage rather than on the tool.
        errors="replace",
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

    @staticmethod
    def set_element_desc(project: Path, member: str, desc: str) -> None:
        """Write a DESC onto one VARIABLE_MEMBER, the way the GUI lets a person."""
        text = project.read_text(encoding="gbk")
        pattern = re.compile(r'<VARIABLE_MEMBER\b[^>]*?NAME="%s"[^>]*?>' % re.escape(member))
        match = pattern.search(text)
        assert match is not None, "no such member: " + member
        tag = match.group(0)
        new_tag = re.sub(r'DESC="[^"]*"', 'DESC="%s"' % desc, tag, count=1)
        project.write_text(text[:match.start()] + new_tag + text[match.end():], encoding="gbk")

    def test_rebuild_variable_members_keeps_per_element_desc(self) -> None:
        # An array element's description exists only on the variable -- the
        # struct definition has nowhere to record it.  A rebuild regenerates the
        # member tree from that definition, so without carrying the text across
        # it comes back empty, silently: the project still compiles and runs,
        # and the loss only shows as a blank column in the variable monitor much
        # later.  Adding one struct member is enough to force the rebuild.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            run_tool("add-user-struct", "--project", str(project), "--name", "AlarmData",
                     "--member", "Active:BOOL[4]", "--no-backup")
            run_tool("add-variable", "--project", str(project), "--name", "Alm",
                     "--datatype", "AlarmData", "--no-backup")
            self.set_element_desc(project, "Alm.Active[2]", "drive 3 offline")

            run_tool("add-user-struct-member", "--project", str(project), "--struct", "AlarmData",
                     "--member", "Count:BYTE", "--no-backup")
            rebuilt = run_tool("rebuild-variable-members", "--project", str(project),
                               "--name", "Alm", "--no-backup")

            self.assertIn("keptDesc=1", rebuilt.stdout)
            after = project.read_text(encoding="gbk")
            self.assertIn("drive 3 offline", after)
            self.assertIn('NAME="Alm.Count"', after)

    def test_rebuild_variable_members_can_be_told_to_drop_element_desc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            run_tool("add-user-struct", "--project", str(project), "--name", "AlarmData",
                     "--member", "Active:BOOL[4]", "--no-backup")
            run_tool("add-variable", "--project", str(project), "--name", "Alm",
                     "--datatype", "AlarmData", "--no-backup")
            self.set_element_desc(project, "Alm.Active[2]", "drive 3 offline")

            rebuilt = run_tool("rebuild-variable-members", "--project", str(project),
                               "--name", "Alm", "--drop-element-desc", "--no-backup")

            self.assertIn("keptDesc=0", rebuilt.stdout)
            self.assertNotIn("drive 3 offline", project.read_text(encoding="gbk"))

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

    def test_export_ai_reports_controller_and_chassis_config(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_project(root)
            out = root / "pack"

            run_tool("export-ai", "--project", str(project), "--output-dir", str(out))

            index = json.loads((out / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["controller"]["type"], "IVC300")
            self.assertEqual(index["controller"]["chassis_driver_type"], "23")
            self.assertEqual(index["controller"]["chassis_driver_type_name"], "八差速总成底盘")

            controller = json.loads((out / "controller.json").read_text(encoding="utf-8"))
            self.assertEqual(controller["general_cfg"]["CAR_DRIVER_TYPE"], "23")
            self.assertEqual(controller["wizard_config"]["CHASSIS_TYPE"], "Eight-DifferentialAssembly")
            self.assertEqual(len(controller["wheel_cfg"]), 2)
            self.assertEqual(controller["wizard_devices"][0]["params"][0]["VALUE"], "23")

    def test_set_node_id_updates_both_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            project = self.make_project(Path(folder))

            run_tool("set-node-id", "--project", str(project), "--port-id", "5",
                     "--address", "1", "--node-id", "9", "--no-backup")

            text = project.read_text(encoding="gbk", newline="")
            self.assertIn('<HARDWARE_DEVICE_UPLINK_PORT ADDRESS="9"', text)
            self.assertIn('NODE_ID="9"', text)
            self.assertNotIn('NODE_ID="1"', text)

    def put_st(self, project: Path, pou: str, body: str) -> None:
        st = project.parent / "body.st"
        st.write_text(body, encoding="utf-8", newline="")
        run_tool("replace-st", "--project", str(project), "--pou-type", "program",
                 "--name", pou, "--st-file", str(st), "--no-backup")

    def test_validate_fb_calls_flags_a_pin_left_out(self) -> None:
        # A pin left out and a pin out of order look identical from the
        # compiler: one FBDError id=769, no line number, no pin named.  The
        # checker used to pass calls that simply omitted a pin.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            self.put_st(project, "CycleProgram", "FB_SCALE(InValue=1);")

            result = run_tool("validate-fb-calls", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pin not listed", result.stdout)
            self.assertIn("Scale", result.stdout)

    def test_validate_fb_calls_passes_when_every_pin_is_listed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            self.put_st(project, "CycleProgram", "FB_SCALE(InValue=1, Scale=>StatusWords[0]);")

            result = run_tool("validate-fb-calls", "--project", str(project), check=False)

            self.assertIn("FB_CALLS=OK", result.stdout)

    def test_validate_array_index_flags_a_bit_string_subscript(self) -> None:
        # BOOL/BYTE/WORD/DWORD are bit strings in IEC 61131-3, not numbers.
        # Subscripting with one is refused: 文本"["错误，数组的索引值不是整数,
        # plus a follow-on 匹配变量表达式失败 on the same statement.  BYTE is
        # the tempting type for a ring buffer pointer, and it compares against
        # an integer without complaint, so nothing warns before the compiler.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            self.put_st(project, "MainProgram", "StatusWords[SystemReady] := 1;")

            result = run_tool("validate-array-index", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BIT_STRING", result.stdout)
            self.assertIn("SystemReady", result.stdout)

    def test_validate_array_index_accepts_integer_and_literal_subscripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            self.put_st(project, "MainProgram", "StatusWords[0] := StatusWords[1];")

            result = run_tool("validate-array-index", "--project", str(project), check=False)

            self.assertEqual(result.returncode, 0)
            self.assertIn("ARRAY_INDEX=OK", result.stdout)

    def test_validate_array_index_ignores_comments_and_reports_the_real_line(self) -> None:
        # Two traps in one: a subscript written inside a comment must not be
        # reported, and the line number has to come from the raw attribute --
        # a literal line break inside an XML attribute value is normalized to
        # a space by any conforming parser, so reading CONTENT through
        # ElementTree collapses the POU to one line and every finding lands on
        # line 1.
        body = (
            "StatusWords[0] := 0;\n"
            "(* StatusWords[SystemReady] would be refused *)\n"
            "StatusWords[SystemReady] := 1;\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            self.put_st(project, "MainProgram", body)

            result = run_tool("validate-array-index", "--project", str(project), check=False)

            self.assertIn("Problems=1", result.stdout)
            offending = [line for line in result.stdout.splitlines() if "BIT_STRING" in line]
            self.assertEqual(len(offending), 1)
            self.assertIn(" 3 ", offending[0])

    def test_validate_canopen_command_ids_flags_an_enabled_group_without_an_id(self) -> None:
        # xRobotDesigner allocates the command id when the group is ticked in
        # the GUI.  A group enabled by editing the XML goes live without one,
        # and the compiler then blames the PROGRAMS that use the tag
        # (文本"<tag>"错误，字符串无法识别) instead of the group -- 216 errors
        # from 27 such groups on IVC300,.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            raw = project.read_text(encoding="gbk", newline="")
            raw = raw.replace(
                '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="NO"',
                '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="YES"')
            project.write_text(raw, encoding="gbk", newline="")

            result = run_tool("validate-canopen-command-ids", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CANOPEN_COMMAND_IDS=FAIL", result.stdout)
            self.assertIn("EnabledWithoutId=1", result.stdout)

    def test_validate_canopen_command_ids_leaves_disabled_groups_alone(self) -> None:
        # An id of "" or "0" is normal on a group that was never enabled, and
        # those repeat freely -- only enabled groups need one.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("validate-canopen-command-ids", "--project", str(project), check=False)

            self.assertIn("CANOPEN_COMMAND_IDS=OK", result.stdout)

    def test_validate_slave_objects_passes_on_a_clean_dictionary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("validate-slave-objects", "--project", str(project), check=False)

            self.assertIn("SLAVE_OBJECTS=OK", result.stdout)
            self.assertIn("Port8Mappings=2/63", result.stdout)

    def test_validate_slave_objects_flags_an_illegal_name(self) -> None:
        # The GUI refuses a slave object name that is empty, longer than 15
        # characters, or holds anything but ASCII letters and digits.  A name
        # written past the GUI compiles and downloads, and the controller then
        # builds no dictionary at all -- every SDO read aborts 0x06020000 and
        # no TPDO is sent (measured).
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            raw = project.read_text(encoding="gbk", newline="")
            raw = raw.replace('DESC="StatusTPDO"', 'DESC="Status_Word_0_7_SDO"')
            project.write_text(raw, encoding="gbk", newline="")

            result = run_tool("validate-slave-objects", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SLAVE_OBJECTS=FAIL", result.stdout)
            self.assertIn("max 15", result.stdout)

    def test_validate_slave_objects_flags_a_datatype_outside_the_dropdown(self) -> None:
        # The dropdown says "boolean"; "bool" is accepted by a text edit and by
        # the compiler, and is not a value the runtime knows.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            raw = project.read_text(encoding="gbk", newline="")
            raw = raw.replace('DATATYPE="uint32" ARRAY_FLAG="YES" ARRAY_SIZE="2"',
                              'DATATYPE="bool" ARRAY_FLAG="YES" ARRAY_SIZE="2"')
            project.write_text(raw, encoding="gbk", newline="")

            result = run_tool("validate-slave-objects", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not one of the GUI dropdown values", result.stdout)

    def test_validate_slave_objects_flags_a_port_over_the_mapping_budget(self) -> None:
        # 63 bound variables work, 64 kill the whole dictionary -- bisected on
        # real hardware.  Object count, byte total and sub-index
        # count were each ruled out along the way.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            raw = project.read_text(encoding="gbk", newline="")
            extra = "".join(
                f'<HARDWARE_MODBUS_TAG_MAPPING OFFSET="{i}" TAG_NAME="StatusWords[0]" />'
                for i in range(2, 64)
            )
            raw = raw.replace("</HARDWARE_CAN_SLAVER_OBJECT>", extra + "</HARDWARE_CAN_SLAVER_OBJECT>")
            project.write_text(raw, encoding="gbk", newline="")

            result = run_tool("validate-slave-objects", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SLAVE_OBJECTS=FAIL", result.stdout)
            self.assertIn("Port8Mappings=64/63", result.stdout)

    NL = chr(10)

    def with_st(self, folder, body: str):
        """Fixture with one program's ST replaced by `body`."""
        project = self.make_project(folder)
        raw = project.read_text(encoding="gbk", newline="")
        start = raw.index("<SECTION_LOGIC_ST CONTENT=\"")
        head = raw.index("\"", start + len("<SECTION_LOGIC_ST CONTENT=")) + 1
        tail = raw.index("\"", head)
        encoded = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        encoded = encoded.replace(chr(34), "&quot;").replace(chr(10), "&#x0D;&#x0A;")
        raw = raw[:head] + encoded + raw[tail:]
        project.write_text(raw, encoding="gbk", newline="")
        return project

    def test_validate_comment_balance_accepts_a_closed_multiline_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.with_st(Path(temp),
                "(* a comment" + self.NL + "   spanning lines *)" + self.NL + "    Speed := 3;" + self.NL)

            result = run_tool("validate-comment-balance", "--project", str(project))

            self.assertIn("COMMENT_BALANCE=OK", result.stdout)

    def test_validate_comment_balance_flags_a_comment_that_eats_the_next_statement(self) -> None:
        # A missing *) runs the comment on to the next end-of-line comment and
        # takes that whole statement with it.  Not a syntax error, compiles and
        # downloads fine, and the only symptom is one assignment that never
        # happened -- observed on 5.1.0 three programs downstream.
        with tempfile.TemporaryDirectory() as temp:
            project = self.with_st(Path(temp),
                "(* forgot to close this one" + self.NL
                + "    Speed := 3;                 (* target speed *)" + self.NL)

            result = run_tool("validate-comment-balance", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SWALLOWED_CODE", result.stdout)
            self.assertIn("Speed := 3", result.stdout)

    def test_validate_comment_balance_flags_a_comment_left_open_at_the_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.with_st(Path(temp), "    Speed := 3;" + self.NL + "(* trailing prose" + self.NL)

            result = run_tool("validate-comment-balance", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("UNCLOSED", result.stdout)

    MODBUS_PORT = (
        '<HARDWARE_DEVICE_DOWNLINK_PORT ID="20" NAME="ETH1" PROTOCOL="2" MODE="1">'
        "{quotes}"
        '<HARDWARE_PROPERTY ID="TCP_LOCAL_PORT" VALUE="502" />'
        "</HARDWARE_DEVICE_DOWNLINK_PORT>"
    )

    def make_modbus_project(self, folder: Path, windows, quoted=None, extra_vars: str = "") -> Path:
        """Fixture plus a Modbus TCP server port quoting the given windows.

        ``windows`` is a list of (name, start, end, [tag, ...]); OFFSET is
        assigned by position, which is how a generator naturally writes it and
        exactly how the address clash arises.
        """
        project = self.make_project(folder)
        raw = project.read_text(encoding="gbk", newline="")
        body = "".join(
            '<HARDWARE_MODBUS_MAPPING NAME="{}" START_ADDR="{}" END_ADDR="{}">{}</HARDWARE_MODBUS_MAPPING>'.format(
                name, start, end,
                "".join('<HARDWARE_MODBUS_TAG_MAPPING OFFSET="{}" TAG_NAME="{}"/>'.format(i, tag)
                        for i, tag in enumerate(tags)))
            for name, start, end, tags in windows)
        raw = raw.replace("<TAGCONFIG/>", "<TAGCONFIG>" + body + "</TAGCONFIG>")
        names = [w[0] for w in windows] if quoted is None else quoted
        quotes = "".join('<HARDWARE_MODBUS_MAPPING_QUOTE NAME="{}"/>'.format(n) for n in names)
        raw = raw.replace("</HARDWARE>", self.MODBUS_PORT.format(quotes=quotes) + "</HARDWARE>")
        if extra_vars:
            raw = raw.replace("</GLOBAL_TAG_CONFIG>", extra_vars + "</GLOBAL_TAG_CONFIG>")
        project.write_text(raw, encoding="gbk", newline="")
        return project

    def test_validate_modbus_mapping_accepts_matching_widths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_modbus_project(Path(temp), [
                ("MODBUS_10001_10016_0", 10001, 10016, ["SystemReady"]),
                ("MODBUS_30001_30016_0", 30001, 30016, ["StatusWords[0]", "StatusWords[1]"]),
            ])

            result = run_tool("validate-modbus-mapping", "--project", str(project))

            self.assertIn("MODBUS_MAPPING=OK", result.stdout)
            self.assertIn("Windows=2", result.stdout)

    def test_validate_modbus_mapping_flags_a_wide_tag_in_a_bit_space(self) -> None:
        # A discrete-input address is one bit, so a 16-bit tag eats sixteen of
        # them and every OFFSET after it is wrong.  The compiler rejects the
        # project with 位号地址存在重叠 and names the window, not the tag --
        # verified on 5.1.0 with a BYTE in this position.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_modbus_project(Path(temp), [
                ("MODBUS_10001_10064_0", 10001, 10064,
                 ["StatusWords[0]", "SystemReady"]),
            ])

            result = run_tool("validate-modbus-mapping", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TOO_WIDE", result.stdout)
            # The tag after it is the one whose address actually collides.
            self.assertIn("OFFSET_CLASH", result.stdout)
            self.assertIn("expected OFFSET 16", result.stdout)

    def test_validate_modbus_mapping_flags_a_wide_tag_in_a_register_space(self) -> None:
        # A 32-bit value needs two registers and nothing in the files says
        # whether the next OFFSET then steps by one or by two, so it is refused
        # rather than guessed at.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_modbus_project(
                Path(temp),
                [("MODBUS_30001_30016_0", 30001, 30016, ["Odometer"])],
                extra_vars='<VARIABLE NAME="Odometer" DATATYPE="UDINT" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />',
            )

            result = run_tool("validate-modbus-mapping", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TOO_WIDE", result.stdout)
            self.assertIn("UDINT", result.stdout)

    def test_validate_modbus_mapping_flags_a_one_byte_tag_in_a_register_space(self) -> None:
        # Compile error 0x22D: 变量长度小于 2 字节或不是偶数字节，无法关联寄存器
        # 地址.  A register is two bytes, so BOOL/BYTE/SINT need an INT copy --
        # the same DISP-style copy that wide types need, for the opposite reason.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_modbus_project(
                Path(temp),
                [("MODBUS_30001_30016_0", 30001, 30016, ["StateCode"])],
                extra_vars='<VARIABLE NAME="StateCode" DATATYPE="BYTE" DESC="" INIT_VALUE="0" READONLY="NO" VISIBLE="YES" />',
            )

            result = run_tool("validate-modbus-mapping", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TOO_NARROW", result.stdout)
            self.assertIn("0x22D", result.stdout)

    def test_validate_modbus_mapping_flags_a_quote_with_no_window(self) -> None:
        # The port carries only the name; the window lives under TAGCONFIG.
        # Clobber the window and the file is still well-formed XML, every tool
        # still reports success, and the mapping is simply not there.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_modbus_project(
                Path(temp),
                [("MODBUS_10001_10016_0", 10001, 10016, ["SystemReady"])],
                quoted=["MODBUS_10001_10016_0", "MODBUS_30001_30192_0"],
            )

            result = run_tool("validate-modbus-mapping", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WINDOW_MISSING", result.stdout)
            self.assertIn("MODBUS_30001_30192_0", result.stdout)

    def test_validate_modbus_mapping_flags_a_window_wider_than_its_span(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_modbus_project(Path(temp), [
                ("MODBUS_30001_30002_0", 30001, 30002,
                 ["StatusWords[0]", "StatusWords[1]", "StatusWords[0]"]),
            ])

            result = run_tool("validate-modbus-mapping", "--project", str(project), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WINDOW_TOO_SMALL", result.stdout)

    def test_set_attrs_routes_a_port_property_to_its_child_element(self) -> None:
        # A port keeps its baud rate in <HARDWARE_PROPERTY ID="CAN_BAUD" VALUE=..>,
        # not on its own start tag.  Writing it onto the tag passes every
        # text-level check and leaves the controller on the old rate, so the
        # value has to land on the child element (verified on hardware
        #).
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "downlink-port",
                              "--port-id", "5", "--attr", "CAN_BAUD=0x02", "--no-backup")

            self.assertIn("downlink-port:5:CAN_BAUD", result.stdout)
            raw = project.read_text(encoding="gbk", newline="")
            self.assertIn('<HARDWARE_PROPERTY ID="CAN_BAUD" VALUE="0x02" />', raw)
            port_tag = raw[raw.index('<HARDWARE_DEVICE_DOWNLINK_PORT ID="5"'):]
            port_tag = port_tag[:port_tag.index(">")]
            self.assertNotIn("CAN_BAUD", port_tag)

    def test_set_attrs_still_writes_a_real_port_attribute_onto_the_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "downlink-port",
                              "--port-id", "5", "--attr", "DISPLAY=CAN-A", "--no-backup")

            self.assertIn("downlink-port:5", result.stdout)
            raw = project.read_text(encoding="gbk", newline="")
            port_tag = raw[raw.index('<HARDWARE_DEVICE_DOWNLINK_PORT ID="5"'):]
            port_tag = port_tag[:port_tag.index(">")]
            self.assertIn('DISPLAY="CAN-A"', port_tag)

    def test_set_attrs_refuses_to_mix_a_port_property_with_a_tag_attribute(self) -> None:
        # The two live in different elements; one call cannot patch both.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "downlink-port",
                              "--port-id", "5", "--attr", "CAN_BAUD=0x02", "--attr", "DISPLAY=CAN-A",
                              "--no-backup", check=False)

            self.assertNotEqual(result.returncode, 0)
            raw = project.read_text(encoding="gbk", newline="")
            self.assertIn('VALUE="0x04"', raw)

    def test_set_attrs_routes_a_com_cmd_property_to_its_child_element(self) -> None:
        # A Modbus master command keeps its first register in
        # <HARDWARE_PROPERTY ID="COM_CMD_START_ADDR" VALUE=..>, the same way a
        # port keeps its baud rate.  Writing it onto the HARDWARE_COM_CMD start
        # tag passes every text-level check and polls the old register.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "com-cmd",
                              "--cmd-id", "251", "--attr", "COM_CMD_START_ADDR=2", "--no-backup")

            self.assertIn("com-cmd:251:COM_CMD_START_ADDR", result.stdout)
            raw = project.read_text(encoding="gbk", newline="")
            self.assertIn('<HARDWARE_PROPERTY ID="COM_CMD_START_ADDR" VALUE="2" />', raw)
            cmd_tag = raw[raw.index('<HARDWARE_COM_CMD '):]
            cmd_tag = cmd_tag[:cmd_tag.index(">")]
            self.assertNotIn("COM_CMD_START_ADDR", cmd_tag)

    def test_set_attrs_still_writes_a_real_com_cmd_attribute_onto_the_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "com-cmd",
                              "--cmd-id", "251", "--attr", "DEV_TYPE=1", "--no-backup")

            self.assertIn("com-cmd:251", result.stdout)
            raw = project.read_text(encoding="gbk", newline="")
            cmd_tag = raw[raw.index('<HARDWARE_COM_CMD '):]
            cmd_tag = cmd_tag[:cmd_tag.index(">")]
            self.assertIn('DEV_TYPE="1"', cmd_tag)

    def test_set_attrs_refuses_to_mix_a_com_cmd_property_with_a_tag_attribute(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "com-cmd",
                              "--cmd-id", "251", "--attr", "COM_CMD_FC=4", "--attr", "DEV_TYPE=1",
                              "--no-backup", check=False)

            self.assertNotEqual(result.returncode, 0)
            raw = project.read_text(encoding="gbk", newline="")
            self.assertIn('<HARDWARE_PROPERTY ID="COM_CMD_FC" VALUE="3" />', raw)

    def test_alloc_canopen_command_ids_fills_enabled_groups_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            raw = project.read_text(encoding="gbk", newline="")
            raw = raw.replace(
                '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="NO"',
                '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="YES"')
            project.write_text(raw, encoding="gbk", newline="")

            result = run_tool("alloc-canopen-command-ids", "--project", str(project),
                              "--no-backup", check=False)

            self.assertIn("Assigned=1", result.stdout)
            patched = project.read_text(encoding="gbk", newline="")
            rpdo = patched.index('HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1"')
            tpdo = patched.index('HARDWARE_CMD_TAG_NAME="Axis1_XCS_TPDO1"')
            self.assertIn('<HARDWARE_CAN_CMD ID="1">', patched[rpdo:tpdo])
            # the still-disabled group keeps its "0"
            self.assertIn('<HARDWARE_CAN_CMD ID="0">', patched[tpdo:])
            self.assertIn("CANOPEN_COMMAND_IDS=OK",
                          run_tool("validate-canopen-command-ids", "--project", str(project)).stdout)

    def test_alloc_canopen_command_ids_never_reuses_a_taken_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            raw = project.read_text(encoding="gbk", newline="")
            raw = raw.replace('<HARDWARE_CAN_CMD ID="cmd1">', '<HARDWARE_CAN_CMD ID="1">')
            raw = raw.replace(
                '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="NO"',
                '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1" HARDWARE_GROUP_ENABLE="YES"')
            project.write_text(raw, encoding="gbk", newline="")

            result = run_tool("alloc-canopen-command-ids", "--project", str(project),
                              "--no-backup", "--format", "json", check=False)

            self.assertIn('"cmd_id": 2', result.stdout)

    def test_rename_hardware_tag_moves_members_and_command_group_together(self) -> None:
        # ST addresses the members (`Tag[0]`), not the tag, and the command group
        # finds its tag by name.  A rename that moves only the start tag leaves a
        # project that parses and compiles but whose references resolve nowhere.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            run_tool("rename-hardware-tag", "--project", str(project),
                     "--old", "Axis1_Position_6004", "--new", "Motor9_Position_6004",
                     "--no-backup")

            raw = project.read_text(encoding="gbk", newline="")
            self.assertNotIn("Axis1_Position_6004", raw)
            self.assertIn('NAME="Motor9_Position_6004"', raw)
            self.assertIn('NAME="Motor9_Position_6004[0]"', raw)
            self.assertIn('NAME="Motor9_Position_6004[3]"', raw)
            self.assertIn('HARDWARE_CMD_TAG_NAME="Motor9_Position_6004"', raw)

    def test_rename_hardware_tag_refuses_an_occupied_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            before = project.read_bytes()

            result = run_tool("rename-hardware-tag", "--project", str(project),
                              "--old", "Axis1_Position_6004",
                              "--new", "Axis1_XCS_RPDO1", "--no-backup", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(project.read_bytes(), before)

    def test_set_attrs_refuses_to_rename_a_hardware_tag(self) -> None:
        # The safe path is rename-hardware-tag; set-attrs would touch the start
        # tag alone and silently orphan every member.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            before = project.read_bytes()

            result = run_tool("set-attrs", "--project", str(project),
                              "--kind", "hardware-tag", "--name", "Axis1_Position_6004",
                              "--attr", "NAME=Whatever", "--no-backup", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("rename-hardware-tag", result.stderr)
            self.assertEqual(project.read_bytes(), before)

    def test_set_attrs_can_enable_a_canopen_command_group(self) -> None:
        # A CANopen object goes live only when both halves are on: the channel
        # tag and the command group that transmits it.  Before `cmd-group`
        # existed there was no way to reach the group without hand-editing XML,
        # and enabling just the tag yields a variable that never moves.
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = self.make_project(temp_path)

            run_tool(
                "set-attrs", "--project", str(project),
                "--kind", "cmd-group", "--name", "Axis1_XCS_RPDO1",
                "--attr", "HARDWARE_GROUP_ENABLE=YES",
                "--attr", "MODE=1",
                "--no-backup",
            )

            raw = project.read_text(encoding="gbk", newline="")
            group = re.search(
                r'<HARDWARE_CAN_CMD_GROUP [^>]*HARDWARE_CMD_TAG_NAME="Axis1_XCS_RPDO1"[^>]*>', raw)
            self.assertIsNotNone(group)
            self.assertIn('HARDWARE_GROUP_ENABLE="YES"', group.group(0))
            self.assertIn('MODE="1"', group.group(0))
            # The other group must be untouched.
            other = re.search(
                r'<HARDWARE_CAN_CMD_GROUP [^>]*HARDWARE_CMD_TAG_NAME="Axis1_Position_6004"[^>]*>', raw)
            self.assertNotIn('MODE="1"', other.group(0))

    def test_set_attrs_refuses_partial_node_id_write(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            project = self.make_project(Path(folder))

            result = run_tool("set-attrs", "--project", str(project), "--kind", "station",
                              "--port-id", "5", "--address", "1", "--attr", "ADDRESS=9",
                              "--no-backup", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("set-node-id", result.stdout + result.stderr)
            self.assertIn('NODE_ID="1"', project.read_text(encoding="gbk", newline=""))

    def test_validate_controller_support_skips_without_install_dir(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_project(root)
            missing = root / "no-such-install"

            result = run_tool("validate-controller-support", "--project", str(project),
                              "--install-dir", str(missing))

            self.assertIn("Controller=IVC300", result.stdout)
            self.assertIn("ChassisDriverType=23", result.stdout)
            self.assertIn("CONTROLLER_SUPPORT=SKIP", result.stdout)

    def test_released_command_ids_are_not_duplicates(self) -> None:
        """xRobotDesigner resets a disabled command id to "0"; that is not an id."""
        with tempfile.TemporaryDirectory() as folder:
            project = self.make_project(Path(folder))

            result = run_tool("validate-canopen-command-ids", "--project", str(project))

            self.assertIn("CANOPEN_COMMAND_IDS=OK", result.stdout)
            self.assertNotIn("DuplicateRows", result.stdout)

    def test_unencodable_character_leaves_project_untouched(self) -> None:
        """A character outside the project encoding must fail before any write."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_project(root)
            before = project.read_bytes()
            st = root / "bad.st"
            st.write_text("(* 直径 Ø450 *)", encoding="utf-8", newline="")

            result = run_tool("replace-st", "--project", str(project),
                              "--pou-type", "program", "--name", "MainProgram",
                              "--st-file", str(st), "--st-encoding", "utf-8",
                              "--no-backup", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot encode", result.stdout + result.stderr)
            self.assertEqual(project.read_bytes(), before)

    def test_write_leaves_no_temporary_file_behind(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_project(root)
            st = root / "ok.st"
            st.write_text("(* 正常注释 *)", encoding="utf-8", newline="")

            run_tool("replace-st", "--project", str(project),
                     "--pou-type", "program", "--name", "MainProgram",
                     "--st-file", str(st), "--st-encoding", "utf-8", "--no-backup")

            leftovers = [f.name for f in root.iterdir() if ".tmp_" in f.name]
            self.assertEqual(leftovers, [])

    def test_command_directions_pass_when_every_output_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            result = run_tool("validate-command-directions", "--project", str(project))
            self.assertIn("COMMAND_DIRECTIONS=OK", result.stdout)

    def test_enabled_output_command_no_program_writes_is_reported(self) -> None:
        # An output command sends the tag's contents to the device on schedule.
        # With nothing writing the tag the device is fed zeros forever, and code
        # that parses the same tag reads its own buffer instead of the device --
        # the project compiles clean either way.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_Position_6004" HARDWARE_GROUP_ENABLE="YES" INDEX_ID="24580" SUB_INDEX_ID="0" CMD_ACCESS_TYPE="ro"',
                    '<HARDWARE_CAN_CMD_GROUP HARDWARE_CMD_TAG_NAME="Axis1_Position_6004" HARDWARE_GROUP_ENABLE="YES" INDEX_ID="24580" SUB_INDEX_ID="0" EDTYPE="0" CMD_ACCESS_TYPE="rw"',
                ),
                encoding="gbk",
            )

            result = run_tool("validate-command-directions", "--project", str(project), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("COMMAND_DIRECTIONS=FAIL", result.stdout)
            self.assertIn("OutputNeverWrittenByST=1", result.stdout)
            self.assertIn("Axis1_Position_6004", result.stdout)

    def test_program_writing_an_input_command_tag_is_reported(self) -> None:
        # The mirror case: the master overwrites the tag on every poll, so the
        # program's write silently disappears.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    'CONTENT="FB_SCALE(InValue:=1, Scale=&gt;StatusWords[0]);"',
                    'CONTENT="Axis1_Position_6004[0] := 0;"',
                ).replace(
                    'CONTENT="FB_SCALE(InValue:=1, Scale=>StatusWords[0]);"',
                    'CONTENT="Axis1_Position_6004[0] := 0;"',
                ),
                encoding="gbk",
            )

            result = run_tool("validate-command-directions", "--project", str(project), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("InputOverwrittenByST=1", result.stdout)

    def test_fb_calls_pass_when_argument_order_matches_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            result = run_tool("validate-fb-calls", "--project", str(project))
            self.assertIn("FB_CALLS=OK", result.stdout)

    def test_fb_call_with_extra_pin_before_declared_one_is_reported(self) -> None:
        # Kecon ST calls read like named arguments, so the order looks optional.
        # It is not: inputs must follow SECTION_VAR_INPUT order and outputs
        # SECTION_VAR_OUTPUT order. Getting it wrong fails the build with one
        # FBDError per call site, carrying no line number and naming no pin --
        # which is exactly why this is worth catching here instead.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    '<SECTION_VAR_INPUT NAME="InValue" DATATYPE="INT" DESC="input value" INIT_VALUE="" VISIBLE="YES" />',
                    '<SECTION_VAR_INPUT NAME="Gain" DATATYPE="INT" DESC="gain" INIT_VALUE="" VISIBLE="YES" />'
                    '<SECTION_VAR_INPUT NAME="InValue" DATATYPE="INT" DESC="input value" INIT_VALUE="" VISIBLE="YES" />',
                ).replace(
                    'CONTENT="FB_SCALE(InValue:=1, Scale=&gt;StatusWords[0]);"',
                    'CONTENT="FB_SCALE(InValue:=1, Gain:=2, Scale=&gt;StatusWords[0]);"',
                ).replace(
                    'CONTENT="FB_SCALE(InValue:=1, Scale=>StatusWords[0]);"',
                    'CONTENT="FB_SCALE(InValue:=1, Gain:=2, Scale=>StatusWords[0]);"',
                ),
                encoding="gbk",
            )

            result = run_tool("validate-fb-calls", "--project", str(project), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FB_CALLS=FAIL", result.stdout)
            self.assertIn("FB_SCALE", result.stdout)
            self.assertIn("input order is InValue,Gain", result.stdout)

    def test_fb_call_naming_an_undeclared_pin_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    'CONTENT="FB_SCALE(InValue:=1, Scale=&gt;StatusWords[0]);"',
                    'CONTENT="FB_SCALE(InValue:=1, Typo:=2, Scale=&gt;StatusWords[0]);"',
                ).replace(
                    'CONTENT="FB_SCALE(InValue:=1, Scale=>StatusWords[0]);"',
                    'CONTENT="FB_SCALE(InValue:=1, Typo:=2, Scale=>StatusWords[0]);"',
                ),
                encoding="gbk",
            )

            result = run_tool("validate-fb-calls", "--project", str(project), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("pin not declared: Typo", result.stdout)

    def test_added_struct_array_member_is_expanded_per_element(self) -> None:
        # The GUI writes an array member of a user data type as a parent with one
        # child per element, and both official sample projects do the same. A
        # flat self-closing member declares the same type and still compiles,
        # but the editor counts and lays out members per element, so its member
        # list and offset column would disagree with the declaration.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            run_tool(
                "add-user-struct-member", "--project", str(project),
                "--struct", "DriveStatus", "--member", "Flags:BOOL[4]:bit flags",
                "--no-backup",
            )
            text = project.read_text(encoding="gbk")
            self.assertIn('DATATYPE="BOOL[4]"', text)
            for i in range(4):
                self.assertIn(f'NAME="Flags[{i}]"', text)

    def test_flat_struct_array_member_is_reported_and_rebuildable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    "</USER_STRUCT>",
                    '<USER_STRUCT_MEMBER DATATYPE="BOOL[4]" DESC="" INIT_VALUE="" NAME="Flat" VISIBLE="YES"/>'
                    "</USER_STRUCT>",
                    1,
                ),
                encoding="gbk",
            )

            # validate-datatypes only fails the run under --strict
            result = run_tool("validate-datatypes", "--project", str(project), "--strict", check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ARRAY_NOT_EXPANDED", result.stdout)

            run_tool("rebuild-user-struct-members", "--project", str(project), "--no-backup")
            self.assertIn('NAME="Flat[3]"', project.read_text(encoding="gbk"))
            run_tool("validate-datatypes", "--project", str(project), "--strict")

    def test_rebuild_user_struct_members_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            run_tool(
                "add-user-struct-member", "--project", str(project),
                "--struct", "DriveStatus", "--member", "Flags:BOOL[4]:bit flags",
                "--no-backup",
            )
            before = project.read_bytes()
            result = run_tool("rebuild-user-struct-members", "--project", str(project), "--no-backup")
            self.assertIn("RebuiltUserStructMembers=0", result.stdout)
            self.assertEqual(before, project.read_bytes())

    def test_resources_reports_missing_install_dir_without_crashing(self) -> None:
        # A machine without xRobotDesigner installed must still get a readable
        # report saying what was not found, not a traceback.
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "kecon-resources.json"
            config.write_text(
                json.dumps({"install_dir": str(Path(temp) / "nowhere"), "sample_projects": []}),
                encoding="utf-8",
            )
            result = run_tool("resources", "--config", str(config), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("InstallDir=NOT FOUND", result.stdout)
            self.assertIn("WARNING", result.stdout)

    def test_resources_reads_paths_from_a_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Minimal fake install: Resource/chs/history/1.2.3/FBLib/MRC with one block.
            lib = root / "install" / "Resource" / "chs" / "history" / "1.2.3" / "FBLib" / "MRC"
            lib.mkdir(parents=True)
            (lib / "Math.xml").write_text(
                '<?xml version="1.0" encoding="UTF-8"?><FBs>'
                '<FB id="0x1" name="DEMO_ADD" desc="demo" type="FC">'
                '<INPUT><PIN name="X" datatype="INT" desc=""/><PIN name="Y" datatype="INT" desc=""/></INPUT>'
                '<OUTPUT><PIN name="Q" datatype="INT" desc=""/></OUTPUT>'
                "</FB></FBs>",
                encoding="utf-8",
            )
            samples = root / "samples"
            samples.mkdir()
            (samples / "demo.xcskr").write_text(FIXTURE_XML, encoding="gbk")

            config = root / "kecon-resources.json"
            config.write_text(
                json.dumps({
                    "install_dir": str(root / "install"),
                    "lang": "chs",
                    "version": "latest",
                    "sample_projects": [str(samples)],
                }),
                encoding="utf-8",
            )

            result = run_tool("resources", "--config", str(config))
            self.assertIn("(from config)", result.stdout)
            self.assertIn("VersionsInstalled=1.2.3", result.stdout)
            self.assertIn("FunctionBlocks=1", result.stdout)
            self.assertIn("SampleProjects=1", result.stdout)
            self.assertIn("demo.xcskr", result.stdout)

    def test_resource_flag_beats_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for version in ("1.0.0", "2.0.0"):
                lib = root / "install" / "Resource" / "chs" / "history" / version / "FBLib" / "MRC"
                lib.mkdir(parents=True)
                (lib / "Math.xml").write_text("<FBs></FBs>", encoding="utf-8")
            config = root / "kecon-resources.json"
            config.write_text(
                json.dumps({"install_dir": str(root / "install"), "lang": "chs", "version": "latest"}),
                encoding="utf-8",
            )

            latest = run_tool("resources", "--config", str(config))
            self.assertIn("2.0.0", latest.stdout.split("FunctionBlockLib=")[1].splitlines()[0])

            pinned = run_tool("resources", "--config", str(config), "--version", "1.0.0")
            self.assertIn("Version=1.0.0 (from flag)", pinned.stdout)
            self.assertIn("1.0.0", pinned.stdout.split("FunctionBlockLib=")[1].splitlines()[0])

    def test_hardware_bindings_pass_on_a_consistent_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            result = run_tool("validate-hardware-bindings", "--project", str(project))
            self.assertIn("HARDWARE_BINDINGS=OK", result.stdout)

    def test_renaming_a_channel_tag_alone_is_reported_as_dangling(self) -> None:
        # Renaming HARDWARE_CHANNEL_TAG@NAME without the command group that feeds it
        # leaves the object polled on the bus but written nowhere, and the project
        # still compiles -- exactly the silent failure this check exists for.
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    '<HARDWARE_CHANNEL_TAG NAME="Axis1_Position_6004"',
                    '<HARDWARE_CHANNEL_TAG NAME="Motor1_Position_6004"',
                ),
                encoding="gbk",
            )

            result = run_tool("validate-hardware-bindings", "--project", str(project), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("HARDWARE_BINDINGS=FAIL", result.stdout)
            self.assertIn("DanglingBindings=1", result.stdout)
            self.assertIn("Axis1_Position_6004", result.stdout)

    def test_enabled_group_pointing_at_a_disabled_tag_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace(
                    '<HARDWARE_CHANNEL_TAG NAME="Axis1_Position_6004" DATATYPE="BYTE[4]" DESC="axis position" ENABLE="YES"',
                    '<HARDWARE_CHANNEL_TAG NAME="Axis1_Position_6004" DATATYPE="BYTE[4]" DESC="axis position" ENABLE="NO"',
                ),
                encoding="gbk",
            )

            result = run_tool("validate-hardware-bindings", "--project", str(project), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("EnabledGroupWithDisabledTag=1", result.stdout)

    def test_desc_within_the_limit_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))

            result = run_tool("validate-desc-length", "--project", str(project))

            self.assertIn("Problems=0", result.stdout)
            self.assertIn("OverBytes=0", result.stdout)

    def test_desc_longer_than_the_limit_is_a_problem(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace('DESC="system ready flag"', 'DESC="%s"' % ("x" * 129)),
                encoding="gbk",
            )

            result = run_tool("validate-desc-length", "--project", str(project), "--strict", check=False)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Problems=1", result.stdout)
            self.assertIn("TOO_LONG", result.stdout)
            self.assertIn("SystemReady", result.stdout)

    def test_desc_over_the_limit_only_in_gbk_bytes_is_a_warning(self) -> None:
        """CJK doubles in GBK, so 100 characters can be 180 bytes on disk.

        Whether the GUI counts characters or bytes is unverified, so this
        stays a warning: it must not fail --strict, but it must be visible.
        """
        with tempfile.TemporaryDirectory() as temp:
            project = self.make_project(Path(temp))
            text = project.read_text(encoding="gbk")
            project.write_text(
                text.replace('DESC="system ready flag"', 'DESC="%s"' % ("中" * 100)),
                encoding="gbk",
            )

            result = run_tool("validate-desc-length", "--project", str(project), "--strict")

            self.assertEqual(result.returncode, 0)
            self.assertIn("Problems=0", result.stdout)
            self.assertIn("OverBytes=1", result.stdout)
            self.assertIn("OVER_BYTES", result.stdout)

    def test_cli_help_is_generic(self) -> None:
        result = run_tool("--help")

        self.assertIn("export-ai", result.stdout)
        self.assertIn("set-attrs", result.stdout)
        self.assertNotIn("project-specific", result.stdout.lower())
        self.assertNotIn("gateway", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
