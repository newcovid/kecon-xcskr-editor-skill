---
name: kecon-xcskr-editor
description: Use when Codex needs to inspect, summarize, export, or safely modify generic Kecon/xRobotDesigner .xcskr PLC projects, including hardware configuration, variables, user data types, function blocks, LD/FBD graphical logic, control-scheme tasks, ST code, CAN/CANopen, Modbus, and GBK XML.
---

# Kecon xRobotDesigner `.xcskr` Editor

Resolve the directory containing this `SKILL.md` from the available-skills catalog and assign
its absolute path to `$keconSkillDir` before running the examples. Do not assume a fixed drive,
username, or Codex home directory.

## Core Workflow

1. Search the help first when the task involves Kecon concepts, built-in function blocks, communication setup, navigation, chassis, safety, or model parameters:

```powershell
python (Join-Path $keconSkillDir "scripts\kecon_help.py") search "关键词"
python (Join-Path $keconSkillDir "scripts\kecon_help.py") show <topic-id>
```

`search` covers the curated notes in `references/` plus a local index built from
the xRobotDesigner CHM installed on the machine. Build that index once; it takes
about ten seconds and is the authoritative source for block pin tables:

```powershell
python (Join-Path $keconSkillDir "scripts\kecon_help.py") status
python (Join-Path $keconSkillDir "scripts\kecon_help.py") index --chm "D:\KCSmart\xRobotDesigner\Resource\chs\HelpFile\xCSStudioHelpFile.chm"
```

Indexing decompiles the CHM with the Windows built-in `hh.exe`, extracts plain
text, and caches it under `~/.kecon-xcskr-editor/help` (override with
`--cache-dir` or `KECON_HELP_CACHE`). Vendor help content is never copied into
this repository. If a topic is missing, ask the user for the CHM path rather
than guessing it.

2. Treat `.xcskr` as GBK XML. Read/write with `encoding='gbk'`.
3. Export a compact AI package before reasoning about the project:

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") export-ai --project "D:/path/project.xcskr" --output-dir "$env:TEMP/kecon_ai_pack" --st-mode files
```

4. Read `index.json` first, then open only the needed package files:
   - `controller.json`: controller node, `GENERAL_CFG`, configuration wizard model and parameters, `WHEEL_CFG` geometry, `NAVI_CFG`. Compile failures about the chassis or the controller model are decided here, not in `hardware.json`.
   - `hardware.json`: downlink ports, stations, hardware variables, CANopen slave objects/mappings.
   - `programs.json`: programs under `CONTROL_SCHEME` tasks.
   - `graphics.json`: LD/FBD blocks, pins, connections, lines and comments.
   - `function-blocks.json`: custom FB interfaces and ST file paths.
   - `variables.json`: custom/global variables.
   - `user-data-types.json`: user structs and members.
   - `st/`: ST sources split into separate files.
5. Prefer structured commands over raw XML editing. Use `replace-st` for ST, `set-attrs` for attributes, the `add-*` commands for new variables and data types, and the graphical commands for LD/FBD.
6. Write commands create timestamped backups by default. Use `--dry-run` first for risky edits.
7. After editing, rerun `export-ai`, `validate-st-format --strict`, `validate-datatypes --strict`, and relevant static validators. Do not drive xRobotDesigner command-line compile yourself; ask the user to compile/download in the GUI and report errors.

## Reading

```powershell
python ... export-ai --project P --output-dir OUT --st-mode files
python ... summary --project P
python ... list-pous --project P
python ... list-tasks --project P
python ... extract-st --project P --pou-type program --name "Main" --output "$env:TEMP/Main.st"
python ... list-downlinks --project P
python ... list-slave-objects --project P
python ... export-slave-mappings --project P
python ... list-hardware-tags --project P --pattern "^Motor1_"
```

Graphical logic (LD and FBD, in programs and in function blocks):

```powershell
python ... export-graphic --project P                        # block-level table
python ... export-graphic --project P --level pin            # pin-level table with bindings
python ... export-graphic --project P --pou "底盘控制" --format json
```

## Writing

ST:

```powershell
python ... replace-st --project P --pou-type program --name "Main" --st-file "$env:TEMP/Main.st" --dry-run
```

Attributes on existing entities:

```powershell
python ... set-attrs --project P --kind variable --name "Flag" --attr "DESC=description"
python ... set-attrs --project P --kind hardware-tag --name "Axis1_Status" --attr "ENABLE=YES"
python ... set-attrs --project P --kind user-struct-member --struct "Status" --member "Ready" --attr "DESC=ready flag"
python ... set-attrs --project P --kind pou --pou-type function-block --name "FB_NAME" --attr "DESC=description"
python ... set-attrs --project P --kind block --name "底盘控制" --block "_MODULE0" --attr "DESC=chassis solver"
```

Supported `set-attrs --kind`: `variable`, `hardware-tag`, `user-struct`, `user-struct-member`, `pou`, `pou-var`, `task`, `trig-condition`, `block`, `downlink-port`, `station`, `slave-object`, `slave-mapping`.

Tasks:

```powershell
python ... list-tasks --project P
python ... add-task --project P --cycle 100 --desc "low rate work"
python ... set-attrs --project P --kind task --task-id 4 --attr "CYCLE=10"
python ... set-attrs --project P --kind trig-condition --task-id 16 --attr "VAR=DI0001"
```

The help defines four kinds and one priority order: startup beats event, event
beats cycle, cycle beats main, and a higher priority task preempts a lower one.
A cycle period is the `CYCLE` attribute in milliseconds. An event task holds
exactly one program, which `add-program` and `move-program` enforce. `add-task`
only creates cycle tasks: an event task needs a `TRIG_CONDITION` whose encoding
is only partly known, and the startup task tag has never been observed, so both
are created in the GUI and edited from here afterwards.

POUs:

```powershell
python ... add-program --project P --name "AGV状态机" --desc "整车状态机" --after "配置入口"
python ... move-program --project P --name "安全控制系统" --before "电机速度解算"
python ... add-function-block --project P --name AlarmLatch --desc "报警锁存" `
    --input "Trigger:BOOL:报警条件" --input "Code:UINT:报警码" `
    --output "Active:BOOL:报警激活" --internal "prevReset:BOOL:上周期复位"
