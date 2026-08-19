# Kecon `.xcskr` XML Structure Reference

## Contents

- Encoding and raw ST handling
- Control scheme and tasks
- POU and ST logic
- Graphical logic: LD and FBD
- Variables and user data types
- Hardware configuration and hardware variables
- CANopen slave object dictionary
- Safe write model
- Verification checklist

Facts marked *verified* were cross-checked against the official Kecon sample
projects shipped with the xRobotDesigner help material, not inferred from a
single project.

## Encoding And Raw ST Handling

- Observed `.xcskr` files are GBK/ANSI XML with no XML declaration. Use
  `Path.read_text(encoding='gbk', newline='')` and
  `Path.write_text(..., encoding='gbk', newline='')`.
- XML parsing is safe for structural inspection.
- Do not write the whole project back through ElementTree. `SECTION_LOGIC_ST CONTENT` may contain literal line breaks inside an XML attribute; XML serializers can normalize or flatten the visible ST code.
- Patch ST by replacing only the raw `SECTION_LOGIC_ST CONTENT` span. `xcskr_tool.py replace-st` does this.
- Attributes are written in alphabetical order, and self-closing tags carry no
  space before the slash. Generated XML reproduces both, and reads its
  indentation step from the target file rather than assuming four spaces.
- Observed projects use bare LF. Read and write must disable newline
  translation: on Windows the default would rewrite every line ending on save,
  changing tens of thousands of bytes and the literal line breaks stored inside
  ST attributes. Generated fragments follow the document's own line ending.
- ST line breaks inside `SECTION_LOGIC_ST CONTENT` appear as literal LF, `&#10;`,
  or `&#x0D;&#x0A;` with tabs as `&#x09;`, depending on the version that wrote
  the file. All three read back correctly, so a rewrite keeps the existing style
  instead of normalizing it.

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
- The help defines four kinds: main, cycle, event and startup, with priority
  startup > event > cycle > main. A higher priority task preempts a lower one.
  Only the first three appear in any observed project, so the startup task tag
  is unknown; task discovery therefore accepts any `*_TASK` element instead of
  matching a fixed list.
- A cycle task carries its period as `CYCLE` in milliseconds. `CYCLE_TIME` on a
  task has never been observed; the attribute of that name on
  `HARDWARE_CAN_CMD_GROUP` is a different thing.
- An event task holds exactly one program. It carries the GUI trigger label in
  `EVENT_NAME` and the machine-readable condition in a `TRIG_CONDITION` child,
  written after the program:

```text
EVENT_TASK DESC="" EVENT_NAME="DI0002 上升沿" ID="16"
  PROGRAM
  TRIG_CONDITION VAR="DI0002" EVENT_TRIGGER="0" ENABLE_UPLIMIT="NO"
                 LOWCOMPARE="-1" LOWLIMIT="" OPERATORCOMPARE="-1"
                 UPCOMPARE="-1" UPLIMIT=""
```

  The help lists seven trigger kinds in this order: rising edge, falling edge,
  either edge, ON, OFF, analog condition, EVENT function block. `EVENT_TRIGGER="0"`
  is confirmed to be the rising edge; the rest of the mapping follows that order
  and is inferred, so an event trigger is best configured in the GUI dialog and
  only adjusted from here.
- Programs execute in document order within a task, so the order of `PROGRAM`
  siblings is functional, not cosmetic. `move-program` reorders them safely.
- `PROGRAM` IDs are unique across the whole project, not per task (verified).

Attribute sets written by the GUI (verified):

| Node | Attributes |
|---|---|
| `PROGRAM` | `DESC ENABLE_PSWD ENABLE_SHOW ID LOGIC_LANG NAME` |
| `FUNCTION_BLOCK` | `DESC ENABLE_PSWD LOGIC_LANG NAME` (plus `SECTION_PSWD` when protected) |
| `SECTION_VAR_INPUT` / `_OUTPUT` / `_INTERNAL` | `DATATYPE DESC INIT_VALUE NAME`, plus `VISIBLE` from V5.1 on |
| `MAIN_TASK` | `DESC ID NAME` |
| `CYCLE_TASK` | `CYCLE DESC ID` |

