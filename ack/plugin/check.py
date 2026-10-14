"""Checks a plugin can fail after a Creation Kit (or any) save, each one from a problem met on real work.

- Masters: the CK adds every plugin it had loaded whose navmesh it touched as a master, through the navmesh
  index (NAVI). Compare against the expected list, or against the masters before the save.
- Navmesh index: every navmesh the plugin adds needs an entry (NVMI) with its FormID in the plugin's NAVI. A
  master list change once left the entries pointing at the wrong file, and the game crashed on entering the cell
  (the CK only says "Did not find matching NavMeshInfo ... Creating a temporary one" when loading it).
- Light plugins (ESL): new records must keep object IDs inside the light range, and so must the header's next
  object ID, which the CK hands out from (it once went to 0x1010).

Nothing here needs the game's masters loaded: it reads only the plugin.
"""
from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .. import games
from .records import FLAG_ESL, Plugin


@dataclass
class Finding:
    level: str      # error | warning | info
    text: str


@dataclass
class CheckReport:
    plugin: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.level == 'error' for f in self.findings)

    def add(self, level: str, text: str) -> None:
        self.findings.append(Finding(level, text))

    def summary(self) -> str:
        errors = sum(f.level == 'error' for f in self.findings)
        lines = [f'{self.plugin}: {"OK" if self.ok else f"{errors} error(s)"}']
        lines += [f'  {f.level.upper():7} {f.text}' for f in self.findings]
        return '\n'.join(lines)


def _default_game() -> games.Game:
    try:
        from .. import config
        return config.load().game
    except SystemExit:
        return games.GAMES['fo4']


def check(path: str | Path, game: games.Game | None = None, expected_masters: list[str] | None = None,
          masters_before: list[str] | None = None) -> CheckReport:
    """expected_masters: the exact master list the plugin must have. masters_before: its masters before an edit
    (a CK save); any master added since is an error."""
    game = game or _default_game()
    path = Path(path)
    report = CheckReport(path.name)
    try:
        p = Plugin.load(path)
    except (OSError, ValueError, struct.error) as e:
        report.add('error', f'cannot read the plugin: {e}')
        return report
    masters = p.masters
    report.add('info', f'masters: {", ".join(masters) or "none"}')
    _check_masters(report, game, masters, expected_masters, masters_before)
    _check_navmesh_index(report, p)
    if game.light_plugins and (p.header.flags & FLAG_ESL or path.suffix.lower() == '.esl'):
        _check_light(report, game, p)
    return report


def _check_masters(report, game, masters, expected, before) -> None:
    if expected is not None and masters != list(expected):
        report.add('error', f'masters are {masters}, expected {list(expected)}')
    if before is not None:
        added = [m for m in masters if m not in before]
        removed = [m for m in before if m not in masters]
        if added:
            report.add('error', f'masters added since before: {", ".join(added)} (a Creation Kit save with these '
                                'loaded? It adds them through the navmesh index, NAVI)')
        if removed:
            report.add('info', f'masters removed since before: {", ".join(removed)}')
    official = [m for m in masters if m in game.masters]
    if official != sorted(official, key=game.masters.index):
        report.add('warning', f'official masters out of load order: {official}')


# Navmeshes with this record flag are never in a navmesh index: Fallout4.esm has 95 of them and no indexed one has
# it (all 7799 others are indexed).
NAVM_UNINDEXED = 0x80000000


def _check_navmesh_index(report, p: Plugin) -> None:
    own_navm = {r.formid for r in p.records('NAVM') if p.is_own(r.formid) and not r.flags & NAVM_UNINDEXED}
    navi = [r for r in p.records('NAVI')]
    if not navi:
        if own_navm:
            report.add('error', f'{len(own_navm)} new navmesh(es) but no navmesh index (NAVI): finalize the '
                                'navmesh in the Creation Kit and save')
        return
    listed = []
    for r in navi:
        listed += [struct.unpack_from('<I', s.data)[0] for s in r.subrecords if s.sig == 'NVMI' and len(s.data) >= 4]
    by_file = Counter(p.owner_of(fid) if (fid >> 24) <= len(p.masters) else '(invalid file index)' for fid in listed)
    report.add('info', 'navmesh index entries: ' + ', '.join(f'{n} {name}' for name, n in by_file.most_common()))
    bad_index = [fid for fid in listed if (fid >> 24) > len(p.masters)]
    if bad_index:
        report.add('error', f'navmesh index entries with no such file: {_ids(bad_index)}')
    own_listed = {fid for fid in listed if p.is_own(fid) and (fid >> 24) == len(p.masters)}
    missing = sorted(own_navm - own_listed)
    stray = sorted(own_listed - own_navm)
    if missing:
        report.add('error', f'{len(missing)} navmesh(es) with no navmesh index entry: {_ids(missing)} - the game '
                            'can crash in that cell; regenerate or finalize the navmesh in the Creation Kit')
    if stray:
        report.add('error', f'navmesh index entries for navmeshes the plugin does not have: {_ids(stray)}')


def _check_light(report, game, p: Plugin) -> None:
    hedr = p.header.get('HEDR')
    version, _count, next_id = struct.unpack('<fII', hedr.data[:12]) if hedr and len(hedr.data) >= 12 else (0, 0, 0)
    lo, hi = game.light_range(version)
    own = [r for r in p.records() if p.is_own(r.formid)]
    outside = [r for r in own if not lo <= (r.formid & 0xFFFFFF) <= hi]
    report.add('info', f'light plugin (HEDR {version:.2f}): {len(own)} new records, object IDs '
                       f'{lo:03X}-{hi:03X} allowed ({hi - lo + 1 - len(own)} free)')
    if outside:
        sample = ', '.join(f'{r.sig} {r.formid & 0xFFFFFF:X}' for r in outside[:8])
        report.add('error', f'{len(outside)} record(s) outside the light range: {sample}'
                            f'{" ..." if len(outside) > 8 else ""} (xEdit build fixes these; the CK\'s Compact '
                            'Form IDs also renumbers, breaking anything that points at the old IDs)')
    # A warning: Bethesda's own Creation Club ESLs ship with it past the range. It only matters for the next forms
    # the CK creates, which the record check above catches once they are saved.
    if (next_id & 0xFFFFFF) > hi + 1:
        report.add('warning', f'header next object ID {next_id & 0xFFFFFF:X} is past the light range: forms the '
                              'CK creates next get IDs outside it (xEdit build resets it)')


def _ids(fids) -> str:
    return ', '.join(f'{f:08X}' for f in list(fids)[:10]) + (' ...' if len(fids) > 10 else '')
