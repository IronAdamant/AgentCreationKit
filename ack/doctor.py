"""Check that this PC is set up for ack, and say how to fix what is not.

    python -m ack doctor

Each line is OK, WARN (works, with a limit to know about) or FAIL (something ack needs), with the fix after "->".
Exit code 1 when anything FAILs. Without config.local.json it lists what it can find (Steam game folders, Mod
Organizer 2 instances) to fill one in. Reads only; the one write is a test file in xEdit's Edit Scripts folder and
the work folder, deleted at once.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import config, games, mo2, win32


class Report:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def add(self, level: str, text: str, fix: str = ''):
        self.lines.append((level, text + (f'\n        -> {fix}' if fix else '')))

    def ok(self, text):
        self.add('OK', text)

    def warn(self, text, fix=''):
        self.add('WARN', text, fix)

    def fail(self, text, fix=''):
        self.add('FAIL', text, fix)

    @property
    def failed(self) -> bool:
        return any(level == 'FAIL' for level, _ in self.lines)

    def text(self) -> str:
        return '\n'.join(f'{level:5} {text}' for level, text in self.lines)


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / '.ack_doctor_probe'
        probe.write_text('ack', encoding='utf8')
        probe.unlink()
        return True
    except OSError:
        return False


def steam_game_dirs(folder_name: str) -> list[Path]:
    """The game's folder in every Steam library (Steam's registry key and libraryfolders.vdf)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
            steam = Path(winreg.QueryValueEx(k, 'SteamPath')[0])
    except OSError:
        return []
    libraries = [steam]
    vdf = steam / 'steamapps' / 'libraryfolders.vdf'
    if vdf.exists():
        libraries += [Path(p.replace('\\\\', '\\')) for p in
                      re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding='utf8', errors='replace'))]
    found = []
    for lib in libraries:
        d = lib / 'steamapps' / 'common' / folder_name
        if d.is_dir() and d.resolve() not in [f.resolve() for f in found]:
            found.append(d)
    return found


def _no_config(r: Report, path: Path) -> None:
    r.fail(f'no {path.name}', f'copy config.example.json to {path.name} and fill it in '
           f'(the paths below help); ask the user where their xEdit (FO4Edit.exe) is')
    for g in games.GAMES.values():
        for d in steam_game_dirs(g.name):
            r.add('INFO', f'{g.name} ("game": "{g.key}"): "game_dir": "{d.as_posix()}"')
            for inst in mo2.find_instances(d):
                r.add('INFO', f'  managed by the Mod Organizer 2 instance "{inst.name}" ({inst}): add '
                              f'"mo2": {{"exe": "<path to ModOrganizer.exe>", "instance": "{inst.name}"}}')


def check(path: Path = config.CONFIG_FILE) -> Report:
    r = Report()
    v = sys.version_info
    (r.ok if v >= (3, 10) else r.fail)(f'Python {v.major}.{v.minor}' + ('' if v >= (3, 10) else ': ack needs 3.10+'))
    if sys.platform != 'win32':
        r.fail('not Windows: the game tools (xEdit, the Creation Kit) and ack run on Windows only')
        return r
    if not path.exists():
        _no_config(r, path)
        return r
    try:
        cfg = config.load(path)
    except (SystemExit, ValueError, KeyError, OSError) as e:
        r.fail(f'{path.name} does not load: {e}', 'fix it against config.example.json (game_dir, xedit_exe, '
                                                   'work_dir are required)')
        return r
    g = cfg.game
    r.ok(f'game profile "{g.key}" ({g.name}); verified with ack: {", ".join(g.verified) or "nothing yet"}')
    if g.key != 'fo4':
        r.warn(f'{g.name} is not verified like Fallout 4', 'treat first runs with care; see "Other games" in README')
    _game(r, cfg)
    _xedit(r, cfg)
    (r.ok if _writable(cfg.work_dir) else r.fail)(f'work_dir {cfg.work_dir}' +
                                                   ('' if _writable(cfg.work_dir) else ' is not writable'))
    _creation_kit(r, cfg)
    _mo2(r, cfg)
    _running(r, cfg)
    return r


