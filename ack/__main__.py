"""AgentCreationKit command line.

    python -m ack xedit run <script> <plugin> [--save] [--timeout S]
    python -m ack xedit scripts
    python -m ack plugin info <path>
    python -m ack plugin check <path> [--masters M ...]
    python -m ack ba2 extract <archive> <pattern>... --out DIR
    python -m ack ck <command> ...        drive a running Creation Kit (python -m ack ck -h)
    python -m ack ck run <steps.txt>      several ck commands in one session that always ends closed
"""
from __future__ import annotations

import argparse
import shlex
import sys
from collections import Counter
from pathlib import Path


def cmd_xedit_run(a):
    from .xedit.runner import Refused, run
    params = dict(kv.split('=', 1) for kv in a.param)
    try:
        report = run(a.script, a.plugin, save=a.save, timeout=a.timeout, params=params, also_load=a.also_load)
    except Refused as e:
        print(f'refused: {e}')
        return 2
    print(report.summary())
    return 0 if report.outcome == 'done' and not report.unknown_dialogs else 1


def cmd_xedit_scripts(a):
    from .xedit.runner import SCRIPTS
    for p in sorted(SCRIPTS.glob('*.pas')):
        first = p.read_text(encoding='utf8').split('}', 1)[0].strip('{ \n').splitlines()
        print(f'{p.stem:18} {" ".join(s.strip() for s in first)}')
    return 0


def cmd_plugin_info(a):
    from .plugin import Plugin
    p = Plugin.load(a.path)
    counts = Counter(r.sig for r in p.records())
    own = sum(1 for r in p.records() if p.is_own(r.formid))
    total = sum(counts.values())
    print(f'{p.name}: {total} records ({own} new, {total - own} overrides), localized={p.is_localized}')
    print('masters:', ', '.join(p.masters) or 'none')
    for sig, n in counts.most_common():
        print(f'  {sig} {n}')
    return 0


def _data_path(name: str) -> Path:
    """A plugin path, or a bare file name in the game's Data folder."""
    if Path(name).exists():
        return Path(name)
    from . import config
    return config.load().data_dir / name


def cmd_plugin_check(a):
    from . import games
    from .plugin.check import check
    report = check(_data_path(a.path), games.get(a.game) if a.game else None, a.masters)
    print(report.summary())
    return 0 if report.ok else 1


def cmd_ba2_extract(a):
    from .archive import extract_general, extract_textures
    got = extract_general(a.archive, a.patterns, a.out) if 'texture' not in Path(a.archive).name.lower() \
        else [g[0] for g in extract_textures(a.archive, a.patterns, a.out)]
    print('\n'.join(got) or 'no matches')
    return 0


def _axes(values):
    """['10', '_', '0'] -> (10.0, None, 0.0); '_' keeps that axis."""
    return None if values is None else tuple(None if v == '_' else float(v) for v in values)


def _print_save(result) -> int:
    for title, texts in result.events:
        print(f'dialog {title!r}: {" | ".join(texts)}')
    if result.report is None:
        print('written, NOT checked: ack cannot tell the active file (pass --plugin NAME)')
        return 1
    print(result.report.summary())
    return 0 if result.ok else 1


def cmd_ck(a, ck=None):
    from .ck import CreationKit
    c = a.cmd
    if c == 'launch':
        ck = CreationKit.launch()
        print(ck.title)
        return 0
    if c == 'run':
        return cmd_ck_run(a)
    if c == 'close':
        from .ck import lifecycle
        if not lifecycle.running():
            lifecycle.clear_state()
            print('the Creation Kit is not running')
            return 0
        result = (ck or CreationKit()).close(force=a.force)
        for title, texts, done in result.events:
            print(f'dialog {title!r}: {" | ".join(texts)} -> {done}')
        print(f'{result.outcome} without saving')
        return 0
    ck = ck or CreationKit()
    if c == 'status':
        st = ck.status()
        print(f'title:     {ck.title}\nselection: {st.selection}\ncamera:    {st.camera} in {st.cell}')
    elif c == 'arrange':
        ck.focus()
        ck.arrange()
    elif c == 'shot':
        print(ck.screenshot(a.out, 'main' if a.main else 'render'))
    elif c == 'load':
        for title, texts in ck.load(a.plugins, a.active):
            print(f'dialog {title!r}: {" | ".join(texts)}')
        print(ck.title)
    elif c == 'cell':
        ck.open_cell(a.editor_id)
        print(ck.status().cell)
    elif c == 'refs':
        for edid, fid, typ in ck.references():
            print(f'{fid}  {typ:14} {edid}')
    elif c == 'select':
        ck.focus()
        ck.select(a.editor_id)
        print(ck.status().selection)
    elif c == 'ref':
        if a.pos is None and a.rot is None and a.scale is None:
            d = ck.read_reference(a.editor_id)
        else:
            d = ck.edit_reference(a.editor_id, _axes(a.pos), _axes(a.rot), a.scale)
        print(f'{d.editor_id}: position {d.position} rotation {d.rotation} scale {d.scale}')
    elif c == 'menu':
        ck.menu(a.path)
        if a.list:
            print('\n'.join(ck.menu_items()))
    elif c == 'camera':
        ck.focus()
        if a.action == 'top':
            ck.top_view()
        elif a.action == 'bright':
            ck.bright_light()
        elif a.action == 'zoom':
            ck.zoom(int(a.values[0]))
        elif a.action == 'orbit':
            ck.orbit(float(a.values[0]), float(a.values[1]))
        elif a.action == 'pan':
            ck.pan(float(a.values[0]), float(a.values[1]))
        elif a.action == 'look':
            pivot = ck.look(*map(float, a.values[:3]))
            print('pivot', tuple(round(v) for v in pivot))
        print(ck.camera())
    elif c == 'save':
        return _print_save(ck.save(a.plugin, a.masters))
    elif c == 'place':
        d = ck.place(a.base, a.editor_id, _axes(a.pos), _axes(a.rot), a.scale)
        print(f'{d.editor_id or "(no editor ID)"}: position {d.position} rotation {d.rotation} scale {d.scale}')
    elif c == 'delete':
        ck.delete(a.editor_id)
        print('deleted', a.editor_id)
    elif c == 'compact':
        result = ck.compact_form_ids(a.plugin, a.masters)
        print(result.message)
        return _print_save(result)
    elif c == 'navmesh':
        for title, texts in ck.generate_navmesh():
            print(f'dialog {title!r}: {" | ".join(texts)}')
    return 0


