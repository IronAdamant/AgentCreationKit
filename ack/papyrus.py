"""Compile a mod's Papyrus scripts with the Creation Kit's compiler.

    python -m ack papyrus compile SOURCE --out DIR [SCRIPT ...] [--import DIR ...] [--debug] [--f4se]

SOURCE is the mod's source root: the folder whose subfolders are script namespaces (source/User, holding
MyMod/MyScript.psc for the script MyMod:MyScript). Without SCRIPT names every .psc under it is compiled. Each .pex
goes to DIR/<namespace>/, e.g. data/Scripts/MyMod/MyScript.pex.

Imports, in order: SOURCE, every --import, then the game's vanilla sources (Data/Scripts/Source/Base for Fallout 4,
unpacked by the Creation Kit). Script Extender sources are left out unless --f4se: a mod that compiles against them
without meaning to needs the script extender to run (F4SE replaces ScriptObject.psc and others in Scripts/Source).
--debug keeps Debug.Trace calls; release builds (the default) strip them.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class Compiled:
    script: str
    pex: Path | None        # None: it failed
    output: str = ''        # the compiler's messages (errors)


def compiler(cfg: config.Config) -> Path:
    return cfg.game_dir / 'Papyrus Compiler' / 'PapyrusCompiler.exe'


def vanilla_sources(cfg: config.Config) -> Path:
    """The game's own script sources (through MO2 if they were installed as a mod)."""
    g = cfg.game
    return cfg.data_path(f'{g.papyrus_sources}/{g.papyrus_flags}').parent


def script_names(source: Path) -> list[str]:
    return [':'.join(p.relative_to(source).with_suffix('').parts) for p in sorted(source.rglob('*.psc'))]


def compile_scripts(source: Path, out: Path, scripts: list[str] | None = None, imports: list[Path] | None = None,
                    debug: bool = False, f4se: bool = False, cfg: config.Config | None = None) -> list[Compiled]:
    cfg = cfg or config.load()
    if not cfg.game.papyrus_sources:
        raise SystemExit(f'no Papyrus settings for {cfg.game.name} in ack/games.py')
    exe, base = compiler(cfg), vanilla_sources(cfg)
    if not exe.exists():
        raise SystemExit(f'no Papyrus compiler at {exe}: it comes with the Creation Kit')
    if not (base / cfg.game.papyrus_flags).exists():
        raise SystemExit(f'the vanilla script sources are not unpacked in {base}: the Creation Kit unpacks them '
                         f'(Base.zip in the same folder) the first time it starts')
    paths = [source.resolve()] + [Path(p).resolve() for p in imports or []]
    if f4se:   # F4SE's ScriptObject etc. replace the vanilla ones, so they come before them
        paths.append(cfg.data_path('Scripts/Source/F4SE.psc').parent)
    paths.append(base)
    flags = [] if debug else list(cfg.game.papyrus_release)

    def one(name: str) -> Compiled:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([str(exe), name, '-i=' + ';'.join(str(p) for p in paths), f'-o={tmp}',
                                f'-f={base / cfg.game.papyrus_flags}', '-quiet'] + flags,
                               capture_output=True, text=True, errors='replace')
            built = next(Path(tmp).rglob(name.split(':')[-1] + '.pex'), None)
            if r.returncode != 0 or not built:
                return Compiled(name, None, (r.stdout + r.stderr).strip())
            dest = out.joinpath(*name.split(':')[:-1]) / built.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(built, dest)
            return Compiled(name, dest)

    with ThreadPoolExecutor(4) as pool:     # the compiler starts slowly; a few at once
        return list(pool.map(one, scripts or script_names(source)))
