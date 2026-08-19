# LD / FBD / ST in xRobotDesigner Projects

## The Short Version

LD, FBD and ST are three of the IEC 61131-3 programming languages. In a Kecon
project they are **three notations for the same POU concept**, not three
different runtimes. A POU declares which notation it uses in `LOGIC_LANG`, and
stores its body in the matching section element:

| `LOGIC_LANG` | Language | Section element | How the body is stored |
|---|---|---|---|
| `0` | LD — Ladder Diagram | `SECTION_LOGIC_LD` | XML tree: blocks, pins, wires |
| `1` | FBD — Function Block Diagram | `SECTION_LOGIC_FBD` | XML tree: blocks, pins, wires |
| `2` | ST — Structured Text | `SECTION_LOGIC_ST` | one `CONTENT` attribute holding source text |

The mapping was verified against the official Kecon sample projects: every POU's
`LOGIC_LANG` agrees with the section tag actually present under it. Always trust
the section tag; treat `LOGIC_LANG` as a hint.

## ST — Structured Text

A Pascal-like textual language:

```pascal
IF EStopOk AND NOT LidarBlocked[0] THEN
    V_lin := RC_Speed * 0.001;
ELSE
    V_lin := 0.0;
END_IF;
```

For this tool ST is the easy case: the whole program body is a **string** in
`SECTION_LOGIC_ST/@CONTENT`. That is why `extract-st` and `replace-st` can do
full read/write — replacing a program is replacing one attribute value. The only
subtlety is that line breaks inside that attribute may be literal LF or the
numeric reference `&#10;`, which is why the tool patches the raw XML span
instead of reserializing the document.

ST is the right choice for state machines, arithmetic, loops, and anything you
want to diff or review as text.

## LD — Ladder Diagram

Ladder is drawn as rungs between two power rails: contacts on the left, coils
and function boxes on the right. It comes from relay logic, so it reads
naturally for interlocks, permissives and simple sequencing:

```text
 |   EStopOk   LidarFront                       RunEnable   |
 |----| |---------|/|----------------------------( )--------|
```

In XML, a ladder rung is **not** stored as a picture. It is stored as a graph:

* `CONTROL_LOGIC_BLOCK` — one element per box or contact. `TYPE` is what it does
  (`B_CONTACT`, `S_CONTACT`, `OPEN_CONTACT`, `MOV`, `GT`, `OR`, `NOT`, `ABS`,
  or a named library block such as `EightDifferentialChassis`). `NAME` is a
  generated id (`_MODULE0`, `_LDELEMENT73`), `RECT_POSITION` is its rectangle.
* `BLOCK_PIN_INPUT` / `BLOCK_PIN_OUTPUT` — the pins of that block, with
  `DATATYPE`, `INIT_VALUE`, `NEGATED`, `ENABLED`.
* `CONTROL_LOGIC_LINE` — one wire, with a `NAME` (`_LINE0`) and a
  `LINE_POSITION` polyline of three points.
* `CONTROL_BLOCK_CONNECTION` — a child of a pin saying what that pin is tied to.

## FBD — Function Block Diagram

FBD uses the same XML vocabulary as LD — the same blocks, pins, wires and
connections — but drops the power rails and the contact/coil metaphor. It is
signal flow: boxes with inputs on the left, outputs on the right, wires between
them. It suits data-path work: kinematics, scaling, filters, and calling large
library blocks with many pins.

Practically, in this file format **LD and FBD differ only by the section tag**.
That is why `export-graphic`, `set-pin`, `connect-pins`, `disconnect-line` and
`copy-block` all work on both without special-casing.

## How a Pin Gets Its Value

This is the part that matters when editing. A pin can be in three states:

1. **Unconnected** — no `CONTROL_BLOCK_CONNECTION` child. The pin uses its own
   `INIT_VALUE` as a literal constant.
2. **Bound to an operand** — `CONNECTION_TYPE="1"`, and `CONNECTION_VALUE` is a
   symbol name: a global `VARIABLE`, a `HARDWARE_CHANNEL_TAG`, a local variable
   of the owning FUNCTION_BLOCK, or a member path such as `rcCmd.RUN_PRESSED`
   or `StatusWords[0]`.
3. **Wired to another block** — `CONNECTION_TYPE="2"`, and `CONNECTION_VALUE` is
   the `NAME` of a `CONTROL_LOGIC_LINE` in the same section. The wire is
   two-ended: the source output pin and the target input pin both carry a
   `CONNECTION_TYPE="2"` connection naming the *same* line.

```xml
<BLOCK_PIN_INPUT DATATYPE="UINT" NAME="IN" INIT_VALUE="0" ...>
  <CONTROL_BLOCK_CONNECTION CONNECTION_TYPE="1" CONNECTION_VALUE="StatusWords[0]"/>
</BLOCK_PIN_INPUT>
<BLOCK_PIN_OUTPUT DATATYPE="BYTE" NAME="Q_H" INIT_VALUE="0" ...>
  <CONTROL_BLOCK_CONNECTION CONNECTION_TYPE="2" CONNECTION_VALUE="_LINE0"/>
</BLOCK_PIN_OUTPUT>
```

Note: some V5.1 FBD pins also carry a `CONNECTION_PIN` attribute. It is empty in
every project inspected so far, including the official samples, and it never
holds a binding. Do not write to it; use `CONTROL_BLOCK_CONNECTION`.

Line names are scoped **per section**, so `_LINE0` may exist once in every
program without conflict.

## Which One to Use

* **ST** for logic you want to reason about as text: state machines, math,
  loops, protocol handling. It is also the only language this tool can author
  from nothing, since the body is just a string.
* **LD** for safety interlocks and permissive chains, where electricians and
  commissioning staff expect to read a ladder.
* **FBD** for signal flow and for driving large library blocks such as the
  chassis solver, where wiring 60 pins is clearer than 60 assignments.

Mixing them within one project is normal: the official Kecon samples use LD for
the chassis page, ST for the state machine, and FBD where a single library block
does the work.

## What This Tool Can and Cannot Do

| Operation | ST | LD / FBD |
|---|---|---|
| Read the full body | yes | yes (`export-graphic`) |
| Replace the whole body | yes (`replace-st`) | no |
| Change one element's attributes | n/a | yes (`set-attrs --kind block`, `set-pin`) |
| Bind a pin to a variable | n/a | yes (`set-pin --bind`) |
| Wire two pins together | n/a | yes (`connect-pins`) |
| Remove a wire | n/a | yes (`disconnect-line`) |
| Add a block | n/a | only by copying one (`copy-block`) |
| Create a POU from nothing | no | no |

Creating a *new* graphical block from nothing is deliberately not supported:
each block `TYPE` has a fixed pin list that the GUI knows and the file format
does not describe. Copy a known-good block from a reference project instead —
the official samples under the xRobotDesigner help folder are a good source.
