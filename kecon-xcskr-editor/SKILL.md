---
name: kecon-xcskr-editor
description: Use when Codex needs to inspect, summarize, export, or safely modify generic Kecon/xRobotDesigner .xcskr PLC projects, including hardware configuration, variables, user data types, function blocks, control-scheme tasks, ST code, CAN/CANopen, Modbus, and GBK XML.
---

# Kecon xRobotDesigner `.xcskr` Editor

Resolve the directory containing this `SKILL.md` from the available-skills catalog and assign
its absolute path to `$keconSkillDir` before running the examples. Do not assume a fixed drive,
username, or Codex home directory.

## Core Workflow

1. Search the curated help first when the task involves Kecon concepts, built-in function blocks, communication setup, navigation, chassis, safety, or model parameters:

```powershell
python (Join-Path $keconSkillDir "scripts\kecon_help.py") search "关键词"
```

2. Treat `.xcskr` as GBK XML. Read/write with `encoding='gbk'`.
3. Export a compact AI package before reasoning about the project:

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") export-ai --project "D:/path/project.xcskr" --output-dir "$env:TEMP/kecon_ai_pack" --st-mode files
```

4. Read `index.json` first, then open only the needed package files:
   - `hardware.json`: downlink ports, stations, hardware variables, CANopen slave objects/mappings.
   - `programs.json`: programs under `CONTROL_SCHEME` tasks.
   - `function-blocks.json`: custom FB interfaces and ST file paths.
   - `variables.json`: custom/global variables.
   - `user-data-types.json`: user structs and members.
   - `st/`: ST sources split into separate files.
   - For LD/FBD graphical programs, export block/pin/line structure directly instead of hand-reading XML:
     `python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") export-ld --project "D:/path/project.xcskr" --program "Main" --format json`
5. Prefer structured commands over raw XML editing. Use `replace-st` for ST, `set-attrs` for attributes, and `copy-pou` for copying an existing POU from a reference project.
6. Write commands create timestamped backups by default. Use `--dry-run` first for risky edits.
7. After editing, rerun `export-ai`, `validate-st-format --strict`, and relevant static validators. Do not drive xRobotDesigner command-line compile yourself; ask the user to compile/download in the GUI and report errors.

## Read/Write Commands

Export:

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") export-ai --project "D:/path/project.xcskr" --output-dir "$env:TEMP/kecon_ai_pack" --st-mode files
```

Extract or replace ST:

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") extract-st --project "D:/path/project.xcskr" --pou-type program --name "Main" --output "$env:TEMP/Main.st"
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") replace-st --project "D:/path/project.xcskr" --pou-type program --name "Main" --st-file "$env:TEMP/Main.st" --dry-run
```

Set structured attributes without hand-editing XML:

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") set-attrs --project "D:/path/project.xcskr" --kind variable --name "Flag" --attr "DESC=description"
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") set-attrs --project "D:/path/project.xcskr" --kind hardware-tag --name "Axis1_Status" --attr "ENABLE=YES"
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") set-attrs --project "D:/path/project.xcskr" --kind user-struct-member --struct "Status" --member "Ready" --attr "DESC=ready flag"
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") set-attrs --project "D:/path/project.xcskr" --kind pou --pou-type function-block --name "FB_NAME" --attr "DESC=description"
```

Supported `set-attrs --kind`: `variable`, `hardware-tag`, `user-struct`, `user-struct-member`, `pou`, `pou-var`, `downlink-port`, `station`, `slave-object`, `slave-mapping`.

Static checks:

```powershell
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") validate-st-format --project "D:/path/project.xcskr" --strict
python (Join-Path $keconSkillDir "scripts\xcskr_tool.py") validate-canopen-command-ids --project "D:/path/project.xcskr"
```

## Structure Notes

- Main programs live under `CONTROL_SCHEME`, not just a flat POU list.
- `CONTROL_SCHEME` may contain `MAIN_TASK`, `EVENT_TASK`, and `CYCLE_TASK`; each can contain one or more `PROGRAM` nodes.
- Hardware variables are `HARDWARE_CHANNEL_TAG`, not ordinary `VARIABLE` nodes.
- User data types are usually `USER_DATA_TYPE/USER_STRUCT/USER_STRUCT_MEMBER`.
- Custom/global variables are usually under `GLOBAL_TAG_CONFIG`.
- ST is stored in `SECTION_LOGIC_ST CONTENT`; raw line breaks can be literal LF or XML numeric references.

Read `references/xcskr-structure.md` before changing hardware, task, variable, POU, or CAN/CANopen structures.

## Guardrails

- Do not full-document reserialize `.xcskr` with ElementTree. It can flatten ST formatting.
- Do not infer physical CAN ports from XML `NAME` alone; compare `ID`, `DISPLAY`, `PHYSICAL_ID`, and exported hardware context.
- Do not disable hardware tags, command groups, or mappings merely to silence a static warning.
- Interpret CANopen PDO direction from the slave perspective: RPDO/Receive means the slave receives data; TPDO/Transmit means the slave sends data.
- Use xRobotDesigner GUI compile/download as the final authority. Static XML checks only prove that the edited file is structurally sane enough to hand back for GUI validation.
