"""Machine-specific paths, read from config.local.json at the repo root (git-ignored).

Example config.local.json:
{
  "game": "fo4",
  "game_dir": "D:/Steam/steamapps/common/Fallout 4",
  "xedit_exe": "D:/Tools/FO4Edit/FO4Edit.exe",
  "work_dir": "D:/Tools/AgentCreationKit/runs",
  "ck_region": [0, 0, 1920, 1080],
  "mo2": {"exe": "D:/MO2/ModOrganizer.exe", "instance": "Fallout 4", "profile": "Default"}
}
"game" picks the profile in ack/games.py (default "fo4"). "ck_region" (optional): the screen rectangle
[x, y, width, height] the Creation Kit is laid out in, e.g. a 1920x1080 part of an ultrawide screen for recording;
without it the CK is maximised. "mo2" (optional): run xEdit and the Creation Kit through Mod Organizer 2 and find
files where MO2 puts them (ack/mo2.py).

`python -m ack doctor` checks all of it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import games
from . import mo2 as mo2_mod

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / 'config.local.json'


@dataclass
class Config:
    game_dir: Path
    xedit_exe: Path
    work_dir: Path
    game: games.Game = games.GAMES['fo4']
    ck_region: tuple[int, int, int, int] | None = None
    mo2: mo2_mod.Instance | None = None

    @property
    def data_dir(self) -> Path:
        return self.game_dir / 'Data'

    @property
    def xedit_scripts_dir(self) -> Path:
        return self.xedit_exe.parent / 'Edit Scripts'

    @property
    def my_games_dir(self) -> Path:
        return Path.home() / 'Documents' / 'My Games' / self.game.my_games

    @property
    def custom_ini(self) -> Path:
        """The game's custom ini as the game will read it (an MO2 profile with its own inis keeps it there)."""
        if self.mo2 and self.mo2.local_inis:
            return self.mo2.profile_dir / self.game.custom_ini
        return self.my_games_dir / self.game.custom_ini

    def data_path(self, rel: str | Path) -> Path:
        """The real path of a file in Data (a plugin name, 'Scripts/X.pex', ...): through MO2's mods when "mo2" is
        set, else the game's Data folder."""
        return self.mo2.resolve(rel) if self.mo2 else self.data_dir / rel

    def write_targets(self, rel: str | Path) -> list[Path]:
        """Where a tool saving this Data file can put it: the file itself, and under MO2 also the overwrite folder
        (where MO2 sends a file a program creates or replaces)."""
        paths = [self.data_path(rel)]
        if self.mo2 and self.mo2.overwrite_dir / rel not in paths:
            paths.append(self.mo2.overwrite_dir / rel)
        return paths

    def command(self, program: Path, args: list[str], cwd: Path | None = None) -> list[str]:
        """The command line to start a game tool: through MO2 when "mo2" is set, so it sees the mods."""
        if self.mo2:
            return self.mo2.run_command(program, args, cwd)
        return [str(program)] + list(args)



def load(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        raise SystemExit(f'Missing {path.name}: copy config.example.json to {path.name} and set your paths '
                         f'(then run python -m ack doctor).')
    raw = json.loads(path.read_text(encoding='utf8'))
    region = tuple(raw['ck_region']) if raw.get('ck_region') else None
    return Config(Path(raw['game_dir']), Path(raw['xedit_exe']), Path(raw['work_dir']), games.get(raw.get('game', 'fo4')),
                  region, mo2_mod.load(raw['mo2']) if raw.get('mo2') else None)