def cmd_ck_run(a):
    """Run the steps file's ck commands in one session: launch if needed, then always close without saving at the
    end, even when a step fails. Save with a `save` step; a failed save check stops the run."""
    from .ck import CKError, CreationKit, lifecycle
    if lifecycle.running() and not lifecycle.read_state():
        print('refused: a Creation Kit that ack did not start is open (it may hold unsaved work): close it first')
        return 2
    lines = [l.strip() for l in Path(a.steps).read_text(encoding='utf8').splitlines()]
    steps = [l for l in lines if l and not l.startswith('#')]
    parser = build_parser()
    parsed = []
    for step in steps:  # parse everything first: a typo should fail before the CK is touched
        args = parser.parse_args(['ck'] + shlex.split(step))
        if args.cmd in ('run', 'launch', 'close'):
            raise SystemExit(f'step {step!r}: run/launch/close are handled by ck run itself')
        parsed.append((step, args))
    code = 0
    ck = CreationKit.launch()
    try:
        for step, args in parsed:
            print(f'> {step}')
            if cmd_ck(args, ck) != 0:
                print(f'step failed: {step}')
                code = 1
                break
    except (CKError, OSError) as e:
        print(f'step failed: {e}')
        code = 1
    finally:
        result = ck.close()
        print(f'Creation Kit {result.outcome} without saving')
    return code


