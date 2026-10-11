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
| `ack.ck` | Drive a running Creation Kit like a level designer: load plugins, open cells, select objects, set exact position/rotation/scale, move the camera (zoom, pan, orbit, or look from a bearing/elevation/distance), screenshot the render window, generate navmesh, compact form IDs, save. |

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

## Driving the Creation Kit (`ack.ck`)

```
python -m ack ck load "MyMod.esp" --active "MyMod.esp"   # File > Data: exactly these plugins
python -m ack ck cell MyInteriorCell                      # open it in the render window
python -m ack ck refs                                     # references in the cell
python -m ack ck ref MyChestRef                           # read position / rotation / scale
python -m ack ck ref MyChestRef --rot _ _ 180             # set them ('_' keeps an axis)
python -m ack ck select MyChestRef                        # select it and fly the camera there
python -m ack ck camera zoom -40 | pan DX DY | orbit DX DY | top | bright
python -m ack ck camera look 135 20 900                  # view the selection from bearing 135 (SE), 20 deg up, 900 away
python -m ack ck shot out.png                             # screenshot of the render window
python -m ack ck navmesh                                  # Recast navmesh for the cell, then finalize
python -m ack ck compact                                  # Compact Active File Form IDs
python -m ack ck save
```

Menus, lists and buttons are driven with window messages. The render window and the Reference dialog only
respond to a person, so those commands use real mouse and keyboard input: they bring the Creation Kit to the front
and move the cursor. **Only run them when nobody is using the PC.** Every edit is checked before it is applied:
`ref` opens the object's Reference dialog by clicking it in the render window and refuses to type anything unless
the dialog shows the requested editor ID.

Things the Creation Kit does that the tools work around (details in `ack/ck/session.py`):
- It is not DPI-aware: coordinates posted to it are scaled by the screen's DPI factor.
- Its render window only draws while visible, so screenshots copy the screen.
- **Set as Active File** toggles, and File > Data opens hidden and remembers the last session's ticks.
- New forms get IDs from its own counter, which can run past an ESL's 0xFFF; run `compact` after creating forms.
- Saving with extra plugins loaded can add their masters to the active file (through the navmesh index, NAVI).
- The camera has no numeric controls. `camera look` orbits and zooms in a closed loop, reading the camera position
  back from the status bar: it finds the orbit pivot from a few probing moves, then corrects until the bearing,
  elevation and distance match. It starts from the top view and tilts down the south side, because orbiting over
  a pole leaves the picture upside down.
- Recast navmesh generation works on the selection when there is one (and fails with "No Triangles Generated" for
  a small object): clear the selection first to cover the whole cell.

## How unattended xEdit runs stay safe

xEdit shows dialogs (startup notices, "save changed files?") that normally need a click. The watcher in
`ack/xedit/dialogs.py` handles them with an **allowlist** (`ack/xedit/rules.json`):

- A dialog is only acted on if a rule matches its title, class, text and buttons. Rules are added only after
  a person (or agent) has reviewed that exact dialog.
- **Unknown dialogs are never clicked.** The watcher records their title, controls and a screenshot to the run
  folder (`unknown_*.json` / `.bmp`) and leaves them alone. If one blocks the run, it times out and xEdit is
  terminated without saving.
- **Saving is decided by the run, not by a dialog.** In script mode xEdit saves changed plugins automatically
  when it closes normally, without asking (it keeps the previous version in `Data/FO4Edit Backups`). So `--save`
  runs close xEdit normally, and read-only runs terminate it once the script is done, which can never write
  anything.
- Rules can still be limited to editing runs (`"when": "save"`) for any prompt that only makes sense there.
- Buttons are pressed with Windows messages, not the mouse: it works in the background and never touches
  other windows.

To teach it a new dialog: run once, look at the captured screenshot, then add a rule to `rules.json`, e.g.

```json
{"name": "Module Selection", "title": "Module Selection", "cls": "TfrmModuleSelect", "buttons": ["OK", "Load"], "action": "click:OK"}
```

## Roadmap

- Record editing helpers on top of `ack.plugin` (copy/create records, FormID allocation, master handling),
  so common edits no longer need xEdit at all; xEdit stays as the independent validator.
- An MCP server exposing these tools to any agent.
- `ack.ck`: placing new objects from the Object Window by drag and drop, and gizmo moves in the render window.