def _game(r: Report, cfg: config.Config) -> None:
    g = cfg.game
    exe = cfg.game_dir / g.exe
    if not exe.exists():
        r.fail(f'game_dir {cfg.game_dir}: no {g.exe}', 'set "game_dir" to the folder holding ' + g.exe)
        return
    r.ok(f'{g.name} {win32.file_version(exe) or "(version unknown)"} in {cfg.game_dir}')
    missing = [m for m in g.masters if not cfg.data_path(m).exists()]
    if g.masters[0] in missing:
        r.fail(f'{g.masters[0]} is not in Data', 'is game_dir the game folder (the one holding Data)?')
    elif missing:
        r.warn(f'official masters missing: {", ".join(missing)}',
               'plugins that need them will not load; xEdit runs load only what is there')
    else:
        r.ok(f'official masters: all {len(g.masters)}')
    ini = cfg.custom_ini
    r.ok(f'custom ini {ini}' + ('' if ini.exists() else ' (not there yet: `ack papyrus-log on` creates it)'))


def _xedit(r: Report, cfg: config.Config) -> None:
    exe = cfg.xedit_exe
    if not exe.exists():
        r.fail(f'xedit_exe {exe} does not exist', f'install xEdit ({cfg.game.xedit_exe}, from Nexus or GitHub '
                                                   f'TES5Edit/TES5Edit) and set "xedit_exe"')
        return
    r.ok(f'xEdit {win32.file_version(exe) or ""} at {exe}')
    if exe.name.lower() != cfg.game.xedit_exe.lower():
        r.ok(f'{exe.name} is started with {cfg.game.xedit_mode} (not the game\'s own {cfg.game.xedit_exe})')
    scripts = cfg.xedit_scripts_dir
    if not scripts.is_dir():
        r.fail(f'no "Edit Scripts" folder beside xEdit ({scripts})', 'use a full xEdit download: ack puts its '
                                                                    'scripts there')
    elif not _writable(scripts):
        r.fail(f'cannot write to {scripts}', 'move xEdit out of Program Files, or give the folder write access')
    else:
        r.ok('xEdit Edit Scripts folder is writable')


def _creation_kit(r: Report, cfg: config.Config) -> None:
    g = cfg.game
    ck = cfg.game_dir / g.ck_exe
    if not ck.exists():
        r.warn(f'no Creation Kit ({ck})', 'ack ck, papyrus and ba2 pack need it: install it from Steam')
        return
    game_v, ck_v = win32.file_version(cfg.game_dir / g.exe), win32.file_version(ck)
    r.ok(f'Creation Kit {ck_v or ""}')
    if game_v and ck_v and game_v.split('.')[:2] != ck_v.split('.')[:2]:
        r.warn(f'the Creation Kit ({ck_v}) and the game ({game_v}) are from different updates',
               'plugins it saves may not suit this game version; update both through Steam')
    if not g.ck_window_class:
        r.warn(f'ack ck is not checked for the {g.name} Creation Kit (no ck_window_class in ack/games.py)')
    compiler = cfg.game_dir / 'Papyrus Compiler' / 'PapyrusCompiler.exe'
    if g.papyrus_sources:
        flags = cfg.data_path(f'{g.papyrus_sources}/{g.papyrus_flags}')
        if not compiler.exists():
            r.warn('no Papyrus compiler', 'it comes with the Creation Kit')
        elif not flags.exists():
            r.warn(f'vanilla script sources not unpacked ({flags.parent})',
                   'start the Creation Kit once: it unpacks them (Base.zip); ack papyrus compile needs them')
        else:
            r.ok(f'Papyrus compiler and vanilla sources ({flags.parent})')
        f4se = cfg.data_path('Scripts/Source/F4SE.psc')
        if g.key == 'fo4' and f4se.exists():
            r.ok('F4SE script sources found (used only with ack papyrus compile --f4se)')
    if g.ba2_version is not None:
        a2 = cfg.game_dir / 'Tools' / 'Archive2' / 'Archive2.exe'
        (r.ok if a2.exists() else r.warn)('Archive2' + ('' if a2.exists() else ' missing: ack ba2 pack needs it '
                                                                               '(it comes with the Creation Kit)'))
    from .ck import session  # noqa: F401  (makes this process DPI-aware, as ack ck is: real pixels)
    dpi = win32.ctypes.windll.user32.GetDpiForSystem() if hasattr(win32.ctypes.windll.user32, 'GetDpiForSystem') else 96
    sm = win32.ctypes.windll.user32.GetSystemMetrics
    screen = (sm(76), sm(77), sm(78), sm(79))     # the virtual screen: x, y, width, height
    r.ok(f'display scaling {dpi * 100 // 96}% (ack ck allows for it), screen {screen[2]}x{screen[3]}')
    if cfg.ck_region:
        x, y, w, h = cfg.ck_region
        inside = x >= screen[0] and y >= screen[1] and x + w <= screen[0] + screen[2] and y + h <= screen[1] + screen[3]
        (r.ok if inside else r.fail)(f'ck_region {list(cfg.ck_region)}' +
                                     ('' if inside else ' is outside the screen'))


