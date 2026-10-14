"""Which Creation Kit is ours, and keeping the plugins safe from it.

A Creation Kit left open keeps its own copy of the loaded plugins: one save from it (a stray Ctrl+S) writes that
stale copy over anything built since, which happened once with an xEdit build. So:
- ack records the CK it launched and what it loaded in a session file (work_dir/ck_session.json).
- `ck close` ends that session without saving; it refuses to close a CK that ack did not start, because closing
  without saving would throw away a person's unsaved work.
- xEdit runs that save refuse to start while a CK that could save over their plugin is open.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import config, win32


@dataclass
class SessionState:
    pid: int
    started: float = field(default_factory=time.time)
    plugins: list[str] = field(default_factory=list)   # ticked in File > Data ([] = not loaded yet)
    active: str | None = None                          # the file the CK saves into, or None (look only)


def _path(cfg: config.Config | None = None) -> Path:
    return (cfg or config.load()).work_dir / 'ck_session.json'


def running(cfg: config.Config | None = None) -> list[int]:
    cfg = cfg or config.load()
    return win32.pids_of(cfg.game.ck_exe)


def read_state(cfg: config.Config | None = None) -> SessionState | None:
    """The session ack recorded, if that CK is still the one running."""
    path = _path(cfg)
    try:
        state = SessionState(**json.loads(path.read_text(encoding='utf8')))
    except (OSError, ValueError, TypeError):
        return None
    return state if win32.process_alive(state.pid) else None


def write_state(state: SessionState, cfg: config.Config | None = None) -> None:
    path = _path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=1), encoding='utf8')


def clear_state(cfg: config.Config | None = None) -> None:
    _path(cfg).unlink(missing_ok=True)


def save_blocker(plugins: list[str], cfg: config.Config | None = None) -> str | None:
    """Why an edit that writes these plugins must not run now, or None. A running CK blocks it unless ack knows
    the CK has none of them as its active file (the only file a CK save writes)."""
    cfg = cfg or config.load()
    pids = running(cfg)
    if not pids:
        return None
    state = read_state(cfg)
    if state and pids == [state.pid] and state.active not in plugins:
        return None
    what = (f'with {state.active} as its active file' if state and pids == [state.pid]
            else 'and ack did not start it, so it may have any plugin active')
    return (f'the Creation Kit is running {what}: a save from it would overwrite this edit. '
            f'Close it first (python -m ack ck close, or close it yourself without saving).')
