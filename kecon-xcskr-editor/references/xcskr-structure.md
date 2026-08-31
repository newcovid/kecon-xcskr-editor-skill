# Kecon `.xcskr` XML Structure Reference

## Contents

- Encoding and raw ST handling
- Control scheme and tasks
- POU and ST logic
- Graphical logic: LD and FBD
- Variables and user data types
- Hardware configuration and hardware variables
- A DESC longer than the GUI limit can only be written by a tool
- Member offsets are computed, not stored -- BOOL takes a byte and members are aligned
- Array members of a user data type are written expanded
- Vendor reference resources, and why none of their paths are hard-coded
- Modbus RTU master commands live in the hardware tree, not in ST
- Command group direction and send mode
- The vendor function block library is the authority on pin order
- Function block call argument order
- Changing a command group between input and output
- CANopen slave object dictionary
- The debug watch list is not in the project file, but a GUI save still changes it
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
  the element being replaced rather than picking one** (verified by
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
  official sample (counted). A bare `>` is legal XML in an attribute
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
  drifts from the shape the GUI writes. Verified by binding and
  unbinding pins on both an LD and an FBD block and re-reading the result.
- How graph-like a graphical POU is varies enormously and the format has to
  cover both ends. Measured: the official sample's `联动` holds 21
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

## A DESC longer than the GUI limit can only be written by a tool

xRobotDesigner validates every description field it saves and rejects an
over-long one with `描述长度超过%d个字符的限制！`.  The limit arrives as a
runtime `%d`; **128** was observed on a `VARIABLE` description in
5.1.0.  The same dialog family also enforces a name limit
(`名称长度不能超过%d个字符`), whose value is unverified.

Writing an over-long description straight into the XML bypasses the check
entirely.  Nothing complains: the project loads, compiles, downloads and runs.
The only symptom appears much later, when someone opens that field in the GUI
and finds they can no longer save the dialog -- and the message points at the
description they may not even have touched.  Since only a tool can create this
state, check for it after every scripted DESC change:

```
python xcskr_tool.py validate-desc-length --project P --strict
```

`check-workspace` runs it as part of the standard suite.

**Characters or bytes is unverified.**  The resource strings say `个字符` and
are stored UTF-16, which points at characters, but the project file is GBK, so
every CJK character costs two bytes and a 100-character Chinese description is
180 bytes on disk.  The validator reports that case as `OVER_BYTES`, a warning
rather than a problem.  To settle it, open one such field in the GUI and press
OK: accepted means characters, rejected means bytes.  Until then, keeping a
description inside the limit **both ways** costs nothing and removes the
question.

## Member offsets are computed, not stored -- BOOL takes a byte and members are aligned

*verified against offsets read out of the editor's user-data-type view.*

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

*verified -- against a member the user created in the GUI, and against
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

### A variable bound into the object dictionary must be written once per scan

The PLC scan and the CAN stack's SDO responder are **not interlocked**. Anything
bound through `HARDWARE_MODBUS_TAG_MAPPING` can be read by the master at any
point in the scan, including halfway through the code that builds it.

So the common ST idiom for packing a status word:

```
Status := 0;
IF Online    THEN Status := Status + 1;   END_IF;
IF DataValid THEN Status := Status + 2;   END_IF;
...
IF Enable    THEN Status := Status + 128; END_IF;
```

publishes every partial sum. With only bits 0, 1 and 7 set, the master sees the
variable pass through `0`, `1`, `3` before settling at `0x83` — and a master that
gates on one of those bits will see it drop, once in a while, for no reason it
can log. Compilation, validation and runtime are all clean; the only evidence is
a bit that flickers at the far end.

Build into a scratch variable and assign once:

```
Tmp := 0;
IF Online THEN Tmp := Tmp + 1; END_IF;
...
Tmp := Tmp + 128;
Status := Tmp;          (* single write — the master sees old or new, never half *)
```

To find these in an existing project: collect variables assigned as `X := 0`
followed by several `X := X + n`, and intersect that set with the `TAG_NAME`
values of `HARDWARE_MODBUS_TAG_MAPPING`. Anything in the intersection is exposed
and non-atomic. Variables that are merely written from several branches (each
assignment a complete value) are fine — the hazard is the accumulate-in-place
pattern, not multiple writes as such.

The mirror-image defence belongs on the consumer: debounce a bit whose loss is
expensive, and let recovery take effect immediately. Late to declare a fault is
usually safer than late to clear one.

*Observed on hardware: a status word read over SDO at 100 ms returned
0, 1 and 3 at random against a nominal 0x83.*

### The workspace exports .st as CRLF, because the GUI decides the stored style

`SECTION_LOGIC_ST CONTENT` holds the ST body, and xRobotDesigner writes its
line breaks three ways depending on which version last touched the POU: literal
LF, `&#10;`, or `&#x0D;&#x0A;`.  Current versions write the third.  The style is
per-POU, so a project the GUI has partly edited stores a mixture.

Exporting the decoded text verbatim hands that mixture straight into the
workspace: the POU someone opened in the GUI comes out CRLF, its neighbours
come out LF.  Every later GUI edit flips one more file, and a one-line change
then arrives as a whole-file diff with the real edit buried in it.  Verified:
one GUI-edited program turned a 3-line comment change into 1599 changed lines.

The GUI is a co-author and cannot be configured, so the workspace converges on
its style rather than fighting it: `export-workspace` writes every `.st` with
CRLF regardless of what the project stores.  Nothing downstream needs to care --
`xml_attr_encode` normalizes newlines before re-encoding, so `import-workspace`
still writes each element back in that element's own style and the round trip
stays byte-identical.  The project file is left alone; only the workspace, which
is the thing humans read and diff, is made uniform.

Set the editor to match (`files.eol` = `
` for `.st`), and keep
`.gitattributes` on `* -text` either way: that switch is about not letting git
rewrite line endings, which matters more now that two different styles are in
play.

## A scratch variable shared by two tasks is worse than the tear it was added to fix

Task priority is fixed: startup > event > cycle > main, and a higher-priority
task **preempts** a lower one mid-scan.  `list-tasks` prints the priority.

The write-once-per-scan rule (above) is usually satisfied by building the value
in a scratch variable and assigning the target once.  That fix is void if the
scratch variable itself is shared with another task.  Verified on a
two-controller project: a `UINT` scratch was used by a main-task program to
assemble a status word *and* by a 50 ms cycle program to assemble a different
one.  When the cycle task preempts between `X := 0` and `target := X`, it
overwrites the whole scratch; the main task resumes, keeps adding bits, and
publishes the other program's value with a few bits added.

This is strictly worse than the torn read it was introduced to prevent.  A torn
read is transient -- the next scan publishes the correct value.  This **latches
a wrong value** into the target and holds it until the next main-task scan.

Same trap for `FOR` loop counters: a counter shared between a main-task loop and
a cycle-task loop can make the main-task loop exit early, leaving the tail of an
initialisation array at its default while the "init done" flag is still set.

Rule: one scratch variable, one task.  Name or document them per task, and when
adding a cycle-task program, check every scratch it touches against the main
task's usage.  Nothing in the file marks a variable as task-local, and the
compiler will not complain.

## Downlink port settings live in child elements, not on the port tag

A `HARDWARE_DEVICE_DOWNLINK_PORT` start tag carries identity and geometry --
`ID`, `NAME`, `DISPLAY`, `PHYSICAL_ID`, `PROTOCOL`, `TYPE`, `RECT_POSITION`.
Everything the runtime configures the port with sits in
`<HARDWARE_PROPERTY ID=".." VALUE=".."/>` children of that port:

| Property | Meaning |
|---|---|
| `CAN_BAUD` | baud rate for the first CAN port group (`0x00`=125k `0x01`=250k `0x02`=500k `0x03`=750k `0x04`=1000k) |
| `CAN_BAUD2` | baud rate for the second group -- same encoding but **no 750k**, so `0x03` is not a value here |
| `CAN_TERMINAL_R` | built-in termination (`0x00`=off `0x01`=on) |
| `CAN_BUS_RESET`, `CAN_PORT` | bus reset enable, physical port number |
| `COM_BAUD`, `COM_DATABITS`, `ROBOT_COM_PARITY`, `ROBOT_COM_STOPBITS` | serial framing |
| `TCP_LOCAL_PORT` | listening port for a Modbus TCP server |

Writing one of these onto the port's start tag instead is silently harmless and
silently useless: the attribute is accepted by every text-level check, the
project still opens, and the port keeps running at its old setting. `set-attrs
--kind downlink-port` routes any name in `PORT_PROPERTY_IDS` to the child
element and reports the target as `downlink-port:<id>:<property>` -- if the
output shows only `downlink-port:<id>`, the value went onto the tag and the
property was not touched. One property per call; mixing a property with a
start-tag attribute is refused because they are different elements.

*Verified: `CAN_BAUD` written onto the start tag left the port at its
previous rate, with no warning from the compiler or the GUI.*

### `DISPLAY` is a label, not an identifier

Two downlink ports can carry the same `DISPLAY` string. A controller whose CAN
port can act as either master or slave exposes both roles as separate ports, and
both read the same `DISPLAY` while differing in `ID`, `NAME` and `PHYSICAL_ID`
-- the `NAME` of one of them need not resemble the `DISPLAY` at all.

Locate a port by `ID` or `PHYSICAL_ID`. Matching on `NAME` or `DISPLAY` can
silently pick the wrong port, and objects written under the wrong port are
accepted by every text-level check: the file parses, the project opens, and the
data simply never appears on the wire.

Locating by proximity is the same trap in a different shape. Ports nest, so the
nearest preceding `HARDWARE_DEVICE_DOWNLINK_PORT` tag before an object is not
necessarily its parent; walk the element stack instead.

*Verified on a production project: ports `ID="6"`
(`NAME="CAN2"`, `PHYSICAL_ID="65"`) and `ID="8"` (`NAME="CAN4"`,
`PHYSICAL_ID="67"`) both carry `DISPLAY="CAN2"`, and all 36 slave objects live
under `ID="6"`.*

## A Modbus TCP server exposes variables through named mapping windows

A port running as a Modbus server (`PROTOCOL="2"`, `MODE="1"`, with a
`TCP_LOCAL_PORT` property) owns no mappings of its own. It names them:

```
HARDWARE_DEVICE_DOWNLINK_PORT PROTOCOL="2" MODE="1"
  HARDWARE_MODBUS_MAPPING_QUOTE NAME="MODBUS_30001_30192_0"
  HARDWARE_PROPERTY ID="TCP_LOCAL_PORT" VALUE="502"
```

and the windows themselves live under `TAGCONFIG`, beside the variables:

```
TAGCONFIG
  HARDWARE_MODBUS_MAPPING NAME="MODBUS_<start>_<end>_0" START_ADDR=".." END_ADDR=".."
    HARDWARE_MODBUS_TAG_MAPPING OFFSET="0" TAG_NAME="Some.Variable"
    HARDWARE_MODBUS_TAG_MAPPING OFFSET="1" TAG_NAME="Some.Other[3]"
```

`OFFSET` is the index within the window, **one entry per scalar** -- an array is
mapped element by element, exactly like the object-dictionary mappings on a
CANopen slave port. The `NAME` encodes the range, so widening a window means
renaming it and updating the quote on the port; the two must agree or the
mapping is silently unreferenced.

**`OFFSET` counts addresses, not entries.** A tag occupies as many addresses as
its type is wide in that space's unit, so consecutive entries are only
consecutive integers when every tag is exactly one unit wide:

| Space | one address is | one entry per |
|---|---|---|
| Coils, discrete inputs | 1 bit | `BOOL` only |
| Input, holding registers | 16 bits | `INT` / `UINT` / `WORD` (and `BYTE`) |

Put a `BYTE` in a bit space and it swallows **eight** addresses; every `OFFSET`
after it is then one the previous tag already owns, and the project is rejected
at compile time with 位号地址存在重叠 -- naming the *window*, not the tag that
caused it, so a 200-entry window gives no clue where to look. Anything wider
than one register in a register space has the same shape of problem with an
extra unknown: **nothing in the files says whether the next `OFFSET` steps by
one or by two.** Do not guess -- scale wide values to 16-bit integers in the
program (put the factor in the field name) and map those. A panel prefers that
form anyway; it only has to divide by a constant.

`validate-modbus-mapping` checks all of this, plus the failure that leaves no
trace at all: **a quote naming a window that does not exist.** The port carries
only `HARDWARE_MODBUS_MAPPING_QUOTE NAME=...`; delete or clobber the window
under `TAGCONFIG` and the file stays well-formed, every tool reports success,
and the mapping is simply gone. A regex that reaches for a window by name is the
usual way to lose one -- `[^>]*` swallows the `/` of a self-closing window, the
match falls through to the `>.*?</HARDWARE_MODBUS_MAPPING>` branch, and it eats
across the whole window into the *next* one's closing tag, deleting a neighbour.
Match the start tag only as far as its first `>`, then decide.

`START_ADDR` carries the classic Modbus address-space prefix, and which one it
is decides the direction and the function codes the window answers:

| Space | `START_ADDR` | Direction | Function codes |
|---|---|---|---|
| Coils | `1`..`9999`, no prefix | client may write bits | 01 read, 05 / 15 write |
| Discrete inputs | `10001`..`19999` | read-only bits | 02 read |
| Input registers | `30001`..`39999` | read-only words | 04 read |
| Holding registers | `40001`..`49999` | client may write words | 03 read, 06 / 16 write |

So the direction of a datum is chosen by **which window it is mapped into**, not
by any attribute on the tag. Put what the controller reports into the discrete
input and input register windows, and what the panel sends into the coil and
holding register windows; mapping a controller-written variable into a writable
window invites the panel to fight the program for it.

A register is 16 bits. How `OFFSET` counts for a datum wider than one register
(a `REAL`, `DINT` or `UDINT` would need two) is **unverified** -- nothing in the
files says whether the next entry starts one slot later or two. Sidestep it:
convert wide values to scaled 16-bit integers in the program and map those. That
is also the friendlier form for a panel, which then only has to divide by a
constant.

*Verified on 5.1.0 by having the GUI create one window of each of the
four address types and diffing the file.*

## Modbus RTU master commands live in the hardware tree, not in ST

A serial port running as a Modbus RTU master polls on its own. Nothing in ST
builds or sends a frame. Each request is one `HARDWARE_COM_CMD` element nested
under the slave's `HARDWARE_OTHER_DEVICE_RTU`, which itself sits under a
`HARDWARE_DEVICE_UPLINK_PORT` whose `ADDRESS` is the Modbus slave address:

```
HARDWARE_DEVICE_DOWNLINK_PORT PROTOCOL="1" MODE="0" ADDRESS="0"   <- the master port
  HARDWARE_NET
    HARDWARE_DEVICE_UPLINK_PORT ADDRESS="1"                       <- slave address
      HARDWARE_OTHER_DEVICE_RTU
        HARDWARE_COM_CMD DEV_TYPE="0" ID=".." TYPE="0"
          HARDWARE_CHANNEL_TAG DATATYPE="UINT[n]" NAME=".."       <- data lands here
            VARIABLE_MEMBER ... x n
          HARDWARE_FLAG_TAG DATATYPE="BOOL" NAME="<tag>_F"
          HARDWARE_PROPERTY ID="COM_CMD_CYCLE"      VALUE=".."    <- poll period, ms
          HARDWARE_PROPERTY ID="COM_CMD_FC"         VALUE=".."    <- function code
          HARDWARE_PROPERTY ID="COM_CMD_START_ADDR" VALUE=".."    <- first register
          HARDWARE_PROPERTY ID="COM_CMD_NUMBER"     VALUE=".."    <- register count
      HARDWARE_PROPERTY ID="COM_SLAVER_RESPTIME"    VALUE=".."    <- per-slave, ms
      HARDWARE_PROPERTY ID="COM_SLAVER_INTERVALTIME" VALUE=".."
```

`COM_CMD_NUMBER` must equal the array length in the channel tag's `DATATYPE`,
and the `VARIABLE_MEMBER` children must be expanded to that many elements the
same way user data type arrays are.

**Read and write commands differ only in `COM_CMD_FC`.** A write command is
written exactly like a read one -- same `HARDWARE_COM_CMD` shape, `DEV_TYPE="0"`,
`TYPE="0"`, same `HARDWARE_CHANNEL_TAG` with `READONLY="NO"`, same generated
`<tag>_F` companion -- and only the function code says which direction the data
moves (`3` reads holding registers, `6` writes one, `16` writes several). There
is no separate direction attribute, so do not go looking for one: `TYPE` is `0`
on reads and writes alike. For a write command the channel tag is the source,
and the master pushes whatever it holds on every `COM_CMD_CYCLE` -- there is no
event-driven mode, so a value that must not be re-sent has to be neutralised in
the tag itself rather than by suppressing the send. *Verified on
5.1.0 by having the GUI create FC 6 and FC 16 commands and diffing the file: the
only bytes that differed from an FC 3 command were the function code, the start
address, the count and the tag name.*

The port's own `ADDRESS` is `0` in master mode: **a Modbus RTU master has no
station number**, only slaves are addressed. `MODE="0"` on the downlink port
goes with master operation and `MODE="1"` with slave operation, matching how a
Modbus TCP server port and a CANopen slave port are written.

Three things that are easy to get wrong:

**Every channel tag gets a `<tag>_F` companion, and what it means is
unverified.** The generator emits a `HARDWARE_FLAG_TAG` beside every
`HARDWARE_CHANNEL_TAG` -- beside the physical `DI`/`DO`/`AI` points as well as
beside a Modbus command's data block. A physical input has no notion of
"communication failed", so a per-channel force/override flag fits the pattern
better than a fault flag, but nothing in the shipped files says so. One
measurement narrows it: on a healthy Modbus link, with the block visibly
updating, the flag reads `OFF` -- so it is **not** a "read succeeded" flag.
Whether it is a "read failed" flag or a force flag is still open. Settle it by
disconnecting the slave's wiring and watching the flag; that same experiment
answers the question below, so run them together. Until then, do not build a
liveness judgement on it.

**An RTU slave gets no comm-status tag.** A CANopen slave with a `DEVICE_NAME`
generates `<name>_CommFailed` that a program can read. `HARDWARE_OTHER_DEVICE_RTU`
has no `DEVICE_NAME` and generates nothing equivalent -- neither the official
sample project nor a hand-built one produces such a tag. Liveness of an RTU
slave therefore has to be judged from the payload itself. Whether the runtime
zeroes a command's channel tag on timeout or leaves the last good values in it
is **unverified**, so a robust check covers both: a plausibility test on a field
that cannot legitimately be zero, plus a staleness test on whether the block's
contents change at all within a timeout.

**`COM_CMD_START_ADDR` is one-based: the runtime sends `value - 1` on the
wire.** Writing the register number straight out of a device's protocol document
polls the register before it and shifts the whole block by one slot. To read
from protocol address `0x0001`, write `2`.

This is the worst kind of wrong. Every field still arrives, every field is
non-zero, and every field has a plausible magnitude, because a shifted register
map is still a register map -- a voltage lands where the code expects a relay
word, a current lands where it expects a state code. Nothing in the project
fails, nothing warns, and the values only give themselves away when they are
compared field by field against the device's own host software. Read the block
once before trusting any of it and check a field whose true value is known
independently, not merely one whose value looks reasonable.

*Verified on 5.1.0: with `COM_CMD_START_ADDR=1` on an FC03 block, the
register documented at `0x0002` arrived in array slot `[2]`, so slot `[0]` held
`0x0000`. Five fields cross-checked against the device's own host application
agreed on the same one-slot shift, and the protocol document's own worked
example confirms its addresses are raw wire addresses (`00 01` on the wire for
address `0x0001`), so the offset is the runtime's, not the document's.*

**`COM_BAUD` is a small index, not a rate.** `COM_DATABITS=3` for 8 data bits,
`ROBOT_COM_PARITY=0` for none and `ROBOT_COM_STOPBITS=0` for one stop bit are
all zero-based indexes into their dropdowns, and `COM_BAUD` behaves the same
way: it is a zero-based index into the standard rate list

```
0:50  1:75  2:110  3:134  4:150  5:200  6:300  7:600  8:1200  9:1800
10:2400  11:4800  12:9600  13:19200  14:38400  15:57600  16:115200
```

so `12` is 9600 and `16` is 115200. No vendor table documents this; the list was
derived from the two observed values and then confirmed against the GUI.

*Verified: a port stored as `COM_BAUD="12"` reads 9600 in the GUI
dropdown. Only that one entry was read back directly; the rest of the list is
inferred from its position and from `16` matching a port intended to run
115200.*

*Structure verified against an official Kecon sample project that
ships with two configured RTU commands, and reproduced by hand-building two more
in a second project that then passed every validator.*

### Re-importing an EDS silently resets command direction and renames tags

Pointing a master port's device at a freshly exported EDS rebuilds that node's
`HARDWARE_CAN_CMD_GROUP` set from the file. Two things change that nothing
reports:

**1. `EDTYPE` is reset.** Groups come back with `EDTYPE=""` or `EDTYPE="0"` --
output commands. A group that reads a slave object must be `EDTYPE="1"`. Left as
output, the master writes its own zero-filled buffer into the slave object every
cycle, overwriting whatever the slave computed and reading back zeros forever.
Nothing fails: it compiles, downloads, runs, and the value is simply always 0.
Run `validate-command-directions` after every EDS import.

**2. Tag names follow the EDS object names.** Renaming an object on the slave
side and re-exporting renames every command group tag that reads it, so ST
referring to the old names no longer resolves. This one at least surfaces at
compile time, but the fix has to happen in the same pass as the import -- grep
the ST for the node's tag prefix before and after.

Groups for objects the new EDS no longer declares are dropped outright, which is
the convenient half: disabling a slave object and re-exporting removes the
master's now-dangling reads without touching them by hand.

### CANopen slave object dictionary: three limits only the GUI enforces

*Measured on hardware by bisecting a live dictionary against a bus
analyser — seven download-and-probe rounds, then two more at the boundary.*

A controller acting as a CANopen **slave** publishes `HARDWARE_CAN_SLAVER_OBJECT`
entries under its slave port. Three rules govern them and **the GUI is the only
thing that checks any of them**. A project edited outside the GUI can break all
three, compile without a warning, download successfully and send its boot-up
frame — while the dictionary the controller actually builds is empty. The
symptoms are uniform and point away from the cause:

- every SDO read of a **data sub-index** (`sub1`..`subN`) aborts with
  `0x06020000` (object does not exist), including indices plainly present in the
  file;
- `0x1A00 sub1` — the TPDO mapping entry — reads `0`, where a working dictionary
  returns a packed descriptor such as `0x20040120` (index `0x2004`, sub `1`,
  32 bits);
- no TPDO is ever transmitted, even after an NMT start the slave accepts.

Two things that look diagnostic are **not**, and cost a day if trusted
(re-measured against a dictionary confirmed working end to end):

- **`0x1000` device type reads `0` either way.** These controllers do not
  populate the standard device-type object at all, so a zero says nothing about
  whether the dictionary was built.
- **Reading `sub0` returns `0` with command byte `0x53`, not the entry count
  with `0x4F`.** The sub0 of a slave object is not the DS301 "number of entries"
  here; it answers as a 4-byte item holding zero. A healthy dictionary looks
  exactly like a broken one at `sub0`. Probe `sub1` instead — that is where the
  abort actually distinguishes the two.

**1. The object name must be non-empty, at most 15 characters, ASCII letters
and digits only.** No underscores. Saving one in the GUI raises 「对象名称非法！
名称不能为空，名称长度不能超过15个字符，只能包含英文字母、数字。」; nothing at
all reports it when a script writes one.

**2. `DATATYPE` must be a value from the GUI dropdown** — `boolean`, not `bool`.
A near-miss spelling survives every text-level check there is.

**3. At most 63 bound variables per slave port.** Sum the
`HARDWARE_MODBUS_TAG_MAPPING` children across every enabled object on the port:
63 works, 64 kills the whole dictionary. Object count, total data bytes and
sub-index count were each ruled out along the way — 14 objects, 169 data bytes
and 81 sub-indices all pass, while two different 64-mapping layouts (one 176
bytes, one 200 bytes, both 14 objects) both fail. Unmapped array elements are
free, so a reserved object costs nothing but its own presence.

`validate-slave-objects` checks all three and prints the per-port budget; run it
after any script-side edit to a slave dictionary.

The budget is small enough that it has to be designed around rather than
discovered. Wide process data is cheap only when packed into few, wide array
elements: eight `uint32` values spread over four TPDO objects cost 8 mappings,
while eight diagnostic arrays of 8 elements cost 64 by themselves and leave room
for nothing else.

### Station communication check: the GUI label does not match the wire

*Verified against a live CAN bus, cross-checked with a bus analyser
and the controller's own CAN log.*

A CAN station keeps two related attributes on `HARDWARE_CAN_DEVICE_SLAVE`:

| GUI field | Attribute |
|---|---|
| 通信检测超时时间 | `TIMEOUT` (ms) |
| 通信检测机制 | `COMM_CHECK_WAY` |

**`COMM_CHECK_WAY="1"` shows as 心跳检测 (heartbeat) in the station property
page, but the master puts node guarding on the wire.** What the bus actually
carries: the master transmits DLC=0 frames on `0x700+NodeID`, and slaves answer
with a single data byte whose bit 7 alternates (`0x05` then `0x85`). That toggle
bit belongs to node guarding alone — a heartbeat producer transmits on its own
initiative, is never polled, and always sends bit 7 clear.

The distinction is not cosmetic, because the two protocols have different
prerequisites. Heartbeat consumption needs the *slave* configured with a
non-zero producer heartbeat time (`0x1017`); node guarding needs nothing on the
slave at all — the master drives it and any DS301 slave answers. So a
commissioning procedure that writes `0x1017` into every slave because the GUI
said "heartbeat" may be maintaining something the online detection never reads.

Prove the dependency before building on it: set one slave's `0x1017` to zero and
watch whether that station's `CommFailed` trips within its timeout. If it stays
online, the link is running on node guarding and `0x1017` is decoration.

### On-board I/O channel properties

*Verified: a controller's eight on-board DI channels were switched
from NPN to PNP in the GUI and confirmed by an I/O bench test. The resulting
file diff was exactly the eight `VALUE` attributes described below, plus the
project `VERSION` counter.*

On-board I/O hangs off the module's channel list rather than a fieldbus port,
and every channel carries its electrical configuration as a sibling of its tag:

```text
HARDWARE_CHANNEL          NAME="DI1"  TYPE="DI"
  HARDWARE_CHANNEL_TAG    NAME="DI0001"  DATATYPE="BOOL"
  HARDWARE_PROPERTY       ID="DI_PNP_NPN_TYPE"  VALUE="0x00"
```

| `HARDWARE_PROPERTY ID` | `VALUE` | Meaning |
|---|---|---|
| `DI_PNP_NPN_TYPE` | `0x00` | NPN (sinking) — the value a newly created project starts at |
| | `0x01` | PNP (sourcing) |

Three properties of this field make it worth a dedicated note:

- **It is per channel, not per module.** Changing input polarity means editing
  every channel. A project may legally hold a mix, so one channel left at the
  default sits invisibly next to seven correct neighbours.
- **Nothing catches a mismatch.** The project compiles, every `validate-*`
  passes, and the only symptom is inputs that never go TRUE (or read stuck
  TRUE). On a bench that reads as a wiring fault, which sends the search to the
  terminals instead of to the configuration.
- **The default is not the common case.** A great deal of field equipment ships
  with PNP outputs while the project starts at NPN, so a fresh project is more
  often wrong than right until someone checks it against the actual sensors.

When a controller's digital inputs all read FALSE with the sensors visibly
energised, read these properties back before touching any wiring. Reading them
back is also the only way to confirm a bulk polarity change actually landed on
every channel.

## Command group direction and send mode

*Verified by reading the GUI property panel for four objects in a
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

`2` and `3` were established by a controlled experiment: the two
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
- **A slave *parameter* write on `MODE="1"` never retries either, and that
  is a different trap from the command case above.** 变化发布 fires once when
  the tag value changes and never again, so an SDO that lands while the slave
  is still initialising after power-up is lost for good: the tag keeps the
  value the program wrote, nothing re-sends it, and the only symptom is a
  generic `CommFailed` — which sends the commissioning engineer off to check
  wiring that is perfectly fine. For configuration the master must
  re-establish on every power-up (`0x1017` producer heartbeat is the
  canonical one) prefer `MODE="3"` 变化加周期 with a long `CYCLE_TIME`, so a
  slave that reboots on its own converges within one cycle.
  Cyclic writes to ordinary parameter objects are **not** EEPROM wear: under
  DS301 an SDO write lands in the object dictionary in RAM, and only an explicit
  write to `1010:01` (store parameters) commits it to non-volatile memory.
  Confirm it per device — a vendor is free to commit on write — but the wear
  warning above is about `1010:01` itself, not about the parameters.

## Vendor reference resources, and why none of their paths are hard-coded

*verified on a 5.0.50.0 install.*

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

*verified -- read straight from the installed library and cross-checked
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

*Verified: reordering the declarations to match the call sites was
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

*Refined against 80 groups converted in a second project.* The three
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


*Verified by switching one object in the GUI and diffing against its
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

## The debug watch list is not in the project file -- but a GUI save still changes it

*verified by inventorying every XML element and attribute name in two
production projects and both official samples, and by locating the file the GUI
actually writes.*

A natural suspicion about `.xcskr` is that the debugging UI -- the variable
monitor, its trend colours, a force table -- is stored inside the project, so
that merely opening the GUI dirties the file and invalidates any hash taken over
it. **It is not there.** Nothing in the format describes a watch list:

| Project | Distinct element names | Monitor-related |
|---|---|---|
| production, V5.1.1.9998-C, 5.2 MB | 55 | none |
| production, V5.1.1.9998-C, 0.9 MB | 45 | none |
| official sample, V5.0 | 52 | none |
| official sample, V5.1 | 50 | none |

Nor do the attribute names: nothing matching `MONITOR`, `WATCH`, `DEBUG`,
`FORCE`, `TRACE`, `OSCILLOSCOPE`, `CHART`, `CURVE`, `VIEW`, `LAYOUT`, `WINDOW`,
`UI_`, `RECENT` or their Chinese equivalents appears on any element, and the
byte strings `DebugVar` and `Monitor` occur zero times in either production
project.

## Array elements carry their own DESC

An array-typed `VARIABLE_MEMBER` nests one child `VARIABLE_MEMBER` per element,
named with the subscript, and each child has its own `DESC`:

```xml
<VARIABLE_MEMBER DATATYPE="BOOL[128]" DESC="current alarms" NAME="ALM.Active">
  <VARIABLE_MEMBER DATATYPE="BOOL" DESC="drive 1 offline" NAME="ALM.Active[0]"/>
  <VARIABLE_MEMBER DATATYPE="BOOL" DESC=""               NAME="ALM.Active[1]"/>
</VARIABLE_MEMBER>
```

These are worth filling. The variable monitor expands an array by subscript, so
a 128-entry alarm bitmap shows as `ALM.Active[0]` .. `[127]` and the engineer
has to go back to the alarm-number table to read it -- which nobody does at a
commissioning bench. The GUI lets a person type each one, and a script can fill
the lot from whatever table already defines the meaning. *Verified on
5.1.0: 991 element descriptions written by script, opened and read back in the
GUI monitor.*

Fill them by locating the single element's start tag by `NAME` and rewriting
only its `DESC` attribute. Do not round-trip the document through ElementTree to
do it -- re-serializing reformats the whole file.

Write a description through `xml_attr_encode`, or restrict it to text with no
XML metacharacters. A hand-rolled patch that drops a `<` or an `&` straight into
`DESC="..."` produces a file that is no longer well-formed, and the failure
surfaces far from the edit: the writing script succeeds, the bytes land on disk,
and the next tool to parse the project dies with `not well-formed (invalid
token)` at a line number, while the GUI simply refuses to open the project. The
trap is that descriptions are prose, and prose about a protocol naturally
contains comparisons -- a state code documented as "at or above 1.5A" is easy to
write as `>=1.5A`, and its `<=` twin is what breaks the file. `>` alone is legal
inside an attribute value; `<`, `&` and `"` are not. *Verified on
5.1.0.*

`rebuild-variable-members` carries them across. It regenerates the member tree
from the struct definition, and the struct definition has no place to record
per-element text, so a naive rebuild would return every element `DESC` to the
empty string -- silently, since the project still compiles and runs and the loss
only shows as a blank column in the monitor much later. Adding one struct member
months afterward is enough to force such a rebuild. The command therefore
harvests the existing `NAME` -> `DESC` map from the variable's current subtree
first and puts it back wherever the regenerated node has no description of its
own, and it reports how many it carried as `keptDesc=N`. A struct field's
description still comes from the struct definition, which is its source of
truth; only elements, which have no such source, fall back to the harvest.
`--drop-element-desc` opts out. *Verified on 5.1.0: rebuilding three
variables on a project with 1945 described elements kept all of them.*

**The watch list is a sidecar file.** Beside the project sits a directory
carrying the project's own name, holding build output (`CS<n>/Bin`,
`CS<n>/Debug`, `Compile.log`, `StationInfo_CS<n>.xml`, `archive.zip`) and one
file per watch group:

```text
<project dir>/DebugVar_CS<scheme>_P<group>.txt
```

`CS<scheme>` is the control scheme (controller) number. The trailing index is
**not** the program id, tempting as the `P` prefix makes that reading: the
observed lists mix variables belonging to several different programs, and they
do not line up with the `P<id>` program files that `EmulatorInfo_CS<n>.xml`
names. Reading it as the monitor's own group or page number fits what is there,
but the exact meaning is *unverified*.

Each line is `variable,0,colour`. The colour is a decimal RGB handed out from a
ten-entry cycle (`255` = 0x0000FF, `38400` = 0x009600, `16711680` = 0xFF0000, and
so on) -- the trend colour the monitor plots that variable in:

```text
Wheel[0].Angle_cdeg,0,16711680
Status.State,0,38400
```

The colour is not stored per variable so much as handed out by position: in
every observed file the colours run straight down this ten-entry cycle, one step
per line, wrapping at the end.

```text
255  38400  16711680  65535  16776960  33023  8388736  32896  16711935  8421440
```

Where a file *starts* in that cycle varies (two of three observed lists start at
`255`, one starts at `16711935`), which fits a rotating counter the monitor
advances as variables are added rather than a per-file reset. Nothing reads the
colour back, so starting a hand-written list at the first entry is safe.

