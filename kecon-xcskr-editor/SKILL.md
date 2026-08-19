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

Static checks:

```powershell
python ... validate-st-format --project P --strict
python ... validate-datatypes --project P --strict
python ... validate-canopen-command-ids --project P
```

## Structure Notes

- Projects use bare LF and the tool reads and writes without newline translation, so an edit changes only what it targets. ST line breaks inside the `CONTENT` attribute may be literal LF, `&#10;`, or `&#x0D;&#x0A;`; `replace-st --newline-style auto` keeps whichever the POU or project already uses.
- Main programs live under `CONTROL_SCHEME`, not just a flat POU list. Task discovery accepts any `*_TASK` element so an unrecognized kind is reported rather than dropped.
- `CONTROL_SCHEME` may contain `MAIN_TASK`, `EVENT_TASK`, and `CYCLE_TASK`; each can contain one or more `PROGRAM` nodes, executed in document order.
- `LOGIC_LANG` is `0` for LD, `1` for FBD, `2` for ST, and always agrees with the logic section element present under the POU.
- Hardware variables are `HARDWARE_CHANNEL_TAG`, not ordinary `VARIABLE` nodes.
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
- Use xRobotDesigner GUI compile/download as the final authority. Static XML checks only prove that the edited file is structurally sane enough to hand back for GUI validation.
