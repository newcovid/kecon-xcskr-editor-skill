# kecon-xcskr-editor

Inspect and safely edit Kecon / xRobotDesigner `.xcskr` PLC projects from the
command line. Pure Python standard library, no dependencies.

`.xcskr` is a GBK-encoded XML document. This tool parses it for reading, but
edits it by patching raw XML spans, because re-serializing the whole document
through an XML library flattens the ST source stored inside an attribute and the
IDE then shows an empty program.

## Install

Copy the folder somewhere and call the script directly:

```bash
python scripts/xcskr_tool.py --help
```

As a Claude Code / Codex skill, place the folder under `.claude/skills/` and the
agent picks it up from `SKILL.md`.

## What it can do

| Area | Read | Write |
|---|---|---|
| Project / task / POU overview | `summary`, `list-pous`, `export-ai` | — |
| Programs and function blocks | `list-pous`, `export-ai` | `add-program`, `move-program`, `add-function-block`, `add-pou-var`, `copy-pou` |
| ST program bodies | `extract-st` | `replace-st` |
| LD / FBD graphical logic | `export-graphic` | `set-pin`, `connect-pins`, `disconnect-line`, `copy-block`, `set-attrs --kind block` |
| User data types | `export-ai` | `add-user-struct`, `add-user-struct-member`, `remove` |
| User variables | `export-ai` | `add-variable`, `rebuild-variable-members`, `remove` |
| Hardware config, CANopen, Modbus | `list-downlinks`, `list-slave-objects`, `export-slave-mappings`, `list-hardware-tags` | `set-attrs` on existing entities |
| Static checks | `validate-st-format`, `validate-datatypes`, `validate-canopen-command-ids` | — |
| Vendor help | `kecon_help.py search` / `show` / `list` | `kecon_help.py index` |

Not supported by design: creating a task, a hardware device or a graphical
block from nothing. Those carry structure the file format does not describe (a
block `TYPE` implies a fixed pin list, for example). Create the empty shell in
the GUI, or copy a known-good one from a reference project with `copy-block`.

Edits are byte-exact everywhere they are not aimed: the tool reads and writes
without newline translation, matches the GUI attribute set and ordering, and
takes its indentation step from the target file.

## Vendor help lookup

`scripts/kecon_help.py` searches two sources: a small curated knowledge base kept
in `references/`, and a local index built from the xRobotDesigner CHM that ships
with the IDE. The CHM is vendor material and is never copied into this
repository; only the machine-local cache holds its text.

```bash
python scripts/kecon_help.py status
python scripts/kecon_help.py index --chm "D:/KCSmart/xRobotDesigner/Resource/chs/HelpFile/xCSStudioHelpFile.chm"
python scripts/kecon_help.py search "八差速 底盘"
python scripts/kecon_help.py show 八差速_舵轮总成底盘
```

Indexing uses the Windows built-in `hh.exe -decompile`, so there is nothing to
install. Word-exported help tables are flattened to pipe separated lines, which
keeps block parameter tables readable, and the `.hhc` table of contents supplies
each topic's real name and breadcrumb. The cache defaults to
`~/.kecon-xcskr-editor/help` and moves with `--cache-dir` or the
`KECON_HELP_CACHE` environment variable. An already decompiled tree can be
indexed with `--from-dir`, which is also how the tests run without a CHM.

## Typical session

```bash
# 1. get an AI-readable package of the whole project
python scripts/xcskr_tool.py export-ai --project proj.xcskr --output-dir /tmp/pack --st-mode files

# 2. define a data type and a variable that uses it
python scripts/xcskr_tool.py add-user-struct --project proj.xcskr --name Wheel_Data \
    --member "Enable:BOOL:takes part in control" --member "Angle_cdeg:DINT:0.01 deg"
python scripts/xcskr_tool.py add-variable --project proj.xcskr --name Wheel --datatype "Wheel_Data[8]"

# 3. wire the chassis block in an FBD page
python scripts/xcskr_tool.py export-graphic --project proj.xcskr --level pin
python scripts/xcskr_tool.py set-pin --project proj.xcskr --pou Chassis --block _MODULE0 \
    --pin V_lin --bind V_lin_cmd

# 4. check, then compile in the GUI
python scripts/xcskr_tool.py validate-datatypes --project proj.xcskr --strict
python scripts/xcskr_tool.py validate-st-format --project proj.xcskr --strict
```

Every write command takes a timestamped backup unless `--no-backup` is given,
supports `--dry-run`, and re-parses the result before saving.

## Format notes

The XML conventions this tool relies on were cross-checked against official
Kecon sample projects, not guessed from one file. The details, including where
user variables actually live and how a graphical pin records what it is bound
to, are written up in:

- `references/xcskr-structure.md` — element placement, attribute sets, safe write model
- `references/ld-fbd-st.md` — how LD, FBD and ST differ, and how each is stored

## Tests

```bash
python -m unittest discover -s tests
```

The suite builds a synthetic project fixture covering ST, LD and FBD programs, a
function block, user data types, hardware tags and CANopen objects, and exercises
every read and write command against it.

## Final authority

Static XML checks only prove the edited file is structurally sane. Compiling and
downloading in xRobotDesigner is the real validation; always hand the project
back for a GUI compile after editing.