Inside a `FUNCTION_BLOCK` the GUI writes the logic section first, then
`SECTION_VAR_INPUT`, `SECTION_VAR_INTERNAL`, `SECTION_VAR_OUTPUT`. Interface
variables carry the per-type default initial value: `OFF` for `BOOL`, `0` for
integer types, `0.000` for `REAL`.

## POU And ST Logic

- `PROGRAM` is a program POU.
- `FUNCTION_BLOCK` is a custom function block.
- `FUNCTION` is a function POU.
- `LOGIC_LANG` selects the notation: `0` LD, `1` FBD, `2` ST (verified: it always
  agrees with the logic section element actually present). Trust the section tag.
- ST is stored in `SECTION_LOGIC_ST` as the `CONTENT` attribute.
- Function block pins are stored as `SECTION_VAR_INPUT`, `SECTION_VAR_OUTPUT`, and `SECTION_VAR_INTERNAL`.
- A function block can have valid pins while its ST content is empty; inspect both interface and ST.
- Raw ST line breaks can be literal LF, `&#10;`, or `&#x0D;&#x0A;`; all three are valid and the writer keeps whichever is already there.

## Graphical Logic: LD And FBD

`SECTION_LOGIC_LD` and `SECTION_LOGIC_FBD` use the same child vocabulary, so one
reader and one writer cover both. See `ld-fbd-st.md` for the language-level view.

```text
PROGRAM | FUNCTION_BLOCK | FUNCTION
  SECTION_LOGIC_LD | SECTION_LOGIC_FBD
    CONTROL_LOGIC_COMMENT      free text box
    CONTROL_LOGIC_BLOCK        NAME TYPE RECT_POSITION DEACTIVE SHOWEN
      BLOCK_PIN_INPUT          NAME DATATYPE INIT_VALUE ENABLED NEGATED VISIBLE
        CONTROL_BLOCK_CONNECTION
      BLOCK_PIN_OUTPUT
        CONTROL_BLOCK_CONNECTION
    CONTROL_LOGIC_LINE         NAME LINE_POSITION FROM_POWERRAIL POSITION_TYPE
```

Verified facts:

- Child order written by the GUI is blocks first, then lines.
- `CONTROL_BLOCK_CONNECTION` is the only binding mechanism.
  `CONNECTION_TYPE="1"` means `CONNECTION_VALUE` is a variable, hardware tag or
  member path; `CONNECTION_TYPE="2"` means it is the `NAME` of a
  `CONTROL_LOGIC_LINE` in the same section. A wire is recorded twice, once on
  the source output pin and once on the target input pin.
- A pin with no `CONTROL_BLOCK_CONNECTION` child falls back to its own
  `INIT_VALUE` as a literal constant.
- The `CONNECTION_PIN` attribute seen on some V5.1 FBD pins is empty in every
  inspected project, including the official samples, and carries no binding.
  Do not write to it.
- `LINE_POSITION` is always three points, `x1,y1,x2,y2,x3,y3`; the middle point
  is the elbow. Per-pin row coordinates are not stored anywhere, so a generated
  polyline is an approximation and should be checked in the GUI.
- Line names are unique per section only; `_LINE0` may appear in many programs.
- Graphical logic is not limited to `PROGRAM`. `FUNCTION_BLOCK` POUs carry LD
  sections too, and pins inside them bind to that block's own `SECTION_VAR_*`
  names rather than to globals.
- A block `TYPE` implies a fixed pin list that the file format does not
  describe, which is why blocks are copied from a reference project rather than
  synthesized.

## Variables And User Data Types

Actual placement (verified):

```text
PROJECT
  FUNCTION_BLOCK_LIST          custom FUNCTION_BLOCK POUs
  GLOBAL_TAG_CONFIG            usually empty / self-closing
  HARDWARE
    HARDWARE_NET
      HARDWARE_DEVICE_UPLINK_PORT
        HARDWARE_ROBOT_CONTROLLER
          CONTROL_SCHEME ...
          TAGCONFIG            <-- user variables live HERE
            VARIABLE
              VARIABLE_MEMBER
  SYS_DATA_TYPE
  USER_DATA_TYPE               <-- user structs live HERE
    USER_STRUCT
      USER_STRUCT_MEMBER
```

