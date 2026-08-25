# Kecon `.xcskr` XML Structure Reference

## Contents

- Encoding and raw ST handling
- Control scheme and tasks
- POU and ST logic
- Graphical logic: LD and FBD
- Variables and user data types
- Hardware configuration and hardware variables
- Member offsets are computed, not stored -- BOOL takes a byte and members are aligned
- Array members of a user data type are written expanded
- Vendor reference resources, and why none of their paths are hard-coded
- Command group direction and send mode
- The vendor function block library is the authority on pin order
- Function block call argument order
- Changing a command group between input and output
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
- Attributes are written in alphabetical order. Generated XML reproduces that,
  and reads its indentation step from the target file rather than assuming four
  spaces.
- The space before a self-closing slash is **version-dependent, so copy it from
  the element being replaced rather than picking one** (verified 2026-08-21 by
  counting `SECTION_LOGIC_ST` in three projects). V5.1.1.9998-C writes `"/>`
  (23 of 23 in the IVC300 project); the V5.0 GUI-authored sample writes `" />`
  (6 of 6); a project edited by both versions is mixed (IVC200: 1 tight, 3
  loose). An earlier note here claimed there is never a space -- that was true
  of the one version then in front of us and is wrong in general. Both parse
  identically, but imposing one style rewrites elements nobody edited, which
  puts noise in every diff and stops an unchanged round trip from being
  byte-identical. `section_logic_self_closing_spacer` reads the existing style
  and `replace_section_logic_raw` reuses it.
- `SECTION_LOGIC_ST CONTENT` never holds a bare `>` in an observed project:
  845 occurrences of `&gt;` and zero bare `>` across IVC300, IVC200 and the
  official sample (counted 2026-08-21). A bare `>` is legal XML in an attribute
  value and parses fine, so a rewrite that escapes it changes nothing
  semantically -- but it is not what the GUI produces, and it is worth knowing
  before reading such a change in a diff as damage.
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
- An unbound pin is written self-closing (`<BLOCK_PIN_INPUT ... />`); a bound one
  is a paired element wrapping its `CONTROL_BLOCK_CONNECTION`. Binding therefore
  has to open the element and unbinding has to collapse it back, or the file
  drifts from the shape the GUI writes. Verified 2026-08-21 by binding and
  unbinding pins on both an LD and an FBD block and re-reading the result.
- How graph-like a graphical POU is varies enormously and the format has to
  cover both ends. Measured 2026-08-21: the official sample's `联动` holds 21
  blocks, 24 wires and 82 connections, and its `底盘` holds 70+ including
  `_LDELEMENT*` LD contacts (`NE_CONTACT`, `B_CONTACT`, `S_CONTACT`,
  `OPEN_CONTACT`, `CLOSE_CONTACT`, `EQ_CONTACT`); a production project's `底盘控制`
  holds exactly one vendor block (`EightDifferentialChassis`, 78 pins), zero
  wires and zero connections. A degenerate POU looks like a parameter table, but
  designing a text representation around that shape would not survive contact
  with a real diagram.

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

## Member offsets are computed, not stored -- BOOL takes a byte and members are aligned

*verified 2026-08-21 against offsets read out of the editor's user-data-type view.*

A `USER_STRUCT_MEMBER` carries no offset attribute. The editor computes the
offset column from the declared types, so `struct-layout` reproduces that
computation rather than reading it. Two rules drive it, and neither can be read
off the official type table:

**A BOOL occupies one byte, not one bit.** For a struct laid out REAL x5,
DINT x3, UINT x2, BOOL[16], BOOL[8], BOOL[8], the editor showed
`0x22 / 0x24 / 0x34 / 0x3C` for the last UINT and the three BOOL arrays. One
byte per BOOL predicts exactly those; bit packing would have predicted
`0x24 / 0x26 / 0x27`.