python ... add-pou-var --project P --name AlarmLatch --var-section input --var "Reset:BOOL:复位请求"
```

Programs execute in the document order of their task, so `--after` / `--before` /
`--index` are functional, not cosmetic; `move-program` is how a safety stage gets
in front of the stage it constrains. A new program starts with an empty ST
section, ready for `replace-st`. `--lang ld` and `--lang fbd` create an empty
graphical section, which no observed project contains, so the command warns and
the page must be checked in the GUI.

User data types and variables:

```powershell
python ... add-user-struct --project P --name Wheel_Data --desc "wheel data" `
    --member "Enable:BOOL:takes part in control" --member "Angle_cdeg:DINT:angle in 0.01 deg"
python ... add-user-struct-member --project P --struct Wheel_Data --member "Online:BOOL:node online"
python ... add-variable --project P --name Wheel --datatype "Wheel_Data[8]" --desc "eight wheel sets"
python ... add-variable --project P --name SafeStopReq --datatype BOOL --init-value OFF
python ... rebuild-variable-members --project P --name Wheel
python ... remove --project P --kind variable --name Wheel
python ... validate-datatypes --project P --strict
```

`add-variable` writes into `TAGCONFIG`, expands a self-closing container, generates the
whole `VARIABLE_MEMBER` tree for arrays and structs, and refuses names that collide with an
existing variable or hardware tag. After changing a struct, every variable that uses it needs
`rebuild-variable-members`; `validate-datatypes` finds the ones that drifted.

LD/FBD graphical logic:

```powershell
python ... set-pin --project P --pou "底盘控制" --block _MODULE0 --pin V_lin --bind "V_lin_cmd"
python ... set-pin --project P --pou "底盘控制" --block _MODULE0 --pin V_lin --init-value "0.000" --unbind
python ... connect-pins --project P --pou "Main" --from-block _MODULE0 --from-pin Q_H --to-block _MODULE1 --to-pin IN
python ... disconnect-line --project P --pou "Main" --line-name _LINE1
python ... copy-block --project P --reference "D:/samples/official.xcskr" --reference-pou "底盘" `
    --block _MODULE4 --pou "底盘控制" --keep-connections
