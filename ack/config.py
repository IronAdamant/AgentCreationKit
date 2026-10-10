"""Machine-specific paths, read from config.local.json at the repo root (git-ignored).

Example config.local.json:
{
  "game_dir": "D:/Steam/steamapps/common/Fallout 4",
  "xedit_exe": "D:/Tools/FO4Edit/FO4Edit.exe",
  "work_dir": "D:/Coding Projects/AgentCreationKit/private/runs"
}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / 'config.local.json'


@dataclass
class Config:
    game_dir: Path
    xedit_exe: Path
    work_dir: Path

    @property
    def data_dir(self) -> Path:
        return self.game_dir / 'Data'

    @property
    def xedit_scripts_dir(self) -> Path:
        return self.xedit_exe.parent / 'Edit Scripts'


def load(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        raise SystemExit(f'Missing {path.name}: copy config.example.json to {path.name} and set your paths.')
    raw = json.loads(path.read_text(encoding='utf8'))
    return Config(Path(raw['game_dir']), Path(raw['xedit_exe']), Path(raw['work_dir']))