The middle field is `0` on every line of every observed list; its meaning is
unknown. Lines are CRLF and the file ends with one, and names are written
exactly as ST spells them -- `Struct.Member`, `Array[0]`, `Struct.Array[15]`,
zero-based. In practice the content is ASCII, so the project's GBK encoding
never comes up, but write it as GBK anyway to stay consistent with the rest.

*Unverified: whether the GUI accepts a hand-authored list unchanged.* The format
above is read off files the GUI itself wrote; a round trip through the GUI after
writing one by hand has not been observed. Write it only while xRobotDesigner is
closed -- the GUI holds the watch list in memory and rewrites the sidecar when it
saves, exactly as it does with the project.

The naming is the vendor's rather than an inference: `RobotBaseCommonAcsR.dll`
holds the literal `DebugVar_CS%d_P%d.txt` and exports
`CBaseCommonAcs::GetDebugVarFile(std::string, int, int)`, which
`xRobotStudioR.exe` imports. An emptied watch list is still written out, as a
zero-byte file.

Two consequences:

- A hash taken over the `.xcskr` alone -- the text workspace's `manifest.json`
  gate is exactly that -- **cannot** be tripped by monitoring a variable,
  changing a trend colour, or clearing the watch list.
- The sidecar directory is build output and belongs in `.gitignore` wholesale.
  The watch list going with it is the right outcome: it is one engineer's
  debugging session, not project content.

