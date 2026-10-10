"""AgentCreationKit command line.

    python -m ack xedit run <script> <plugin> [--save] [--timeout S]
    python -m ack xedit scripts
    python -m ack plugin info <path>
    python -m ack ba2 extract <archive> <pattern>... --out DIR
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


def cmd_xedit_run(a):
    from .xedit.runner import run
    params = dict(kv.split('=', 1) for kv in a.param)
    report = run(a.script, a.plugin, save=a.save, timeout=a.timeout, params=params)
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


def cmd_ba2_extract(a):
    from .archive import extract_general, extract_textures
    got = extract_general(a.archive, a.patterns, a.out) if 'texture' not in Path(a.archive).name.lower() \
        else [g[0] for g in extract_textures(a.archive, a.patterns, a.out)]
    print('\n'.join(got) or 'no matches')
    return 0


def main(argv=None):
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
    r.set_defaults(func=cmd_xedit_run)
    x.add_parser('scripts', help='list available scripts').set_defaults(func=cmd_xedit_scripts)

    p = sub.add_parser('plugin', help='inspect plugin files').add_subparsers(dest='cmd', required=True)
    i = p.add_parser('info')
    i.add_argument('path')
    i.set_defaults(func=cmd_plugin_info)

    b = sub.add_parser('ba2', help='BA2 archives').add_subparsers(dest='cmd', required=True)
    e = b.add_parser('extract')
    e.add_argument('archive')
    e.add_argument('patterns', nargs='+', help=r'glob(s) on archive paths, e.g. meshes\effects\laser*')
    e.add_argument('--out', required=True)
    e.set_defaults(func=cmd_ba2_extract)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == '__main__':
    sys.exit(main())