def cmd_papyrus_log(a):
    from ack.game import papyrus_log
    if a.state:
        papyrus_log.set_logging(a.state == 'on')
    print(f'Papyrus logging is {"on" if papyrus_log.is_on() else "off"} ({papyrus_log.ini_path()})')
    print(f'logs: {papyrus_log.logs_dir()}')
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog='ack', description='AgentCreationKit: tools for AI agents working on Bethesda mods')
    sub = ap.add_subparsers(dest='area', required=True)

    x = sub.add_parser('xedit', help='run FO4Edit/xEdit scripts unattended').add_subparsers(dest='cmd', required=True)
    r = x.add_parser('run', help='run a script from ack/xedit/scripts against a plugin')
    r.add_argument('script', help='bundled script name, or path to a .pas template using {{TARGET}} and {{OUT}}')
    r.add_argument('plugin', help='plugin file name as it appears in the Data folder')
    r.add_argument('--save', action='store_true', help='let xEdit save changed plugins when it closes (without this flag nothing is ever written)')
    r.add_argument('--timeout', type=float, default=900)
    r.add_argument('--param', action='append', default=[], metavar='KEY=VALUE',
                   help='fill a {{KEY}} placeholder in the script, e.g. EDITS=path/to/edits.txt')
    r.add_argument('--also-load', action='append', default=[], metavar='PLUGIN',
                   help='also load this plugin after the target (e.g. an add-on that uses it as a master)')
    r.set_defaults(func=cmd_xedit_run)
    x.add_parser('scripts', help='list available scripts').set_defaults(func=cmd_xedit_scripts)

    p = sub.add_parser('plugin', help='inspect plugin files').add_subparsers(dest='cmd', required=True)
    i = p.add_parser('info')
    i.add_argument('path')
    i.set_defaults(func=cmd_plugin_info)
    ch = p.add_parser('check', help='masters, navmesh index and light-plugin ID range: the things a CK save breaks')
    ch.add_argument('path', help='plugin path, or a file name in the Data folder')
    ch.add_argument('--masters', nargs='+', metavar='MASTER', help='the exact master list it must have')
    ch.add_argument('--game', help='game profile (default: config.local.json)')
    ch.set_defaults(func=cmd_plugin_check)

    b = sub.add_parser('ba2', help='BA2 archives').add_subparsers(dest='cmd', required=True)
    e = b.add_parser('extract')
    e.add_argument('archive')
    e.add_argument('patterns', nargs='+', help=r'glob(s) on archive paths, e.g. meshes\effects\laser*')
    e.add_argument('--out', required=True)
    e.set_defaults(func=cmd_ba2_extract)

    k = sub.add_parser('ck', help='drive a running Creation Kit').add_subparsers(dest='cmd', required=True)
    k.add_parser('launch', help='start the Creation Kit (if needed) and wait until it is ready')
    cl = k.add_parser('close', help='close the Creation Kit WITHOUT saving (only one ack launched, unless --force)')
    cl.add_argument('--force', action='store_true', help="also close a CK ack did not start (loses its unsaved work)")
    rn = k.add_parser('run', help='run a file of ck commands (one per line) in one session, then always close it '
                                  'without saving, even if a step fails')
    rn.add_argument('steps')
    k.add_parser('status', help='active file, selection, camera position')
    k.add_parser('arrange', help='bring to front; big render window, Cell View and Object Window on the left')
    s_ = k.add_parser('shot', help='screenshot the render window (brings the CK to the front)')
    s_.add_argument('out')
    s_.add_argument('--main', action='store_true', help='the whole CK window instead')
    l_ = k.add_parser('load', help='File > Data: load exactly these plugins')
    l_.add_argument('plugins', nargs='+')
    l_.add_argument('--active')
    c_ = k.add_parser('cell', help='open an interior cell in the render window')
    c_.add_argument('editor_id')
    k.add_parser('refs', help='references in the loaded cell')
    se = k.add_parser('select', help='select a reference and move the camera to it')
    se.add_argument('editor_id')
    rf = k.add_parser('ref', help="read a reference, or set its position/rotation/scale ('_' keeps an axis)")
    rf.add_argument('editor_id')
    rf.add_argument('--pos', nargs=3, metavar=('X', 'Y', 'Z'))
    rf.add_argument('--rot', nargs=3, metavar=('X', 'Y', 'Z'))
    rf.add_argument('--scale', type=float)
    pl = k.add_parser('place', help='drag a base object from the Object Window into the cell, then set it up')
    pl.add_argument('base', help='base object editor ID')
    pl.add_argument('--editor-id')
    pl.add_argument('--pos', nargs=3, metavar=('X', 'Y', 'Z'))
    pl.add_argument('--rot', nargs=3, metavar=('X', 'Y', 'Z'))
    pl.add_argument('--scale', type=float)
    de = k.add_parser('delete', help='delete a reference from the loaded cell')
    de.add_argument('editor_id')
    m_ = k.add_parser('menu', help="run a menu command, e.g. 'View/Top' or 'Finalize Cell NavMeshes'")
    m_.add_argument('path')
    m_.add_argument('--list', action='store_true', help='also print every menu path')
    ca = k.add_parser('camera', help='top | bright | zoom N (positive = in) | pan DX DY | orbit DX DY (pixels; Shift+mouse around the selection) | look YAW PITCH [DISTANCE] (degrees: bearing from the selection, 0 = north; elevation, 90 = overhead)')
    ca.add_argument('action', choices=['top', 'bright', 'zoom', 'pan', 'orbit', 'look'])
    ca.add_argument('values', nargs='*')
    sv = k.add_parser('save', help='File > Save, then check the saved plugin (masters, navmesh index, light IDs)')
    k.add_parser('navmesh', help='Recast navmesh for the loaded cell, then finalize')
    co = k.add_parser('compact', help='Compact Active File Form IDs (renumbers a CK-edited ESL into its ID range). '
                                      'It writes the file itself, so it is checked like save')
    for p_ in (sv, co):
        p_.add_argument('--plugin', help='the active file, if ack cannot tell')
        p_.add_argument('--masters', nargs='+', metavar='MASTER', help='the exact master list it must have')
    for p_ in k.choices.values():
        p_.set_defaults(func=cmd_ck)

    pl = sub.add_parser('papyrus-log', help="switch the game's Papyrus script log on/off (its custom ini, e.g. Fallout4Custom.ini)")
    pl.add_argument('state', nargs='?', choices=['on', 'off'], help='omit to show the current state')
    pl.set_defaults(func=cmd_papyrus_log)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.area != 'ck':
        return a.func(a)
    from .ck import CKError
    try:
        return a.func(a)
    except CKError as e:
        print(f'error: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