```

`--bind` writes an operand connection, `--bind-line` attaches the pin to an existing wire, and
`connect-pins` creates the wire plus both end connections. A generated `LINE_POSITION` is only
an approximation of the routing; the logical connection is exact.

Controller and configuration wizard:

```powershell
python ... validate-controller-support --project P
python ... set-node-id --project P --port-id 6 --address 1 --node-id 9
```

`validate-controller-support` catches the failures the rest of the tool cannot
see, because they live in the wizard data rather than in the control scheme:
`GENERAL_CFG@CAR_DRIVER_TYPE` is what the compiler tests against
`Resource/<lang>/Hardware/Common/MRCSeries.xml` before reporting
`0x234 当前控制器不支持当前的底盘驱动类型`. The same command reports the enabled
CANopen command count against `max_canopen_cmd_cnt`, the cycle and event task
counts against their per-model limits, and any feature the model declares
unsupported. Point it at the installation with `--install-dir` or
`KECON_INSTALL_DIR`; an explicit path is never silently replaced by a default.

`set-node-id` exists because a CANopen node id is stored twice, in
`HARDWARE_DEVICE_UPLINK_PORT@ADDRESS` and `HARDWARE_CAN_DEVICE_SLAVE@NODE_ID`.
`set-attrs --kind station` refuses an `ADDRESS` update for that reason.

Static checks:

```powershell
python ... validate-controller-support --project P
python ... validate-st-format --project P --strict
python ... validate-datatypes --project P --strict
python ... validate-canopen-command-ids --project P    # duplicates AND enabled-without-id
python ... validate-hardware-bindings --project P
python ... validate-command-directions --project P
python ... validate-fb-calls --project P
python ... rebuild-user-struct-members --project P
python ... struct-layout --project P --struct S
```

`struct-layout` reports the byte offset the editor shows for each member of a
user data type. Offsets are not stored in the file -- inside a struct a BOOL
takes a whole byte (not a bit) and every member is aligned to its own width, so
the tool recomputes them. Use it to check a layout against the GUI, and to spot
padding worth removing by reordering.

Vendor reference data:

```powershell
python ... resources
python ... datatype-library --name <text>
```

`resources` reports the install directory, library version, function block
library, data type library, help files and configured sample projects, and says
where each value came from. Paths resolve as CLI flag -> environment variable ->
`kecon-resources.json` -> probing; the config file is git-ignored and
`kecon-resources.example.json` is the committed template. Run `resources` first
on an unfamiliar machine.

Official sample projects, when configured, are GUI-authored and therefore the
best available evidence for any question of the form "what shape does the GUI
write?" -- diff against one instead of guessing.

An array member of a user data type must be written expanded, one child element
per array element. A flat member compiles but makes the GUI's user-data-type
editor show a member list and offset column that disagree with the declared type.
`add-user-struct-member` writes the expanded shape, `validate-datatypes` reports
a flat one as `ARRAY_NOT_EXPANDED`, and `rebuild-user-struct-members` repairs it.

`validate-hardware-bindings` catches a command group whose
`HARDWARE_CMD_TAG_NAME` no longer names an existing, enabled channel tag --
the object is still polled but its value reaches no variable.

`validate-command-directions` reads the direction (`EDTYPE`) and send mode
(`MODE`) of every enabled group and cross-checks them against what the ST
actually writes. An enabled *output* command nothing writes feeds the device a
constant forever, and any code parsing the same tag is reading its own buffer.
Expect noise on a project still under construction: an output whose control
program is not written yet looks identical to a mistake, so read the list as a
to-do rather than a verdict.

`validate-fb-calls` checks that every function block call lists its pins in
declaration order. Kecon calls read like named arguments so the order looks
optional; it is not, and getting it wrong fails the build with one FBDError per
call site, worded for FBD, carrying no line number and naming no pin.
Declarations come from the project's own `FUNCTION_BLOCK` entries and from the
vendor library under the install directory (`--install-dir`, or
`KECON_INSTALL_DIR`); without the library only project-defined blocks are
checked and the run says so.

## Text Workspace (round trip through an ordinary editor)

`scripts/xcskr_workspace.py` explodes a project into plain text files, and folds
edited files back. It exists because the xRobotDesigner editor cannot change its
font, size or theme, which makes a large project painful to write in place.

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_workspace.py") export-workspace --project P --workspace W
python ... status-workspace  --project P --workspace W
python ... import-workspace  --project P --workspace W --dry-run
python ... import-workspace  --project P --workspace W
python ... check-workspace   --project P --workspace W --align-script <align_st_comments.py>
```

