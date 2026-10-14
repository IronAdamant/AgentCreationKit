"""Machine-specific paths, read from config.local.json at the repo root (git-ignored).

Example config.local.json:
{
  "game": "fo4",
  "game_dir": "D:/Steam/steamapps/common/Fallout 4",
  "xedit_exe": "D:/Tools/FO4Edit/FO4Edit.exe",
  "work_dir": "D:/Coding Projects/AgentCreationKit/private/runs",
  "ck_region": [0, 0, 1920, 1080]
}
"game" picks the profile in ack/games.py (default "fo4"). "ck_region" (optional): the screen rectangle
[x, y, width, height] the Creation Kit is laid out in, e.g. a 1920x1080 part of an ultrawide screen for recording;
without it the CK is maximised.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import games

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / 'config.local.json'


@dataclass
class Config:
    game_dir: Path
    xedit_exe: Path
    work_dir: Path
    game: games.Game = games.GAMES['fo4']
    ck_region: tuple[int, int, int, int] | None = None

    @property
    def data_dir(self) -> Path:
        return self.game_dir / 'Data'

    @property
    def xedit_scripts_dir(self) -> Path:
        return self.xedit_exe.parent / 'Edit Scripts'

    @property
    def my_games_dir(self) -> Path:
        return Path.home() / 'Documents' / 'My Games' / self.game.my_games


def load(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        raise SystemExit(f'Missing {path.name}: copy config.example.json to {path.name} and set your paths.')
    raw = json.loads(path.read_text(encoding='utf8'))
    region = tuple(raw['ck_region']) if raw.get('ck_region') else None
    return Config(Path(raw['game_dir']), Path(raw['xedit_exe']), Path(raw['work_dir']), games.get(raw.get('game', 'fo4')),
                  region)
