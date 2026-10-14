# Instructions for AI agents

You are helping a modder build or fix a Bethesda game mod. AgentCreationKit (ack) is how you work the game's
tools: xEdit runs, the Creation Kit, plugin files, Papyrus scripts and BA2 archives. Run everything from this
repo's root as `python -m ack ...`. `python -m ack <area> -h` shows the options of any command; README.md explains
how each part works.

The person you work for owns their PC, their game install and their mod. ack is built so that nothing it does
can lose their work. Keep it that way: the rules below are what makes that true.

## First run on a new PC

1. `python -m ack doctor`. It checks Python, the config, the game, xEdit, the Creation Kit, the Papyrus compiler,
   Archive2, the display and Mod Organizer 2, and prints the fix for each problem.
2. No `config.local.json` yet: write it from `config.example.json`, using the paths doctor found (it lists Steam
   game folders and MO2 instances). **Ask the user** for what it cannot find: where their xEdit (FO4Edit.exe) is,
   whether they use Mod Organizer 2 or Vortex, and which MO2 profile. Never guess a path.
3. Run doctor again until it prints `ready`. Tell the user what any WARN line limits.
4. `python -m unittest discover -s tests -t .` (tests that need game files skip without them).

## Rules

1. **Ask before driving the Creation Kit.** `ack ck` brings the CK to the front and uses the real mouse and
   keyboard for the render window and the Reference dialog. Confirm that nobody is using the PC first.
2. **The CK never saves except through `ck save` or `ck compact`**, which check the written plugin. Prefer
   `python -m ack ck run steps.txt`: one session that always ends with the CK closed without saving. After single
   commands, end with `python -m ack ck close`. Never `ck close --force` without the user's OK: it throws away
   the unsaved work of a CK they opened.
3. **xEdit runs are read-only unless you pass `--save`**, and `--save` is only for the user's own mod. Never save
   an official master (Fallout4.esm, the DLC), another author's mod, or anything in the game's archives.
   Before an editing run, make sure the plugin is committed to the mod's git repo or backed up.
4. **A refusal (exit code 2) is a safety stop, not an obstacle.** ack refuses, for example, an xEdit save while a
   Creation Kit that could save over the plugin is open. Report it to the user. Do not work around it (do not
   kill a CK you did not start).
5. **Read every check result.** `ck save`, `ck compact` and `plugin check` exit 1 on a problem: a master the save
   added, a navmesh missing from the navmesh index (NAVI), an ESL form ID out of range. Fix it before going on.
   Exit codes: 0 OK, 1 problem (the output says what), 2 refused.
6. **Unknown dialogs are never clicked.** If an xEdit run stops on one, open the captured screenshot
   (`unknown_*.bmp` in the run folder) and show the user. Add a rule to `ack/xedit/rules.json` only when the
   dialog and the effect of the button are understood, and never one that agrees to save in a read-only run.
7. **Leave the game install alone** apart from the mod being worked on: not the vanilla script sources
   (Data/Scripts/Source/Base), not the vanilla archives, not other mods' files.
8. **Uploading and publishing are the user's.** Prepare the files; they upload them (Nexus, Bethesda.net).

## Which command for what

| Task | Command |
|---|---|
| Check the setup | `python -m ack doctor` |
| Where a file really is (MO2: which mod) | `python -m ack where "MyMod.esp" Scripts/MyMod/X.pex` |
| A plugin's records and masters | `python -m ack plugin info MyMod.esp` |
| Check a plugin after any CK save | `python -m ack plugin check MyMod.esp --masters Fallout4.esm` |
| Learn a record's xEdit field paths before editing | `python -m ack xedit run dump_records MyMod.esp --param RECORDS=EDID1,EDID2` |
| Edit records (properties, text, effects, fields, positions) | `apply_edits` with an EDITS file, `--save` |
| Build a plugin from a spec (records, placed objects, terminals, scripts) | `build` with a SPEC file, `--save` |
| Errors xEdit can find | `python -m ack xedit run check_errors MyMod.esp` |
| Remove unused masters | `python -m ack xedit run clean_masters MyMod.esp --save` |
| Move or place references | the `build` spec (`ref`) or `apply_edits` (`ref.move`), not the CK |
| Navmesh | the CK: a `ck run` steps file with `cell`, `navmesh`, `save`; then `ack navmesh` and `plugin check` |
| See what something looks like | `python -m ack ck shot out.png` (then read the image) |
| Compile scripts | `python -m ack papyrus compile source/User --out data/Scripts` |
| Debug scripts in game | `python -m ack papyrus-log on`, the user plays, read the log, then `papyrus-log off` |
| Pack the release archives | `python -m ack ba2 pack stage "dist/MyMod - Main.ba2"` and `... --textures` |
| Look inside an archive | `python -m ack ba2 info X.ba2 --files`; `ba2 extract` for vanilla assets |

