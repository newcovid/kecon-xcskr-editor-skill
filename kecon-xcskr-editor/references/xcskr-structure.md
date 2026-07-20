# Kecon `.xcskr` XML Structure Reference

## Contents

- Encoding and raw ST handling
- Control scheme and tasks
- POU and ST logic
- Variables and user data types
- Hardware configuration and hardware variables
- CANopen slave object dictionary
- Safe write model
- Verification checklist

## Encoding And Raw ST Handling

- Observed `.xcskr` files are GBK/ANSI XML. Use `Path.read_text(encoding='gbk')` and `Path.write_text(..., encoding='gbk')`.
- XML parsing is safe for structural inspection.
- Do not write the whole project back through ElementTree. `SECTION_LOGIC_ST CONTENT` may contain literal line breaks inside an XML attribute; XML serializers can normalize or flatten the visible ST code.
- Patch ST by replacing only the raw `SECTION_LOGIC_ST CONTENT` span. `xcskr_tool.py replace-st` does this.

## Control Scheme And Tasks

Typical program hierarchy:

```text
PROJECT
  HARDWARE
    HARDWARE_NET
      HARDWARE_DEVICE_UPLINK_PORT
        HARDWARE_ROBOT_CONTROLLER
          CONTROL_SCHEME
            MAIN_TASK
              PROGRAM
            EVENT_TASK
              TRIG_CONDITION
              PROGRAM
            CYCLE_TASK
              PROGRAM
```

Implications:

- A flat `PROGRAM` list loses task context.
- Main task, event task, and cycle task programs should be reviewed from `export-ai` `index.json` / `programs.json`.
- Event tasks can carry trigger configuration in `TRIG_CONDITION`.
- Cycle tasks may carry timing attributes such as `CYCLE_TIME` or project-version-specific equivalents.

## POU And ST Logic

- `PROGRAM` is a program POU.
- `FUNCTION_BLOCK` is a custom function block.
- `FUNCTION` is a function POU.
- ST is stored in `SECTION_LOGIC_ST` as the `CONTENT` attribute.
- Function block pins are stored as `SECTION_VAR_INPUT`, `SECTION_VAR_OUTPUT`, and `SECTION_VAR_INTERNAL`.
- A function block can have valid pins while its ST content is empty; inspect both interface and ST.
- Raw ST line breaks can be literal LF or `&#10;`; both forms can be valid.

## Variables And User Data Types

Common nodes:

```text
GLOBAL_TAG_CONFIG
  VARIABLE
    VARIABLE_MEMBER

USER_DATA_TYPE
  USER_STRUCT
    USER_STRUCT_MEMBER
```

Notes:

- `VARIABLE` nodes represent custom/global variables.
- `VARIABLE_MEMBER` nodes represent array or struct members under variables and hardware tags.
- `USER_STRUCT` / `USER_STRUCT_MEMBER` represent user-defined data types.
- Use `export-ai` for a compact view, and `set-attrs` for attribute changes such as `DESC`, `INIT_VALUE`, `VISIBLE`, or `READONLY`.

## Hardware Configuration And Hardware Variables

Common downlink structure:

```text
HARDWARE_DEVICE_DOWNLINK_PORT
  HARDWARE_NET
    HARDWARE_DEVICE_UPLINK_PORT
      HARDWARE_PROPERTY
      HARDWARE_CAN_DEVICE_MOTOR
        HARDWARE_CAN_DEVICE_SLAVE
          HARDWARE_CAN_CMD_GROUP
            HARDWARE_CAN_CMD
              HARDWARE_CHANNEL_TAG
```

Important fields:

- `HARDWARE_DEVICE_DOWNLINK_PORT`: `ID`, `NAME`, `DISPLAY`, `PHYSICAL_ID`, `PROTOCOL`, `TYPE`.
- `HARDWARE_DEVICE_UPLINK_PORT`: station address/name and device properties.
- `HARDWARE_CAN_DEVICE_SLAVE`: device name, node ID, communication checks.
- `HARDWARE_CAN_CMD_GROUP`: object index/subindex, access type, enable state, cycle time, output length.
- `HARDWARE_CHANNEL_TAG`: generated hardware variable name, datatype, enable state, description.

Guardrails:

- Hardware variables are `HARDWARE_CHANNEL_TAG`, not ordinary `VARIABLE`.
- Do not infer physical port from `NAME` alone; compare exported `id`, `display`, and `physical_id`.
- Non-empty `HARDWARE_CAN_CMD ID` values should be unique in the checked scope; use `validate-canopen-command-ids`.

## CANopen Slave Object Dictionary

Object dictionary entries typically appear under a CAN slave downlink port:

```text
HARDWARE_CAN_SLAVER_OBJECT
  INDEX="8192"
  DATATYPE="uint32"
  ARRAY_FLAG="YES"
  ARRAY_SIZE="2"
  PDO_INDEX="6656"
  PDO_DESC="Transmit PDO 1"
  HARDWARE_MODBUS_TAG_MAPPING OFFSET="0" TAG_NAME="Status[0]"
```

Notes:

- Index values are decimal in XML; `8192 = 0x2000`.
- `OFFSET="0"` corresponds to sub1 in observed mappings.
- `TAG_NAME` is the mapped PLC variable.
- `PDO_INDEX` is decimal; common PDO mapping object ranges are `0x1600..` for RPDO and `0x1A00..` for TPDO.
- PDO direction is from the slave perspective: RPDO/Receive means master writes to slave; TPDO/Transmit means slave sends data.
- Objects without `PDO_INDEX` can exist as non-cyclic/SDO-style data unless the target project proves otherwise.

## Safe Write Model

Prefer these operations:

- `replace-st`: replace only the target POU's raw ST `CONTENT`.
- `set-attrs`: patch only the selected XML start tag attributes.
- `copy-pou`: replace an existing POU raw block from a known reference project.

Avoid:

- Whole-file XML pretty printing.
- Broad search/replace across the full XML.
- Deleting hardware tags or command groups without proving logic and mappings no longer depend on them.

## Verification Checklist

After any edit:

- XML parses successfully.
- `export-ai` succeeds and the expected task/POU/variable/hardware entity appears.
- `validate-st-format --strict` passes or any warning is understood.
- `validate-canopen-command-ids` passes when CANopen master device command IDs were touched.
- The changed ST file has meaningful raw line breaks when it contains multiple statements.
- The user compiles/downloads in xRobotDesigner GUI and reports any errors; do not treat command-line compile as final validation.
