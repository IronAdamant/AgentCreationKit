"""Mod Organizer 2: where a mod's files really are, and running tools inside MO2's virtual Data folder.

MO2 keeps each mod in its own folder (<base>/mods/<mod>) and only merges them into the game's Data folder for the
programs it launches (a virtual file system, usvfs). Started on their own, xEdit and the Creation Kit see the real
Data folder only, so a plugin installed through MO2 does not exist for them. With "mo2" in config.local.json:
- file lookups (plugin check, the CK save check) resolve a Data path the way MO2 does: the overwrite folder first,
  then the enabled mods from the highest priority down, then the real Data folder;
- xEdit and the Creation Kit are started through ModOrganizer.exe (its "run" command), so they see the profile's
  mods. A file a tool writes there goes back to the mod it came from; a new file goes to the overwrite folder.

    "mo2": {"exe": "D:/MO2/ModOrganizer.exe", "instance": "Fallout 4", "profile": "Default"}

instance: a global instance's name (its folder is %LOCALAPPDATA%/ModOrganizer/<name>), or the path of an instance
folder (the folder holding ModOrganizer.ini; a portable instance is the folder of ModOrganizer.exe). profile:
optional, default the instance's selected profile.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


def read_ini(path: Path) -> dict[str, dict[str, str]]:
    """A Qt settings file (ModOrganizer.ini): sections -> keys -> values, with Qt's quoting undone:
    @ByteArray(...) unwrapped, surrounding quotes dropped, doubled backslashes made single."""
    out: dict[str, dict[str, str]] = {}
    section = out.setdefault('', {})
    for line in path.read_text(encoding='utf8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = out.setdefault(line[1:-1], {})
            continue
        key, sep, value = line.partition('=')
        if not sep:
            continue
        m = re.fullmatch(r'@ByteArray\((.*)\)', value)
        value = m.group(1) if m else value
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        section[key.strip()] = value.replace('\\\\', '\\').replace('\\"', '"')
    return out


@dataclass
class Instance:
    exe: Path                   # ModOrganizer.exe
    dir: Path                   # the folder holding ModOrganizer.ini
    name: str | None            # a global instance's name; None for a portable instance (or one given as a path)
    profile: str
    game_dir: Path
    base_dir: Path
    mods_dir: Path
    overwrite_dir: Path
    profiles_dir: Path
    local_inis: bool            # the profile has its own game inis (Fallout4Custom.ini etc.)

    @property
    def profile_dir(self) -> Path:
        return self.profiles_dir / self.profile

    @property
    def portable(self) -> bool:
        return self.dir.resolve() == self.exe.parent.resolve()

    # ------------------------------------------------------------------ the profile
    def modlist(self) -> list[tuple[str, bool]]:
        """(mod, enabled) from the highest priority down: modlist.txt lists the winning mod first. Separators and
        unmanaged entries (DLC, files in the real Data folder: '*') are left out."""
        path = self.profile_dir / 'modlist.txt'
        out = []
        for line in path.read_text(encoding='utf8', errors='replace').splitlines() if path.exists() else []:
            if not line or line[0] not in '+-' or line.endswith('_separator'):
                continue
            out.append((line[1:], line[0] == '+'))
        return out

    def enabled_mods(self) -> list[str]:
        return [m for m, on in self.modlist() if on]

    def plugins(self) -> list[str]:
        """The profile's active plugins in load order (plugins.txt, '*' = active; the official masters are not
        listed)."""
        path = self.profile_dir / 'plugins.txt'
        lines = path.read_text(encoding='utf8', errors='replace').splitlines() if path.exists() else []
        return [l[1:] for l in lines if l.startswith('*')]

    # ------------------------------------------------------------------ files
    def origin(self, rel: str | Path) -> tuple[str, Path] | None:
        """Where a Data-relative file comes from, as MO2 sees it: ('overwrite' | mod name | 'Data', its real path),
        or None if it is nowhere."""
        rel = Path(rel)
        if (self.overwrite_dir / rel).exists():
            return 'overwrite', self.overwrite_dir / rel
        for mod in self.enabled_mods():
            p = self.mods_dir / mod / rel
            if p.exists():
                return mod, p
        p = self.game_dir / 'Data' / rel
        return ('Data', p) if p.exists() else None

    def resolve(self, rel: str | Path) -> Path:
        """The real path of a Data-relative file as MO2 shows it (the overwrite folder when it is nowhere yet,
        which is where a new file written through MO2 lands)."""
        found = self.origin(rel)
        return found[1] if found else self.overwrite_dir / rel

    # ------------------------------------------------------------------ running tools
    def run_command(self, program: Path, args: list[str], cwd: Path | None = None) -> list[str]:
        """The command line that starts a program inside this instance's virtual file system. MO2 starts itself if
        needed (or hands the command to the MO2 already running) and stays locked until the program exits."""
        cmd = [str(self.exe)]
        if self.name and not self.portable:
            cmd += ['-i', self.name]
        cmd += ['-p', self.profile, 'run']
        if args:
            cmd += ['-a', subprocess.list2cmdline(args)]
        if cwd:
            cmd += ['-c', str(cwd)]
        return cmd + [str(program)]


def global_instances_dir() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'ModOrganizer'


def load(raw: dict) -> Instance:
    """The instance described by config.local.json's "mo2" entry."""
    exe = Path(raw['exe'])
    inst = str(raw.get('instance') or '')
    if inst and (Path(inst).is_absolute() or os.sep in inst or '/' in inst):
        folder, name = Path(inst), None
    elif inst:
        folder, name = global_instances_dir() / inst, inst
    else:
        folder, name = exe.parent, None           # the portable instance beside ModOrganizer.exe
    ini_path = folder / 'ModOrganizer.ini'
    if not ini_path.exists():
        raise SystemExit(f'MO2: no ModOrganizer.ini in {folder} (config.local.json "mo2" "instance")')
    ini = read_ini(ini_path)
    general, settings = ini.get('General', {}), ini.get('Settings', {})
    base = Path(settings.get('base_directory') or folder)

    def sub(key: str, default: str) -> Path:
        return Path(settings.get(key, f'%BASE_DIR%/{default}').replace('%BASE_DIR%', str(base)))

    return Instance(exe, folder, name, raw.get('profile') or general.get('selected_profile') or 'Default',
                    Path(general.get('gamePath', '')), base, sub('mod_directory', 'mods'),
                    sub('overwrite_directory', 'overwrite'), sub('profiles_directory', 'profiles'),
                    settings.get('profile_local_inis', 'false').lower() == 'true')


def find_instances(game_dir: Path) -> list[Path]:
    """Global MO2 instances that manage this game folder (for `ack doctor`: mods ack cannot see without "mo2")."""
    out = []
    root = global_instances_dir()
    for ini in sorted(root.glob('*/ModOrganizer.ini')) if root.exists() else []:
        game = read_ini(ini).get('General', {}).get('gamePath', '')
        if game and Path(game).resolve() == game_dir.resolve():
            out.append(ini.parent)
    return out