**Members are naturally aligned.** Each member starts on a multiple of its own
width, with padding inserted ahead of it. In a struct running BYTE x5, BOOL,
BOOL, UINT, BOOL x8, UINT, UINT, BYTE, DINT the editor placed that DINT at
`0x18`; straight packing would have placed it at `0x16`, so the two pad bytes
(before the first UINT, and before the DINT) are real. `struct-layout` reports
the pad in its own column, which makes the wasted bytes easy to see -- ordering
a struct widest-member-first removes most of them.

One piece is still *unverified*: the total size. The editor shows member offsets
but no struct total, so `struct-layout` rounds the end up to the widest member's
alignment (the usual rule that keeps an array of structs aligned) without
anything to check it against. Nothing in the tool depends on the total today.

## Array members of a user data type are written expanded

*verified 2026-08-20 -- against a member the user created in the GUI, and against
both official sample projects (4 array members, 4 expanded, 0 flat).*

Inside a `USER_STRUCT`, an array member is a parent element with one child per
element:

```xml
<USER_STRUCT_MEMBER DATATYPE="BOOL[8]" DESC="bit scratch" INIT_VALUE="" NAME="bMot" VISIBLE="YES">
    <USER_STRUCT_MEMBER DATATYPE="BOOL" DESC="" NAME="bMot[0]" VISIBLE="YES"/>
    ...
    <USER_STRUCT_MEMBER DATATYPE="BOOL" DESC="" NAME="bMot[7]" VISIBLE="YES"/>
</USER_STRUCT_MEMBER>
```

The children carry `DATATYPE`, `DESC`, `NAME`, `VISIBLE` and **no `INIT_VALUE`**;
the parent keeps its own `INIT_VALUE`. Attribute order is alphabetical and the
children are indented one step deeper than the parent.

A flat self-closing member declares the same type and **still compiles**, which
is why this is easy to get wrong and easy to miss. What breaks is the editor: the
GUI counts and lays out members per element -- the help states a user data type
holds at most 1024 members and gives "one array member with 1024 elements" as an
example of reaching that limit -- so a flat member makes the member list and the
offset column in the user-data-type editor disagree with the declared type, while
the variable instance tree (which is expanded) looks correct. That split is
exactly what a user reported before this was fixed.

Note the vendor's own `DataType/*.xml` libraries use a *different* schema
(`<Struct><Member datatype="REAL[3]"/></Struct>`) where arrays stay flat. That is
an import format, not the project format, and it does not set the convention here.

`validate-datatypes` reports a flat member as `ARRAY_NOT_EXPANDED` and
`rebuild-user-struct-members` fixes it; `add-user-struct-member` writes the
expanded shape directly. The variable-instance side is unaffected --
`rebuild-variable-members` already expanded `VARIABLE_MEMBER` trees correctly.

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

## Command group direction and send mode

*Verified 2026-08-20 by reading the GUI property panel for four objects in a
live IVC200 project and cross-checking the mapping against all 528 command
groups in that project — the correlation is exact, with no exceptions.*

A `HARDWARE_CAN_CMD_GROUP` carries two independent axes that are easy to
conflate. Neither is named after what the GUI shows.

| GUI field | XML attribute | Values |
|---|---|---|
| 输入命令 / 输出命令 (direction) | `EDTYPE` | `1` = 输入命令, master **reads** the slave into the tag; `0` **or the attribute missing** = 输出命令, master **writes** the tag to the slave |
| 发送方式 (send mode) | `MODE` | `0` = 周期 · `1` = 变化发布 · `2` = 初始化执行 · `3` = 变化加周期 |

The four send modes, from the GUI dropdown:

| `MODE` | GUI | Behaviour |
|---|---|---|
| `0` | 周期 | resend every `CYCLE_TIME` ms, forever |
| `1` | 变化发布 | send only when the tag value changes |
| `2` | 初始化执行 | send once when the station starts |
| `3` | 变化加周期 | send on change, and also on the cycle |

`2` and `3` were established by a controlled experiment on 2026-08-20: the two
objects the operator switched in the GUI (`0x1000` to 初始化执行, `0x1001` to
变化加周期) came back as `MODE="2"` and `MODE="3"` in the file, and no other
group in either project carried those values.

