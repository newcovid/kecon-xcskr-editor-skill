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
agent picks it up from `SKILL.md`. `agents/openai.yaml` is the Codex-side
manifest for the same folder: a display name, a one-line description and the
default prompt Codex offers when the skill is invoked by name.

## What it can do

| Area | Read | Write |
|---|---|---|
| Project / task / POU overview | `summary`, `list-pous`, `export-ai` | — |
| Control scheme tasks | `list-tasks` | `add-task` (cycle only), `set-attrs --kind task` / `--kind trig-condition` |
| Programs and function blocks | `list-pous`, `export-ai` | `add-program`, `move-program`, `add-function-block`, `add-pou-var`, `copy-pou`, `rename-pou`, `remove` |
| ST program bodies | `extract-st` | `replace-st` |
| LD / FBD graphical logic | `export-graphic` | `set-pin`, `connect-pins`, `disconnect-line`, `copy-block`, `set-attrs --kind block` |
| User data types | `export-ai`, `struct-layout` | `add-user-struct`, `add-user-struct-member`, `remove` |
| User variables | `export-ai` | `add-variable`, `rebuild-variable-members`, `remove` |
| Hardware config, CANopen, Modbus | `list-downlinks`, `list-slave-objects`, `export-slave-mappings`, `list-hardware-tags` | `set-attrs` on existing entities, `set-node-id`, `rename-hardware-tag`, `alloc-canopen-command-ids` |
| Static checks | `validate-st-format`, `validate-datatypes`, `validate-controller-support`, `validate-canopen-command-ids`, `validate-slave-objects`, `validate-hardware-bindings`, `validate-command-directions`, `validate-fb-calls`, `validate-desc-length`, `validate-desc-drift`, `validate-array-index`, `validate-comment-balance`, `validate-modbus-mapping` | `rebuild-user-struct-members` |
| Text workspace | `export-workspace`, `status-workspace`, `check-workspace` | `import-workspace` |
| Vendor reference data | `resources`, `datatype-library` | — |
| Vendor help | `kecon_help.py search` / `show` / `list` | `kecon_help.py index` |

Not supported by design: creating a task, a hardware device or a graphical
block from nothing. Those carry structure the file format does not describe (a
block `TYPE` implies a fixed pin list, for example). Create the empty shell in
the GUI, or copy a known-good one from a reference project with `copy-block`.

Edits are byte-exact everywhere they are not aimed: the tool reads and writes
without newline translation, matches the GUI attribute set and ordering, and
takes its indentation step from the target file.

## Text workspace

`scripts/xcskr_workspace.py` is the other way to work on a project: it explodes
the single XML document into a directory of plain text files, so programs can be
edited in an ordinary editor, and folds the edited files back afterwards. The
xRobotDesigner editor cannot change its font, size or theme, which is what makes
this worth doing on a large project.

```bash
python scripts/xcskr_workspace.py export-workspace --project proj.xcskr --workspace ws
python scripts/xcskr_workspace.py status-workspace --project proj.xcskr --workspace ws
python scripts/xcskr_workspace.py import-workspace --project proj.xcskr --workspace ws --dry-run
python scripts/xcskr_workspace.py import-workspace --project proj.xcskr --workspace ws
python scripts/xcskr_workspace.py check-workspace  --project proj.xcskr --workspace ws
```

The layout is `程序/<task>/NN_<name>.st` (`NN` is the task-internal execution
order, which is functional -- programs run in document order),
`功能块/<name>.st`, and graphical POUs as `<name>.graph.json` beside their
siblings. A `.graph.json` accepts changes to pin `bind` / `init` / `negated`,
block `deactive` and wires; adding, deleting or retyping a block is refused,
because a block `TYPE` implies a fixed pin list the file does not describe.

`只读/` holds regenerated views -- variables, structs, tasks, hardware tags, a
pseudo-declaration file and `符号表.json`. They are export products: edit them
and nothing happens, because import ignores them.

`manifest.json` records the project's sha256 at export time and every workspace
file's hash. If the project moved on -- someone opened the GUI and saved --
`import-workspace` refuses and asks for a fresh export, which is the only thing
standing between a text edit and silently overwriting the GUI's work. Export
refuses in the other direction too, so re-exporting cannot discard edits that
were never imported. `import-workspace` builds the whole result in memory and
writes once, so a failure part-way leaves the project untouched.

`check-workspace` runs the static validators and prints
`file:line:col: severity: message`, which an editor's problem panel can parse
into clickable entries.

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

The XML conventions this tool relies on are written down with the evidence
behind each one: official sample comparison, GUI observation, production-project
reproduction, or what the compiler accepts and refuses. Judge a fact by the
method named beside it; anything unmarked is inference. The details, including
where user variables actually live and how a graphical pin records what it is
bound to, are written up in:

- `references/xcskr-structure.md` — element placement, attribute sets, safe write model
- `references/ld-fbd-st.md` — how LD, FBD and ST differ, and how each is stored
- `references/kecon-help-kb.md` — curated vendor notes, searched by `kecon_help.py`

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

## Vendor reference resources

The tool reads the xRobotDesigner function block library, data type library,
help files and (optionally) official sample projects. None of those paths are
hard-coded -- they differ per machine, install language and version.

Resolution order: CLI flag -> environment variable -> `kecon-resources.json` ->
probing. Copy `kecon-resources.example.json` to `kecon-resources.json` and edit
it; that file is git-ignored because the paths are per-machine and often
personal. Run `python scripts/xcskr_tool.py resources` to see what resolved and
from where.