def _mo2(r: Report, cfg: config.Config) -> None:
    if not cfg.mo2:
        found = mo2.find_instances(cfg.game_dir)
        if found:
            r.warn(f'Mod Organizer 2 manages this game ({", ".join(f.name for f in found)}), but "mo2" is not set: '
                   f'ack sees only the real Data folder, not mods installed through MO2',
                   'fine if your mod is in Data; otherwise add "mo2" to the config (README, Mod Organizer 2)')
        return
    m = cfg.mo2
    if not m.exe.exists():
        r.fail(f'mo2 exe {m.exe} does not exist', 'set "mo2" "exe" to ModOrganizer.exe')
    else:
        r.ok(f'Mod Organizer 2 {win32.file_version(m.exe) or ""}: instance {m.name or m.dir}, profile {m.profile}')
    if m.game_dir.resolve() != cfg.game_dir.resolve():
        r.fail(f'the MO2 instance manages {m.game_dir}, not game_dir {cfg.game_dir}', 'pick the right instance')
    if not m.profile_dir.is_dir():
        r.fail(f'no MO2 profile "{m.profile}" ({m.profile_dir})', 'set "mo2" "profile" to one of: ' +
               ', '.join(p.name for p in m.profiles_dir.glob('*') if p.is_dir()))
        return
    r.ok(f'MO2 profile: {len(m.enabled_mods())} enabled mods, {len(m.plugins())} active plugins; '
         f'files the tools create land in {m.overwrite_dir}')
    if m.portable or not m.name:
        r.warn('portable MO2 instance (or one given as a path): MO2 is started without -i, so it opens the '
               'instance it used last', 'open this instance in MO2 once before running ack')
    if m.local_inis:
        r.ok(f'the profile has its own inis: ack uses {cfg.custom_ini}')


def _running(r: Report, cfg: config.Config) -> None:
    from .ck import lifecycle
    pids = lifecycle.running(cfg)
    if pids and not lifecycle.read_state(cfg):
        r.warn('a Creation Kit is open that ack did not start', 'ack will not save over plugins or close it; '
                                                               'close it yourself when done (without saving)')
    elif pids:
        r.ok('a Creation Kit ack started is open (python -m ack ck close ends it without saving)')
    if win32.pids_of(cfg.xedit_exe.name):
        r.warn(f'{cfg.xedit_exe.name} is running', 'a run started now opens a second xEdit; close the other '
                                                   'first if it has the same plugins loaded')


def main() -> int:
    r = check()
    print(r.text())
    print('\nFAILED: fix the FAIL lines above' if r.failed else '\nready')
    return 1 if r.failed else 0