Picking a send mode for a write:

- A **one-shot parameter the program computes** (a heartbeat time, a preset)
  belongs on `1` 变化发布, not `2` 初始化执行: 初始化执行 fires when the station
  starts, which can be before the program has put the intended value in the tag,
  so it would transmit the power-on default instead.
- A **command signature** (`1010:01` "save") belongs on `1`, and the program
  must clear the buffer afterwards or the identical value never re-triggers.
- `0` 周期 on a write means the device is rewritten every cycle. For a
  configuration object that is silent enforcement rather than verification; for
  an EEPROM-backed object it is wear.

`CMD_ACCESS_TYPE` is the EDS access string (`ro` / `rw`), not a direction. It
correlates with `EDTYPE` only because an `ro` object cannot be an output.

Observed GUI readings behind the table:

| Object | GUI | `EDTYPE` | `MODE` |
|---|---|---|---|
| `1001` Error Register | 周期 · 输入命令 | 1 | 0 |
| `6000` Operating Parameters | 周期 · 输出命令 | 0 | 0 |
| `1017` Producer Heartbeat Time | 变化发布 · 输出命令 | 0 | 1 |
| `6003` Preset Value | 变化发布 · 输出命令 | 0 | 1 |
| `1000` Device Type | 初始化执行 · 输入命令 | 1 | 2 |
| `1001` Error Register | 变化加周期 · 输入命令 | 1 | 3 |

Consequences worth checking in any project:

- **An `rw` object you believe you are reading may be an output.** The tag then
  holds what the PLC sends, not what the device reports, and any code that
  parses it for diagnostics is reading its own buffer. Grep for enabled groups
  with `EDTYPE="0"` whose tag the program never writes: those send zeros
  forever.
- **`MODE="0"` on a write is a cyclic write.** For EEPROM-backed objects
  (`1010:01` store parameters is the classic one) that is device wear, not a
  one-shot command. Writes that represent commands belong on `MODE="1"`.
- **`MODE="1"` means the program must clear the buffer after the command
  lands**, otherwise writing the same value a second time produces no change
  and therefore no transmission — the command silently never repeats.

## Vendor reference resources, and why none of their paths are hard-coded

*verified 2026-08-20 on a 5.0.50.0 install.*

xRobotDesigner ships several reference libraries that beat inference every time.
They live under the install directory, they are **versioned**, and their paths
differ per machine and per install language, so the tool resolves them instead of
assuming them:

| Resource | Location | What it settles |
|---|---|---|
| Function block library | `Resource/<lang>/[history/<ver>/]FBLib/MRC/*.xml` | Authoritative pin names and order for 203 blocks |
| Data type library | `Resource/<lang>/[history/<ver>/]DataType/*.xml` | Vendor chassis/system struct definitions |
| Help file | `Resource/<lang>/HelpFile/xCSStudioHelpFile.chm` + a wizard PDF | Type widths, limits, GUI semantics |
| Hardware library | `Resource/<lang>/Hardware/...` | Controller capabilities, chassis support |
| Official sample projects | machine-specific, config only | GUI-authored ground truth for file shape |

Resolution order for every value is **CLI flag → environment variable → config
file → built-in probing**, implemented in `resolve_resources()`. Run

```powershell
python ... resources
```

to see what was found and which source each value came from; it is the first
thing to run on an unfamiliar machine. `--version` pins a library version so a
result can be reproduced later, and `--lang` picks the resource language.

The config file is `kecon-resources.json`, looked up as `KECON_CONFIG`, then
`./kecon-resources.json`, then `~/kecon-resources.json`, then the one beside the
skill. **It is git-ignored on purpose** -- these paths are per-machine and often
personal. `kecon-resources.example.json` is the committed template and documents
every key. Environment overrides: `KECON_INSTALL_DIR`, `KECON_LANG`,
`KECON_VERSION`, `KECON_FB_LIB_DIR`, `KECON_DATATYPE_DIR`, `KECON_SAMPLES_DIR`.