Notes:

- User `VARIABLE` nodes sit under `TAGCONFIG`, **not** under `GLOBAL_TAG_CONFIG`.
  In the official samples 137 of 137 user variables are under `TAGCONFIG`, and
  `GLOBAL_TAG_CONFIG` is written as an empty self-closing element.
- `USER_DATA_TYPE`, `GLOBAL_TAG_CONFIG` and `FUNCTION_BLOCK_LIST` are often
  self-closing in a fresh project; a writer must expand them before adding a child.
- `VARIABLE_MEMBER` nodes represent array or struct members under variables and hardware tags.
- Variable names share one namespace with `HARDWARE_CHANNEL_TAG` names.

Attribute sets written by the GUI (verified):

| Node | Attributes |
|---|---|
| `VARIABLE` | `COLD_RETAIN DATATYPE DESC INIT_VALUE NAME READONLY SYSTEM_GENERATE VISIBLE` |
| `VARIABLE_MEMBER` | `COLD_RETAIN DATATYPE DESC INIT_VALUE NAME VISIBLE` |
| `USER_STRUCT` | `DESC NAME READONLY VISIBLE` |
| `USER_STRUCT_MEMBER` | `DATATYPE DESC INIT_VALUE NAME VISIBLE` |

`READONLY` on `VARIABLE_MEMBER` is version-dependent: the official samples never
write it, while some projects created by V5.1.1.9998-C write it on array element
members only, never on struct field members. `add-variable --member-readonly auto`
mirrors whatever the target project already does.

Member naming and datatypes:

- An array `T[N]` produces members `Name[0] .. Name[N-1]`, each with
  `DATATYPE="T"`, the element type rather than the array type.
- A struct produces members `Name.Field`, each with the field's own datatype.
- A struct array nests both: `Name[0]`, and under it `Name[0].Field`.

`INIT_VALUE` conventions: containers (arrays, structs) get an empty value; scalar
leaves usually get the type default the GUI offers, `OFF` for `BOOL`, `0` for
integer types, `0.000` for `REAL`. Both an empty value and the literal appear in
GUI-written files, so the tool writes empty unless `--element-init auto` or an
explicit literal is given.

Editing a `USER_STRUCT` does **not** update variables that already use it. Run
`rebuild-variable-members` for each dependent variable afterwards;
`validate-datatypes` compares the whole member tree recursively and reports the
drift, including members nested inside array elements.

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
- CANopen object datatypes (`uint8`, `int32`, ...) are a different namespace from
  the IEC datatypes used by `VARIABLE`; do not validate one against the other.

## Safe Write Model

Prefer these operations:

- `replace-st`: replace only the target POU's raw ST `CONTENT`.
- `set-attrs`: patch only the selected XML start tag attributes.
- `copy-pou`: replace an existing POU raw block from a known reference project.
- `add-user-struct`, `add-user-struct-member`, `add-variable`,
  `rebuild-variable-members`, `remove`: structured create and update of user data
  types and variables.
- `set-pin`, `connect-pins`, `disconnect-line`, `copy-block`: graphical edits
  that only touch the pins, connections, lines and blocks named on the command line.

Avoid:

- Whole-file XML pretty printing.
- Broad search/replace across the full XML.
- Deleting hardware tags or command groups without proving logic and mappings no longer depend on them.
- Writing a block or POU that the GUI did not create, since the pin list of a
  block `TYPE` is not described by the file.

## Verification Checklist

After any edit:

- XML parses successfully.
- `export-ai` succeeds and the expected task/POU/variable/hardware entity appears.
- `validate-st-format --strict` passes or any warning is understood.
- `validate-datatypes --strict` passes after any user data type or variable change.
- `export-graphic` shows the expected connection kinds after any graphical edit.
- `validate-canopen-command-ids` passes when CANopen master device command IDs were touched.
- The changed ST file has meaningful raw line breaks when it contains multiple statements.
- The user compiles/downloads in xRobotDesigner GUI and reports any errors; do not treat command-line compile as final validation.
