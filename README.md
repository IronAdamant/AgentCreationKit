# AgentCreationKit

Let your AI coding agent (Claude Code, Codex, Grok Build, ...) build Bethesda game mods: run xEdit scripts
unattended, drive the Creation Kit (load, open cells, place and move objects, generate navmesh, save), read and
write plugins, compile Papyrus and pack BA2 archives, with or without Mod Organizer 2. Built while restoring and
updating real Fallout 4 mods ([Custom Legendary Modifications](https://www.nexusmods.com/fallout4/mods/5565),
Sandbox Room), so every feature exists because a real modding task needed it.

**For modders who already work with an AI agent.** You describe the change; the agent makes it with these tools and
checks the result. Setup is done by the agent too: it asks you for what it cannot find.

## Quick start

```
git clone https://github.com/IronAdamant/AgentCreationKit
cd AgentCreationKit
python -m ack doctor
```

Then tell your agent: *"Read AGENTS.md and set up AgentCreationKit for my game."*
[AGENTS.md](AGENTS.md) is its manual (Claude Code loads it through CLAUDE.md): setup, the safety rules, and which
command does what.

Needs Windows, Python 3.10+ (nothing else to install), the game, xEdit (FO4Edit), and the Creation Kit for the
CK, Papyrus and archive commands.

## Built not to lose your work

- A Creation Kit session always ends **closed without saving**, even when a step fails; ack never closes a CK you
  opened yourself (it may hold your unsaved work).
- xEdit runs are **read-only unless asked to save**, and a saving run refuses to start while a Creation Kit that
  could save over the same plugin is open.
- **Unknown dialogs are never clicked**: they are captured with a screenshot for review.
- Every Creation Kit save is **checked**: masters it added, navmeshes missing from the navmesh index, ESL form IDs
  out of range.

## Status

| | Fallout 4 | Skyrim Special Edition |
|---|---|---|
| xEdit runs, plugin read/write and checks | verified | profile only, untried |
| Creation Kit automation | verified | not yet (needs checking against its CK) |
| Papyrus compile, BA2 packing | verified | compile untried; Skyrim uses BSA, not BA2 |
| Mod Organizer 2 | read-only xEdit runs verified; saving runs and the CK untried | untried |
| Vortex | deploys into Data, so it should need nothing; untried | untried |

What differs between games lives in one place (`ack/games.py`), so other Creation Engine games are a profile away
(see [Other games](#other-games)).

## What it does

| Module | Purpose |
|---|---|
| `ack.xedit` | Run FO4Edit/xEdit Pascal scripts unattended: generates the plugin list, launches xEdit, watches its windows, answers only allowlisted dialogs, closes it when the script is done, and returns a report. |
| `ack.plugin` | Read and write plugin files (`.esp/.esm/.esl`) directly. Lossless: unmodified data is written back byte-for-byte (verified on `Fallout4.esm`, 1.5M records). |
| `ack.plugin.check` | Check a plugin for what Creation Kit saves break: masters added since before, navmeshes missing from the navmesh index (NAVI), light-plugin (ESL) IDs out of range. Reads only the plugin. |
| `ack.games` | Per-game facts: official masters, xEdit and CK names, My Games folder, light-plugin ID ranges. |
| `ack.archive` | Extract files from BA2 archives (general and texture archives; textures come out as `.dds`); pack a mod's archives with Archive2, stamped so every PC game version reads them; show an archive's version, files and texture tile modes. |
| `ack.papyrus` | Compile a mod's Papyrus scripts with the Creation Kit's compiler, against the vanilla sources only (F4SE's only when asked). |
| `ack.mo2` | Mod Organizer 2: run xEdit and the CK inside MO2's virtual Data folder, and find which mod a file comes from. |
| `ack.doctor` | Check the setup and say how to fix it; without a config, find the game folders and MO2 instances to fill one in. |
| `ack.nif` | Inspect NIF models and patch length-prefixed strings (e.g. texture paths) while keeping the block table valid. |
| `ack.ck` | Drive a running Creation Kit like a level designer: load plugins, open cells, select objects, set exact position/rotation/scale, move the camera (zoom, pan, orbit, or look from a bearing/elevation/distance), screenshot the render window, generate navmesh, compact form IDs, save. |

## Setup

```
copy config.example.json config.local.json   # then set your game, xEdit and work paths ("mo2" for Mod Organizer 2)
python -m ack doctor                         # checks everything; run it until it says "ready"
python -m unittest discover -s tests -t .
```

Run ack from a clone of this repo: it reads `config.local.json` from the repo root.

## Usage

```
python -m ack xedit scripts                                  # list bundled xEdit scripts
python -m ack xedit run check_errors "MyMod.esp"             # read-only run
python -m ack xedit run clean_masters "MyMod.esp" --save     # editing run
python -m ack plugin info "D:/.../Data/MyMod.esp"
python -m ack plugin check "MyMod.esp" --masters Fallout4.esm DLCCoast.esm   # exit code 1 on any error
python -m ack navmesh "MyMod.esp" --island y-1536 --covered 1100,1100,2250,1750   # check a generated navmesh
python -m ack ba2 extract "D:/.../Fallout4 - Meshes.ba2" "meshes\effects\laser*" --out extracted
python -m ack where "MyMod.esp"                              # the real path (with MO2: the mod it comes from)
python -m ack papyrus compile source/User --out data/Scripts # every script under source/User; --debug keeps traces
python -m ack ba2 pack stage "dist/MyMod - Main.ba2"         # stage/ is laid out like Data; all but Textures
python -m ack ba2 pack stage "dist/MyMod - Textures.ba2" --textures
python -m ack ba2 info "dist/MyMod - Textures.ba2"           # version, file count, tile modes (8 = PC layout)
```

## Mod Organizer 2

MO2 keeps each mod in its own folder and merges them into Data only for the programs it starts, so on their own
xEdit and the Creation Kit cannot see a plugin installed through MO2. Add the instance to `config.local.json`:

```json
"mo2": {"exe": "D:/MO2/ModOrganizer.exe", "instance": "Fallout 4", "profile": "Default"}
```

`instance` is a global instance's name, or the path of an instance folder; `profile` defaults to the instance's
selected one. ack then starts xEdit and the CK through `ModOrganizer.exe run`, so they see the profile's mods, and
looks files up the way MO2 does (overwrite, then the enabled mods from the highest priority, then Data), for
`plugin check`, `where` and the CK's save check. Files the tools create go to MO2's overwrite folder; an xEdit
save run reports where the plugin is afterwards.

- Verified: read-only xEdit runs on a plugin that exists only in an MO2 mod folder (MO2 2.5.2).
- Not yet verified: xEdit saving runs and the Creation Kit through MO2 (check where the file lands the first time);
  portable instances (MO2 is started without `-i`, so it opens the instance it used last).
- xEdit writes its cache (`FO4Edit Cache`) into overwrite when run through MO2.
- Vortex deploys mods into the real Data folder, so it needs no setting.

## Driving the Creation Kit (`ack.ck`)

Do as much as possible in xEdit (records, references, positions: `apply_edits`'s `ref.move` sets what the
Reference dialog does), and use the Creation Kit only for what needs it: navmesh, placing things by eye, looking.
Then bring the plugin back through xEdit for masters and IDs.

The safest way is a steps file run as one session, which **always ends with the CK closed without saving**, even
when a step fails:

```
# navmesh.txt: one ck command per line
load "MyMod.esp" --active "MyMod.esp"
cell MyInteriorCell
navmesh
save --masters Fallout4.esm
```
```
python -m ack ck run navmesh.txt
```

Single commands, for working step by step (end with `ck close`):

```
python -m ack ck launch                                   # start it; ack records it as its session
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
python -m ack ck save                                     # File > Save, then check the saved plugin
python -m ack ck close                                    # close WITHOUT saving
```

### How Creation Kit sessions stay safe

- **A CK left open is a hazard**: it holds its own copy of the plugins, and one save from it writes that stale copy
  over anything built since. So `ck close` (and the end of `ck run`) closes without saving: it answers *No* to a
  save prompt and terminates the CK if anything else is in the way (terminating never writes).
- `ck close` only closes a CK that ack launched (recorded in `work_dir/ck_session.json`); one a person opened may
  hold their unsaved work. `--force` overrides.
- `xedit run --save` refuses to start while a CK is open that could save over its plugin: one ack did not start,
  or one with that plugin as its active file.
- `ck save` and `ck compact` check the written plugin (`ack.plugin.check`) against its masters from just before and
  exit with code 1 on a problem: a master the save added, a navmesh missing from the navmesh index, an ESL record
  outside the light range. `--masters` also checks the exact list.

Menus, lists and buttons are driven with window messages. The render window and the Reference dialog only
respond to a person, so those commands use real mouse and keyboard input: they bring the Creation Kit to the front
and move the cursor. **Only run them when nobody is using the PC.** Every edit is checked before it is applied:
`ref` opens the object's Reference dialog by clicking it in the render window and refuses to type anything unless
the dialog shows the requested editor ID.

Things the Creation Kit does that the tools work around (details in `ack/ck/session.py`):
- It is not DPI-aware: coordinates posted to it are scaled by the screen's DPI factor.
- Its render window only draws while visible, so screenshots copy the screen.
- **Set as Active File** toggles, and File > Data opens hidden and remembers the last session's ticks.
- New forms get IDs from its own counter, which can run past an ESL's 0xFFF; `compact` renumbers them.
  **Compact Active File Form IDs writes the plugin to disk itself**, without a Save, and can leave the header's next
  object ID past the light range (0x1732 on an empty ESL). Renumbering also breaks other plugins that point at the
  old IDs: xEdit's `build` script fixes out-of-range IDs and repoints references instead.
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

## Other games

Everything game-specific is a `Game` profile in `ack/games.py`: official masters, the xEdit exe and its game switch,
the CK exe and main window class, the My Games folder and custom ini, light-plugin ID ranges. Choose one with
`"game"` in `config.local.json` (default `fo4`).

- **Fallout 4**: verified (xEdit, CK, plugin, Papyrus compile and log, BA2).
- **Skyrim Special Edition** (`sse`): profile from xEdit's rules, not yet tried. `ack.xedit`, `ack.plugin` and the
  checks should work as they are (same record format); `ack.ck` refuses to run until the CK's window class is set in
  the profile, because each command needs checking against that CK.
- Adding a game: add a profile, run the round-trip test on its masters (`ACK_GAME_DATA`), and mark what was checked
  in `verified`. Oblivion's older record format (20-byte headers) would need `ack.plugin` changes.

## Roadmap

- Record editing helpers on top of `ack.plugin` (copy/create records, FormID allocation, master handling),
  so common edits no longer need xEdit at all; xEdit stays as the independent validator.
- An MCP server exposing these tools to any agent.
- Mod Organizer 2: verify saving xEdit runs and the Creation Kit through MO2.
- `ack.ck`: gizmo moves in the render window.
- Verify `ack.ck`'s save-prompt answer on close with unsaved changes (closing has so far always found nothing to
  save; terminating covers it either way).

## License

MIT - see [LICENSE](LICENSE). Copyright (c) 2026 IronAdamant.