**Official sample projects are the strongest evidence available.** They are
authored entirely in the GUI, so whenever the tool has to reproduce something the
GUI writes -- an expanded array member, a command group direction, an attribute
set -- diffing against a sample settles it without guessing and without asking
the user to click through a dialog. Point `sample_projects` at wherever they are
on the machine and pass one to any read-only command with `--project`.

Unpacking the help file: `7z x xCSStudioHelpFile.chm -o<dir>` (a 7-Zip copy ships
inside the install directory). Topic pages are **GBK-encoded HTML**, so decode
them as GBK before searching -- a UTF-8 read silently finds nothing. The
`outline_*.htm` files carry the reference chapters; `outline_42` is the system
data type table (BOOL 1 bit, BYTE/SINT/USINT 8, WORD/INT/UINT 16,
DWORD/DINT/UDINT/REAL/TIME 32) and `outline_43` the user data type rules
(no nesting, at most 1024 members counted per array element, at most 128 types).

## The vendor function block library is the authority on pin order

*verified 2026-08-20 -- read straight from the installed library and cross-checked
against 74 compiling call sites in two projects.*

The blocks a project can call are described in XML under the install directory:

```
<install>/Resource/<lang>/FBLib/MRC/*.xml
<install>/Resource/<lang>/history/<version>/FBLib/MRC/*.xml
```

`<lang>` is `chs` on a Chinese install. The `history/<version>/` copies are what
actually existed on the machine this was written against; the un-versioned path
may be absent, so look in both. Files are grouped by topic -- `Math.xml`,
`Logic.xml`, `Timer_Counter.xml`, `Compare_Limit.xml`, `Control.xml`,
`System.xml`, `Safe.xml`, `MC.xml`, `Chassis.xml`, `Navi.xml`, `Commu.xml`,
`Dispatch.xml`, `AdvMath.xml`, `IO.xml` -- 203 blocks in the 5.0.50.0 library.

Each entry looks like:

```xml
<FB id="0x40d" name="BYTE2DINT" disp="BYTE2DINT" desc="BYTE合成DINT" type="FB">
    <INPUT>
        <PIN name="IN_HH" datatype="BYTE" desc=""/>
        <PIN name="IN_H"  datatype="BYTE" desc=""/>
        <PIN name="IN_L"  datatype="BYTE" desc=""/>
        <PIN name="IN_LL" datatype="BYTE" desc=""/>
    </INPUT>
    <OUTPUT>
        <PIN name="Q" datatype="DINT" default="0" desc=""/>
    </OUTPUT>
</FB>
```

`type` is `FB` (holds internal state) or `FC` (a pure function). A section may
instead carry `base_name` with `min`/`max` in place of explicit `PIN` children --
that is a variadic group such as `ADD`'s `X1..X32`, whose arguments are
positional and cannot be mis-ordered the way a named pin list can.

**Read this before writing any call.** The pin names are not guessable and the
order is not optional (see the next section). `validate-fb-calls` loads the
library automatically and checks every call site against it.

Conversion blocks are worth memorising, since CANopen data arrives as `BYTE[n]`:

| Block | Inputs, in order | Outputs, in order |
|---|---|---|
| `BYTE2UINT` / `BYTE2INT` | `IN_H, IN_L` | `Q` |
| `BYTE2UDINT` / `BYTE2DINT` / `BYTE2REAL` | `IN_HH, IN_H, IN_L, IN_LL` | `Q` |
| `UINT2BYTE` / `INT2BYTE` | `IN` | `Q_H, Q_L` |
| `UDINT2BYTE` / `DINT2BYTE` / `REAL2BYTE` | `IN` | `Q_HH, Q_H, Q_L, Q_LL` |
| `BYTE2BIT` | `IN` | `Q_0 … Q_7` |
| `BIT2BYTE` | `IN_0 … IN_7` | `Q` |

CANopen is little-endian, so the lowest array index feeds the `_LL` / `_L` pin.

Two library facts that are easy to get wrong from memory:

- **`MOD` exists.** It is an ordinary `FC` in `Math.xml` (`取余（Q=X%Y）`, inputs
  `X, Y`) and `IDXC MOD 2` compiles. An earlier note here treated `MOD` as
  unverified because it did not appear in the vendor sample code that happened
  to be on hand; the library settles it. Code already written to avoid `MOD` is
  still correct and does not need changing back.
- **There is no scan-time block and no scan-time system variable.** Nothing in
  the library reports the main task's cycle time, projects carry no
  `SYSTEM_GENERATE` variables at all, and `GET_SYSTIME` only resolves to
  seconds. A millisecond accumulator in a free-running main task therefore has
  to add a *nominal* scan time from configuration, or be driven from a
  fixed-period cycle task.

`System.xml` also carries the persistence blocks, which matter whenever
retentive variables are in question: `WriteUserDefParam` / `ReadUserDefParam`
(`CarID`, two encoder calibration values, and `UserVar1..UserVar32`, all `REAL`,
persisted by the controller) and `SysParmWrite` / `SysParmRead`
(`BUF: ARRAY` + `LEN: UINT`, with a `Q: BOOL` success flag). Either one lets a
project persist calibration without relying on a retentive variable at all.

## Function block call argument order

> Automated by `validate-fb-calls`, which resolves declarations from both the
> project's own `FUNCTION_BLOCK` entries and the vendor library described above.

*Verified 2026-08-20: reordering the declarations to match the call sites was
the only change made, and the project then compiled clean.*

Kecon ST calls a function block by type name with named arguments
(`FB(In=x, Out=>y)`). **Named arguments do not make order optional.** After
appending three inputs to a block's `SECTION_VAR_INPUT` list (`add-pou-var`
appends at the end) while the call sites listed them in the middle, the compiler
raised one error per call site:

```text
[程序:<program>][功能块:<FB>]:使用的功能块实例与库中定义不一致!请更新使用的功能块!
<FBDError controller="1" id="769" section="..." block="..." pin="" nParam="0" line="-1"/>
```

Every pin name matched and the counts matched; only the order differed. The
message is FBD wording ("update the block instance") and carries no line number,
so it does not point at the offending argument — take it as "the argument list
does not match the declaration".

**Rule: the call's input list and output list must be in
`SECTION_VAR_INPUT` / `SECTION_VAR_OUTPUT` declaration order.** After
`add-pou-var`, either append the new pins at the end of every call too, or move
the declarations to match the calls.

## Changing a command group between 输入命令 and 输出命令

*Refined 2026-08-20 against 80 groups converted in a second project.* The three
attributes below are what differ **when the group has been through the GUI's
direction dialog before**. A group the dialog never touched carries none of
`EDTYPE`, `MODE`, `READ_ONLY` or `CMD_LEVEL`; bringing such a group to the input
shape means adding all four, not just flipping `EDTYPE`. Attributes are stored in
alphabetical order, so an inserted one has to land in its alphabetical position to
match what the GUI would write.

The reliable way to obtain the target shape is to diff against a group the user
converted in the GUI: in one project everything except `EDTYPE` was identical
between a GUI-made 输入命令 SDO group and an 输出命令 one.

**Regex trap when patching these by hand:** `HARDWARE_CAN_CMD` is a *prefix* of
`HARDWARE_CAN_CMD_GROUP`, so `<HARDWARE_CAN_CMD[^>]*>` matches the group tag first
and silently writes the child's attribute onto the parent. Match the child as
`<HARDWARE_CAN_CMD[\s>]`. This cost a full rollback the first time it was hit.


*Verified 2026-08-20 by switching one object in the GUI and diffing against its
seven untouched siblings.*

Switching an enabled `rw` object from 输出命令 to 输入命令 writes exactly three
attributes and nothing else:

| Element | Attribute | 输出命令 | 输入命令 |
|---|---|---|---|
| `HARDWARE_CAN_CMD_GROUP` | `EDTYPE` | absent | `1` |
| | `READ_ONLY` | absent | `""` |
| `HARDWARE_CAN_CMD` | `CMD_LEVEL` | absent | `""` |