Layout: `程序/<任务>/NN_<名>.st` (NN is the task-internal execution order, which is
functional -- programs run in document order), `功能块/<名>.st`, `图形` POUs as
`<名>.graph.json` beside their siblings, and regenerated read-only views under
`只读/` (variables, structs, tasks, hardware tags, a pseudo-declaration file and
`符号表.json`).

Four refusals carry the design, and none of them should be worked around:

1. `manifest.json` stores the project's sha256 at export time. If the project
   moved on, `import-workspace` aborts with exit 3 and asks for a fresh export.
   This is the only thing standing between a text edit and silently overwriting
   whatever the GUI saved.
2. `export-workspace` refuses (exit 2) when a workspace file differs from its
   recorded hash, so re-exporting cannot discard unimported edits. `--force`
   overrides deliberately.
3. A renamed or deleted workspace file aborts the import: the manifest maps file
   to POU by path, and a rename silently orphans a POU otherwise.
4. `.graph.json` accepts changes only to pin `bind` / `init` / `negated`, block
   `deactive`, and wires. Adding, deleting or retyping a block, and adding or
   deleting a pin, are refused with exit 4 -- a block TYPE implies a fixed pin
   list the file does not describe, so a new block must come from `copy-block`.

`import-workspace` applies every change to one in-memory string, parses once and
writes once, so a failure part-way leaves the project untouched. An unchanged
round trip is byte-identical (verified against the 5.2 MB IVC300 project).

`check-workspace` prints `file:line:col: severity: message`, which an editor's
problem panel can parse into clickable entries. Only `validate-fb-calls` can
name a line; the project-wide validators are reported as a pass/fail summary.

## Structure Notes

- Projects use bare LF and the tool reads and writes without newline translation, so an edit changes only what it targets. ST line breaks inside the `CONTENT` attribute may be literal LF, `&#10;`, or `&#x0D;&#x0A;`; `replace-st --newline-style auto` keeps whichever the POU or project already uses.
- Main programs live under `CONTROL_SCHEME`, not just a flat POU list. Task discovery accepts any `*_TASK` element so an unrecognized kind is reported rather than dropped.
- `CONTROL_SCHEME` may contain `MAIN_TASK`, `EVENT_TASK`, and `CYCLE_TASK`; each can contain one or more `PROGRAM` nodes, executed in document order.
- `LOGIC_LANG` is `0` for LD, `1` for FBD, `2` for ST, and always agrees with the logic section element present under the POU.
- Hardware variables are `HARDWARE_CHANNEL_TAG`, not ordinary `VARIABLE` nodes.
- A CANopen node id is stored in two attributes that must stay in sync: `HARDWARE_DEVICE_UPLINK_PORT@ADDRESS` and `HARDWARE_CAN_DEVICE_SLAVE@NODE_ID`.
- Configuration wizard data hangs off `HARDWARE_ROBOT_CONTROLLER` as `GENERAL_CFG`, `WIZARD_CONFIG`, `WHEEL_CFG` and `NAVI_CFG`, outside both `CONTROL_SCHEME` and the downlink port tree.
- User data types are `USER_DATA_TYPE/USER_STRUCT/USER_STRUCT_MEMBER` directly under `PROJECT`.
- User variables live under `TAGCONFIG`, not under `GLOBAL_TAG_CONFIG`, which is normally an empty self-closing element.
- Graphical bindings live in `CONTROL_BLOCK_CONNECTION`: `CONNECTION_TYPE="1"` is a variable operand, `CONNECTION_TYPE="2"` is a `CONTROL_LOGIC_LINE` name.
- ST is stored in `SECTION_LOGIC_ST CONTENT`; raw line breaks can be literal LF or XML numeric references.

