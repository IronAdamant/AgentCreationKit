"""Switch the game's Papyrus script log on or off (Fallout4Custom.ini), for debugging scripts in-game.

"on" writes a [Papyrus] section with logging, tracing and debug info enabled; "off" removes exactly that section,
leaving the rest of the file alone. Logs: Documents/My Games/Fallout4/Logs/Script/Papyrus.0.log (newest session),
and user logs (Debug.OpenUserLog) in Logs/Script/User/<name>.0.log. Debug.Trace/TraceUser lines only appear from
scripts compiled without -release/-final.
"""
from __future__ import annotations

from pathlib import Path

INI = Path.home() / 'Documents' / 'My Games' / 'Fallout4' / 'Fallout4Custom.ini'
LOGS = Path.home() / 'Documents' / 'My Games' / 'Fallout4' / 'Logs' / 'Script'
SECTION = ['[Papyrus]', 'bEnableLogging=1', 'bEnableTrace=1', 'bLoadDebugInformation=1']


def _strip(lines: list[str]) -> list[str]:
    """The ini without its [Papyrus] section (header and keys up to the next section)."""
    out, skipping = [], False
    for line in lines:
        if line.strip().startswith('['):
            skipping = line.strip().lower() == '[papyrus]'
        if not skipping:
            out.append(line)
    return out


def _lines(ini: Path) -> list[str]:
    return ini.read_text(encoding='utf8').splitlines() if ini.exists() else []


def is_on(ini: Path = INI) -> bool:
    return any(l.strip().lower() == '[papyrus]' for l in _lines(ini))


def set_logging(on: bool, ini: Path = INI) -> None:
    lines = _strip(_lines(ini)) + (SECTION if on else [])
    ini.write_text('\n'.join(lines) + '\n', encoding='utf8')