`CMD_ACCESS_TYPE` stays at the EDS value (`rw`), `MODE` and `CYCLE_TIME` are
untouched, and no command id is reallocated. That makes this one of the few
hardware transformations safe to replicate across sibling objects from a
GUI-made template: apply the three attributes, then assert the whole block is
byte-identical to the template once the station number and `ID` are normalized.

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
- `validate-hardware-bindings` passes when a command group or channel tag was touched.
- `validate-command-directions` was read after any direction or send-mode change; every
  remaining entry is a program not yet written rather than a misconfiguration.
- `validate-fb-calls` passes after any new or edited function block call.
- `validate-datatypes --strict` reports no `ARRAY_NOT_EXPANDED` after any user data type change.
- The changed ST file has meaningful raw line breaks when it contains multiple statements.
- The user compiles/downloads in xRobotDesigner GUI and reports any errors; do not treat command-line compile as final validation.


## Controller configuration and the configuration wizard

`HARDWARE_ROBOT_CONTROLLER` carries more than the control scheme and the downlink
ports. Four sibling elements hold what the configuration wizard produced, and they
decide whether the project compiles at all:

| Element | Contents |
|---|---|
| `GENERAL_CFG` | `CAR_DRIVER_TYPE` (the chassis id the compiler validates), `CAR_WHEEL_COUNT`, vehicle envelope, gear ratio, encoder resolution |
| `WIZARD_CONFIG` | model library identity: `CHASSIS_TYPE`, `CONTROLLER`, `PATH`, `SUPPORT_CORE_BLOCK`, `FIRMWARE_VERSION`; contains the `WIZARD_DEVICE` / `WIZARD_DEVICE_PARAM` / `WIZARD_DEVICE_PARAM_OPTION` tree |
| `WHEEL_CFG` | one element per wheel group; `CAR_WHEEL_X_POS` longitudinal, `CAR_WHEEL_Y_POS` lateral, both in millimetres |
| `NAVI_CFG` | which navigation modes the project claims |

The installation carries the matching capability tables:

- `Resource/<lang>/Hardware/Common/MRCSeries.xml` — per controller model, the list
  of `<Chassis id=... des=...>` it accepts. A `CAR_DRIVER_TYPE` outside that list
  produces compile error `0x234 当前控制器不支持当前的底盘驱动类型` even when the
  wizard offered the combination: the wizard model library
  (`Resource/<lang>/model/...`) and this table are maintained separately and can
  disagree.
- `Resource/<lang>/Hardware/Device/<lib>/<MODEL>.xml` — `<Config>` gives
  `max_cycle_task`, `max_event_task`, `max_canopen_cmd_cnt`; each `<Version>` lists
  `FeatureNotSupport` / `FeatureSupport`.
- `Resource/<lang>/CompileError.xml` — the compile error id to message table.
  Looking an id up there beats guessing from the message.

`validate-controller-support` reads all of these.

## CANopen node ids are stored twice

```
HARDWARE_DEVICE_DOWNLINK_PORT
  HARDWARE_NET
    HARDWARE_DEVICE_UPLINK_PORT ADDRESS="1"       <- node id
      HARDWARE_CAN_DEVICE_OTHER | HARDWARE_CAN_DEVICE_MOTOR
        HARDWARE_CAN_DEVICE_SLAVE NODE_ID="1"     <- node id again
```

Write both or neither. `set-node-id` does; `set-attrs --kind station` refuses an
`ADDRESS` update rather than leaving the project half-changed.

## Enabling and disabling a CANopen object

Verified against xRobotDesigner V5.1.1 by enabling one object in the GUI and
diffing the project before and after. Two details contradict what an older
official sample suggests, so trust this table:

**Enable a named object**

