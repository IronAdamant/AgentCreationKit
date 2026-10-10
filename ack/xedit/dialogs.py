"""Allowlist-driven handling of xEdit dialog windows.

Only dialogs matched by a rule are ever acted on. Anything else is captured (title, controls,
screenshot) to the run log and left untouched, so an unexpected prompt can never be confirmed blindly.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import win32

RULES_FILE = Path(__file__).with_name('rules.json')


def _caption(s: str) -> str:
    """Normalise a button caption: drop '&' accelerators and surrounding whitespace."""
    return s.replace('&', '').strip().lower()


@dataclass
class Rule:
    """One known dialog and what to do with it.

    title:   regex the window title must fully match
    cls:     optional regex the window class must fully match
    text:    optional regex that must match one of the window's text controls
    buttons: captions that must all be present (case-insensitive, '&' ignored)
    action:  'click:<caption>' | 'close' | 'ignore' | 'main' (marks xEdit's main window)
    when:    'always' | 'save' (only in runs that want changes saved) | 'nosave'
    """
    name: str
    title: str
    action: str
    cls: str | None = None
    text: str | None = None
    buttons: list[str] = field(default_factory=list)
    when: str = 'always'

    def matches(self, w: win32.Window) -> bool:
        if not re.fullmatch(self.title, w.title, re.I):
            return False
        if self.cls and not re.fullmatch(self.cls, w.cls, re.I):
            return False
        if self.text and not any(re.search(self.text, t, re.I) for t in w.texts):
            return False
        have = {_caption(b.text) for b in w.buttons}
        return all(_caption(b) in have for b in self.buttons)

    def applies(self, save: bool) -> bool:
        return self.when == 'always' or (self.when == 'save') == save


def load_rules(path: Path = RULES_FILE) -> list[Rule]:
    return [Rule(**r) for r in json.loads(path.read_text(encoding='utf8'))['rules']]


@dataclass
class Event:
    t: float
    kind: str          # 'action' | 'unknown' | 'main'
    rule: str | None
    title: str
    cls: str
    detail: str


class DialogWatcher:
    def __init__(self, pid: int, log_dir: Path, save: bool, rules: list[Rule] | None = None):
        self.pid = pid
        self.log_dir = log_dir
        self.save = save
        self.rules = rules if rules is not None else load_rules()
        self.events: list[Event] = []
        self.main_hwnd: int | None = None
        self._seen: set[int] = set()
        self._acted: set[tuple[int, str]] = set()

    def _record(self, kind, rule, w, detail):
        self.events.append(Event(time.time(), kind, rule, w.title, w.cls, detail))

    def _capture(self, w: win32.Window) -> None:
        """Save everything visible about an unrecognised window for later review."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stem = self.log_dir / f'unknown_{len(self._seen):02d}_{w.hwnd:x}'
        info = {
            'title': w.title, 'class': w.cls, 'owner': w.owner,
            'buttons': [b.text for b in w.buttons],
            'texts': w.texts,
            'controls': [(c.cls, c.text, c.visible) for c in w.controls],
        }
        stem.with_suffix('.json').write_text(json.dumps(info, indent=1), encoding='utf8')
        bmp = win32.screenshot_bmp(w.hwnd)
        if bmp:
            stem.with_suffix('.bmp').write_bytes(bmp)
        self._record('unknown', None, w, f'captured to {stem.name}; buttons={info["buttons"]}')

    def poll(self) -> None:
        for w in win32.process_windows(self.pid):
            rule = next((r for r in self.rules if r.applies(self.save) and r.matches(w)), None)
            if rule is None:
                if w.hwnd not in self._seen:
                    self._seen.add(w.hwnd)
                    self._capture(w)
                continue
            if rule.action == 'main':
                if self.main_hwnd != w.hwnd:
                    self.main_hwnd = w.hwnd
                    self._record('main', rule.name, w, '')
                continue
            if rule.action == 'ignore' or (w.hwnd, rule.action) in self._acted:
                continue
            self._acted.add((w.hwnd, rule.action))
            if rule.action == 'close':
                win32.close(w.hwnd)
                self._record('action', rule.name, w, 'closed')
            elif rule.action.startswith('click:'):
                want = _caption(rule.action[6:])
                btn = next((b for b in w.buttons if _caption(b.text) == want), None)
                if btn and btn.enabled:
                    win32.click(btn)
                    self._record('action', rule.name, w, f'clicked {btn.text!r}')
                else:
                    self._acted.discard((w.hwnd, rule.action))  # retry once the button is usable

    @property
    def unknown(self) -> list[Event]:
        return [e for e in self.events if e.kind == 'unknown']