**What a GUI save does change is `PROJECT@VERSION`.** It is a save counter, and
only the GUI writes it -- the CLI tools read it and never assign it. Across 123
consecutive pairs of saved states from two projects (backups taken before every
CLI write, plus the live files) the counter advanced in 22 and stood still in
101, and every advance falls in a window where the GUI had had the project
(`117 -> 166` and `111 -> 151` over eight days). Since the counter lives in the
file, **any GUI save invalidates a hash of the project whether or not the logic
changed** -- the same practical symptom the watch-list theory was invented to
explain, from a different cause. The response is to re-export the workspace
after the GUI has had the project, not to hunt for what moved.

Two points remain *unverified*. Whether the GUI marks the document dirty on
merely opening it: the backup chain samples only at CLI-write moments, so a bare
open-and-close cycle cannot be isolated within it. And whether a save with no
edit writes anything besides the counter: version increments do outrun the
visible edits between backups -- one pair advanced three versions while the body
lost a single line of ST -- which points that way without settling it. Settling
both takes one measurement: hash the project, open it in the GUI, close it,
answer the save prompt, hash again.

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

*Verified on an IVC300 project.* 27 enabled 6083/6084 groups with an
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
number of enabled command groups per controller. The cap is **per controller model**,
not per software version: IVC300/IVC200/IVC6000 declare 256, FRC5000 and IVC2000-E
declare 144, and the MRC/CRC/DRC families declare 80. Exceeding it fails the build
with `0x233 canopen最多支持%s条命令` from `Resource/<lang>/CompileError.xml`, whose
`%s` is filled from the same library field. *verified by reading
`Resource/chs/Hardware/Device/{1.0.0,2.0.0}/*.xml` and `CompileError.xml`.*

