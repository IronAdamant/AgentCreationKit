# AgentCreationKit

Tools that let AI coding agents (Claude Code, Grok Build, ...) work on Bethesda game mods without a human
clicking through the Creation Kit or FO4Edit. Built while restoring a real Fallout 4 mod
([Custom Legendary Modifications](https://www.nexusmods.com/fallout4/mods/5565)), so every feature exists
because a real modding task needed it.

Python 3.10+, Windows, no third-party dependencies.

## What it does

| Module | Purpose |
|---|---|
| `ack.xedit` | Run FO4Edit/xEdit Pascal scripts unattended: generates the plugin list, launches xEdit, watches its windows, answers only allowlisted dialogs, closes it when the script is done, and returns a report. |
| `ack.plugin` | Read and write plugin files (`.esp/.esm/.esl`) directly. Lossless: unmodified data is written back byte-for-byte (verified on `Fallout4.esm`, 1.5M records). |
| `ack.archive` | Extract files from BA2 archives (general and texture archives; textures come out as `.dds`). |
| `ack.nif` | Inspect NIF models and patch length-prefixed strings (e.g. texture paths) while keeping the block table valid. |

## Setup

```
copy config.example.json config.local.json   # then set your game, xEdit and work paths
python -m unittest discover -s tests -t .
```

## Usage

```
python -m ack xedit scripts                                  # list bundled xEdit scripts
python -m ack xedit run check_errors "MyMod.esp"             # read-only run
python -m ack xedit run clean_masters "MyMod.esp" --save     # editing run
python -m ack plugin info "D:/.../Data/MyMod.esp"
python -m ack ba2 extract "D:/.../Fallout4 - Meshes.ba2" "meshes\effects\laser*" --out extracted
```

## How unattended xEdit runs stay safe

xEdit shows dialogs (startup notices, "save changed files?") that normally need a click. The watcher in
`ack/xedit/dialogs.py` handles them with an **allowlist** (`ack/xedit/rules.json`):

- A dialog is only acted on if a rule matches its title, class, text and buttons. Rules are added only after
  a person (or agent) has reviewed that exact dialog.
- **Unknown dialogs are never clicked.** The watcher records their title, controls and a screenshot to the run
  folder (`unknown_*.json` / `.bmp`) and leaves them alone. If one blocks the run, it times out and xEdit is
  terminated without saving.
- Rules can be limited to editing runs (`"when": "save"`), so a read-only run can never confirm a save.
- Buttons are pressed with Windows messages, not the mouse: it works in the background and never touches
  other windows.

To teach it a new dialog: run once, look at the captured screenshot, then add a rule such as

```json
{"name": "Save prompt", "title": "Save changed files.*", "buttons": ["OK"], "action": "click:OK", "when": "save"}
```

## Roadmap

- Record editing helpers on top of `ack.plugin` (copy/create records, FormID allocation, master handling),
  so common edits no longer need xEdit at all; xEdit stays as the independent validator.
- An MCP server exposing these tools to any agent.