`python -m ack xedit scripts` lists the bundled xEdit scripts; each one's header in `ack/xedit/scripts/` explains
its file format (`apply_edits.pas`, `build.pas`). A mod can keep its own `.pas` templates and run them by path.

## How a mod is usually laid out and built

Keep the mod in a git repo, separate from the game: `source/User/<Mod>/*.psc` (scripts), `data/` (the plugin and
loose assets as they go in Data), the spec or edits files that build the plugin, and the mod's own tools. Then:

1. Build or edit the plugin with xEdit (`build` or `apply_edits`, `--save`) into the game's Data folder (or the
   mod's MO2 folder), and copy it back into the repo.
2. Compile the scripts (`papyrus compile`) and install them with the assets.
3. Use the Creation Kit only for what needs it (navmesh, looking at a layout), and check every save.
4. The user tests in game. Write the test steps as a checklist; turn on the Papyrus log when a script misbehaves.
5. Pack the archives (`ba2 pack`) and package the release (the mod's own script: FOMOD, readme).

## Things that will catch you out

- **xEdit** takes about a minute to load the game's masters. In script mode it saves changed plugins whenever it
  closes normally, without asking; that is why ack kills read-only runs instead of closing them.
- **Creation Kit** (details in README): it is not DPI-aware; Set as Active File is a toggle; a save finishes a few
  seconds after the CK looks idle; Compact Active File Form IDs writes the plugin itself; saving with extra plugins
  loaded can add their masters through the navmesh index; new forms can get IDs outside an ESL's range.
- **Mod Organizer 2**: xEdit and the CK only see mods installed through MO2 when ack starts them through MO2
  (`"mo2"` in the config). Files they create there go to MO2's overwrite folder (xEdit's cache does too).
  `where` shows where a file landed. A plugin saved into overwrite belongs in its mod's folder: tell the user, and
  move it only with their OK. Read-only xEdit runs through MO2 are verified; saving runs and the Creation Kit
  through MO2 are newer, so check where the file landed the first time.
- **Vortex** deploys mods into the real Data folder, so ack works with it as it is (no `"mo2"`).
- **Game versions**: the old-gen game (1.10.163) cannot read BA2 version 8, which the next-gen Archive2 writes;
  `ba2 pack` stamps version 1, which every PC version reads.
- **Consoles**: Xbox archives must come from the Creation Kit's Generate when uploading to Bethesda.net (Archive2's
  Xbox format shows pink textures). PlayStation allows no custom scripts or assets.
- **Papyrus**: scripts are compiled against the vanilla sources only, so the mod never needs F4SE by accident;
  `--f4se` is for mods meant to need it. Release builds strip `Debug.Trace`; use `--debug` while testing.
- **Other games**: `ack/games.py` lists what each profile has been verified for (`verified`). Anything else is
  untried: go slowly, read every output, and tell the user it is a first run.

## When something fails

- An xEdit run: its folder (in `work_dir`, named after the time and script) holds `report.json`, `xedit_log.txt`
  (script errors), `unknown_*.bmp` (dialogs it would not click) and `timeout_main_window.bmp`.
- The Creation Kit: `python -m ack ck shot --main x.png` shows the whole window; `ck status` the active file,
  selection and camera.
- Do not retry the same failing command in a loop. Read the output, say what you found, and ask if it is unclear.