| Element | Attribute | Disabled | Enabled |
|---|---|---|---|
| `HARDWARE_CAN_CMD_GROUP` | `HARDWARE_GROUP_ENABLE` | `NO` | `YES` |
| | `MODE` | absent | **`0` for every object, regardless of read or write direction** |
| | `READ_ONLY` | absent | `""` |
| | `EDTYPE` | `1` read-only / `0` writable; sometimes absent | added as `0` when absent |
| `HARDWARE_CAN_CMD` | `CMD_LEVEL` | absent | `""` |
| | `ID` | `""` | allocated number |
| `HARDWARE_CHANNEL_TAG` | `ENABLE` | `NO` | `YES` |
| | `USED_BY` | absent | **not written** (an older sample has it; this version does not) |

**Disable a command group**

| Element | Attribute | Change |
|---|---|---|
| `HARDWARE_CAN_CMD_GROUP` | `HARDWARE_GROUP_ENABLE` | `YES` to `NO`; `MODE="0"`, `READ_ONLY=""`, `CMD_ACCESS_TYPE=""` are added |
| `HARDWARE_CAN_CMD` | `ID` | previous number to **`"0"`**, not to an empty string |
| | `CMD_LEVEL` | added as `""` |
| `HARDWARE_CHANNEL_TAG` | `ENABLE` | `YES` to `NO` |

**Command id allocation.** `HARDWARE_CAN_CMD@ID` is the command id, and an
**enabled group without one does not compile**. This is the single nastiest trap
in the whole file format, because nothing in the error output points at it:

> A group with `HARDWARE_GROUP_ENABLE="YES"` and `ID=""` makes the compiler
> reject every PROGRAM that references the group's tag --
> `文本"<tag>"错误，字符串无法识别` plus one `无法识别引脚连接的变量` per output
> pin, all reported on 第1行 no matter where the reference really is.
> The project parses, the tag exists, the group reads as enabled, and
> `validate-hardware-bindings` is happy.

*Verified 2026-08-25 on an IVC300 project.* 27 enabled 6083/6084 groups with an
empty id produced 216 such errors; 5 sibling groups that still carried a stale
leftover id compiled untouched. Splitting the ST calls across lines, renaming,
and line-ending changes made no difference -- only the id did. 113 enabled
groups in the same project lack `READ_ONLY`/`CMD_LEVEL` entirely and compile
fine, so those two attributes are cosmetic; the id is not.

The GUI allocates the id when you tick the group, so this only bites projects
edited as XML. **Always run `alloc-canopen-command-ids` after enabling command
groups**, and `validate-canopen-command-ids` catches it either way.

What is actually required is **uniqueness across the project**, nothing more:
the same project compiled with ids scattered up to 229 and holes at 217..224,
and with three ids sitting outside their own station's range. The GUI's own
numbering is denser than that -- ids run 1..N over the enabled groups, in
allocation order, and only enabled groups hold one -- so `alloc-canopen-command-ids`
fills the lowest free numbers first to keep the file looking GUI-written.
(An earlier version of this file claimed ids come in a contiguous per-station
block. That is wrong: in the same project one station's 98 groups took
32, 40, 48, 56 ... interleaved through other stations' ranges.)

`ID="0"` and `ID=""` both mean "no id". On a **disabled** group that is normal
and repeats freely, so a duplicate check must ignore both -- but on an enabled
group both are the fault above.

**The CommFailed variable** is not enabled by ticking an object. It follows the
slave's `COMM_CHECK_WAY` setting: switching it from `""` to `1` (heartbeat) adds
`TIMEOUT` on `HARDWARE_CAN_DEVICE_SLAVE`, flips the `CommFailed` group to
`HARDWARE_GROUP_ENABLE="YES"` and moves its `DATOBJECT` from `3` to `4`.

Enabling is budgeted: `max_canopen_cmd_cnt` in the device library caps the total
number of enabled command groups per controller.

## Renaming a hardware variable

The GUI offers no rename. The edit touches only:

- `HARDWARE_CHANNEL_TAG@NAME`
- each child `VARIABLE_MEMBER@NAME`

`HARDWARE_CAN_CMD_GROUP@HARDWARE_CMD_TAG_NAME` keeps the original generated name;
an official sample ships in exactly that state and compiles.