**How a slot is charged** — this is the part that is invisible in the file and
easy to design against:

| Access path | Cost |
|---|---|
| A raw PDO channel (`XCS_TPDO1`, `XCS_RPDO1`, …) | **1 group per 8-byte PDO** |
| A named SDO sub-index | **1 group per sub-index** — a `bool` costs the same as a `uint32` |

So an object declared `bool[8]` on the slave costs the master **8** groups to carry
**8 bits**, while a `uint32[2]` riding a TPDO costs **1** group to carry 8 bytes.
A slave object dictionary laid out one-quantity-per-object / one-sub-index-per-device
reads beautifully and can silently consume most of the master's budget: in one
project a single gateway station held 106 of 256 groups. *verified on a
production project by disabling 42 groups with no loss of information — two boolean
arrays that duplicated bits already carried in a status word (16), a target value
the slave could own itself (8), a request array that had a PDO channel alongside it
(7), eight DI bound one-per-sub-index that packed into one byte (7), and three
`Reserved` PDO channels (3).*

When budget is tight, look for these in order: sub-index arrays of `bool`, values
duplicated in a status word, write objects whose value never varies per device, and
named sub-objects that shadow an already-enabled raw PDO channel.

## Renaming a hardware variable

The GUI offers no rename. The edit touches only:

- `HARDWARE_CHANNEL_TAG@NAME`
- each child `VARIABLE_MEMBER@NAME`

`HARDWARE_CAN_CMD_GROUP@HARDWARE_CMD_TAG_NAME` keeps the original generated name;
an official sample ships in exactly that state and compiles.
