"""Make BA2 archives with the Creation Kit's Archive2, and read an archive's header.

    python -m ack ba2 pack ROOT OUT.ba2 [FOLDER ...] [--textures] [--keep-version]
    python -m ack ba2 info ARCHIVE [--files]

ROOT is laid out like Data (ROOT/Scripts/MyMod/..., ROOT/Meshes/MyMod/...). Fallout 4 loads "<plugin> - Main.ba2"
and "<plugin> - Textures.ba2" beside a plugin by themselves: Main is a General archive of everything but textures
(the default FOLDERs: every folder in ROOT except Textures), Textures a DDS archive (--textures: ROOT/Textures).

The archive is stamped with the game profile's BA2 version (Fallout 4: 1). The next-gen Archive2 writes version 8,
which the old-gen game (1.10.163, still widely played) silently skips, so its players get no scripts and no
textures; the layout is the same and every PC version reads version 1. --keep-version leaves Archive2's number.

PC only. Xbox archives must come from the Creation Kit's Generate when uploading to Bethesda.net: Archive2's
XBoxDDS format keeps the textures in the PC layout, which the console shows as pink. `ba2 info` shows each
texture's tile mode (8 = the PC layout) to check what Generate made.
"""
from __future__ import annotations

import struct
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

PC_TILE_MODE = 8


def archive2(cfg: config.Config) -> Path:
    return cfg.game_dir / 'Tools' / 'Archive2' / 'Archive2.exe'


def pack(root: Path, out: Path, folders: list[str] | None = None, textures: bool = False,
         keep_version: bool = False, cfg: config.Config | None = None) -> Path:
    cfg = cfg or config.load()
    if cfg.game.ba2_version is None:
        raise SystemExit(f'ack does not pack archives for {cfg.game.name} (ba2_version in ack/games.py)')
    exe = archive2(cfg)
    if not exe.exists():
        raise SystemExit(f'no Archive2 at {exe}: it comes with the Creation Kit')
    root = root.resolve()
    if folders is None:
        folders = ['Textures'] if textures else sorted(p.name for p in root.iterdir()
                                                        if p.is_dir() and p.name.lower() != 'textures')
    missing = [f for f in folders if not (root / f).is_dir()]
    if missing or not folders:
        raise SystemExit(f'nothing to pack: no {", ".join(missing) or "folders"} in {root}')
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    r = subprocess.run([str(exe), ','.join(str(root / f) for f in folders), f'-create={out}', f'-root={root}',
                        f'-format={"DDS" if textures else "General"}', '-compression=Default', '-quiet'],
                       capture_output=True, text=True, errors='replace')
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f'Archive2 failed for {out.name}:\n{r.stdout}\n{r.stderr}')
    if not keep_version:
        stamp(out, cfg.game.ba2_version)
    return out


def stamp(path: Path, version: int) -> None:
    """Set a BA2's version number (header bytes 4-8); only between versions that share the layout (1, 7, 8)."""
    with open(path, 'r+b') as f:
        head = f.read(8)
        old = int.from_bytes(head[4:8], 'little')
        if head[:4] != b'BTDX' or old not in (1, 7, 8):
            raise SystemExit(f'{path.name}: not a Fallout 4 BA2 (version {old})')
        f.seek(4)
        f.write(version.to_bytes(4, 'little'))


@dataclass
class Info:
    version: int
    kind: str                                   # GNRL (general) or DX10 (textures)
    files: list[str] = field(default_factory=list)
    tile_modes: list[int] = field(default_factory=list)   # DX10: per file

    def summary(self, files: bool = False) -> str:
        lines = [f'BA2 version {self.version}, {"general" if self.kind == "GNRL" else "textures"}, '
                 f'{len(self.files)} files']
        if self.tile_modes:
            modes = Counter(self.tile_modes)
            lines.append('tile modes: ' + ', '.join(f'{m} x{n}' for m, n in sorted(modes.items())) +
                         (f'  ({PC_TILE_MODE} = PC layout)' if PC_TILE_MODE in modes else ''))
        if files:
            lines += [f'  {n}' + (f'  tile {t}' if self.tile_modes else '')
                      for n, t in zip(self.files, self.tile_modes or [None] * len(self.files))]
        return '\n'.join(lines)


def info(path: Path) -> Info:
    b = Path(path).read_bytes()
    magic, version, kind, n, names_at = struct.unpack_from('<4sI4sIQ', b, 0)
    if magic != b'BTDX':
        raise SystemExit(f'{Path(path).name}: not a BA2 archive')
    if version not in (1, 7, 8):
        raise SystemExit(f'{Path(path).name}: BA2 version {version} is not a Fallout 4 archive')
    result = Info(version, kind.decode('latin1'))
    o = 24
    if result.kind == 'DX10':
        for _ in range(n):
            chunks, tile = b[o + 13], b[o + 23]
            result.tile_modes.append(tile)
            o += 24 + chunks * 24
    o = names_at
    for _ in range(n):
        size, = struct.unpack_from('<H', b, o)
        result.files.append(b[o + 2:o + 2 + size].decode('latin1'))
        o += 2 + size
    return result