Read `references/xcskr-structure.md` before changing hardware, task, variable, POU, graphical, or CAN/CANopen structures. Read `references/ld-fbd-st.md` when deciding between ST and a graphical language, or when explaining the difference.

## Guardrails

- Do not full-document reserialize `.xcskr` with ElementTree. It can flatten ST formatting.
- Do not infer physical CAN ports from XML `NAME` alone; compare `ID`, `DISPLAY`, `PHYSICAL_ID`, and exported hardware context.
- Do not disable hardware tags, command groups, or mappings merely to silence a static warning.
- Do not write to the `CONNECTION_PIN` attribute; it is empty in every observed project and carries no binding.
- Do not synthesize a new graphical block: a block `TYPE` implies a fixed pin list the file does not describe. Copy one from a reference project with `copy-block`.
- Interpret CANopen PDO direction from the slave perspective: RPDO/Receive means the slave receives data; TPDO/Transmit means the slave sends data.
- Do not read `CMD_ACCESS_TYPE` as a direction. Direction is `EDTYPE` (1=input/read, 0 or absent=output/write); send mode is `MODE` (0=周期, 1=变化发布, 2=初始化执行, 3=变化加周期). Both are verified against the GUI. An `rw` object may well be an output you are only pretending to read.
- A command on `MODE="1"` fires on value change, so a program that writes a command signature must clear the buffer afterwards or the same command never repeats. A command on `MODE="0"` is resent every cycle, which for an EEPROM-backed object such as `1010:01` is device wear rather than a one-shot.
- Keep an ST function block call's argument list in declaration order. Named arguments do not make order optional (verified): `add-pou-var` appends, so a call that lists new pins in the middle raises one `FBDError` id=769 per call site, with no line number and FBD wording about updating the block instance.
- Run `validate-controller-support` before handing a project back for compilation: the chassis driver type, the CANopen command budget and the task limits are vendor-table constraints that no amount of XML tidiness will satisfy.
- Enabling a CANopen object takes **three** writes, not two: the channel tag's `ENABLE`, the group's `HARDWARE_GROUP_ENABLE`, and a **command id** on `HARDWARE_CAN_CMD@ID`. The GUI hands out the id when you tick the group; `set-attrs --kind cmd-group` does not, so always follow it with `alloc-canopen-command-ids`. Skipping the id costs a build with no clue in it: the compiler blames every program that uses the tag with `文本"<tag>"错误，字符串无法识别` on 第1行, and nothing mentions the command group (verified 2026-08-25: 27 such groups -> 216 errors). Only uniqueness is required; see references/xcskr-structure.md for the numbering the GUI itself uses.
- Use xRobotDesigner GUI compile/download as the final authority. Static XML checks only prove that the edited file is structurally sane enough to hand back for GUI validation.
- Close xRobotDesigner before writing to a project from here. The GUI holds its own in-memory copy and a single save overwrites the whole file, so a CLI edit made while the project is open is lost without any error. An ordinary text editor such as VSCode holds no exclusive lock and does not need to be closed.
- Preserve the self-closing style an element already uses (verified 2026-08-21). V5.1.1.9998-C writes `"/>` and the V5.0 sample projects write `" />`; both parse identically, but rewriting one as the other puts a spurious line in every diff and stops an unchanged round trip from being byte-identical. `replace_section_logic_raw` now keeps whichever the element had.
- Do not expect a bare `>` inside `SECTION_LOGIC_ST CONTENT`. Counted across the IVC300 project, its IVC200 sibling and the official GUI-authored sample: 845 occurrences of `&gt;` and zero bare `>`. Writing a bare `>` parses, but it is not what the GUI produces.
