"""Drive a running Creation Kit (Fallout 4) the way a level designer would.

Two kinds of control are used:
- Window messages (menu commands, list views, buttons). These work in the background.
- Real input (ack.ck.inputs) for the render window and for dialogs that ignore text set by message. These need
  the Creation Kit in the foreground: call focus() first, and only when nobody is using the PC.

Findings this is built on (FO4 CK, Windows 11, 120 dpi):
- The CK is not DPI-aware: coordinates posted to its windows are scaled by 96/dpi, so they are multiplied by
  dpi_scale before posting. This process makes itself DPI-aware so screen coordinates are real pixels.
- File > Data opens hidden; ticking a plugin is a double-click on its row, and a row's image index tells
  whether it is ticked (1) or not (0).
- Double-clicking a reference in the Cell View selects it and moves the camera to it. Its Reference dialog
  (position/rotation/scale edit boxes) opens from the row's right-click menu > Edit; the boxes must be typed
  into: text set with WM_SETTEXT is ignored when OK is pressed.
- The render window only draws while visible; captures copy the screen.
- Cell editor IDs are shown without underscores; list rows end in " *" for records in the active file.
"""
from __future__ import annotations

import ctypes
import math
import re
import time
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import Path

from .. import win32
from . import capture, inputs
from .remote import Remote

user32 = win32.user32
user32.GetMenu.argtypes = [W.HWND]
user32.GetMenu.restype = W.HMENU
user32.GetSubMenu.argtypes = [W.HMENU, ctypes.c_int]
user32.GetSubMenu.restype = W.HMENU
user32.GetMenuItemCount.argtypes = [W.HMENU]
user32.GetMenuItemID.argtypes = [W.HMENU, ctypes.c_int]
user32.GetMenuItemID.restype = W.UINT
user32.GetMenuStringW.argtypes = [W.HMENU, W.UINT, W.LPWSTR, ctypes.c_int, W.UINT]
user32.GetDlgItem.argtypes = [W.HWND, ctypes.c_int]
user32.GetDlgItem.restype = W.HWND
user32.IsWindow.argtypes = [W.HWND]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
user32.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
user32.ClientToScreen.argtypes = [W.HWND, ctypes.POINTER(W.POINT)]
user32.GetForegroundWindow.restype = W.HWND
user32.GetWindowThreadProcessId.restype = W.DWORD
user32.AttachThreadInput.argtypes = [W.DWORD, W.DWORD, W.BOOL]
user32.SetFocus.argtypes = [W.HWND]

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware: real pixels everywhere
except OSError:
    user32.SetProcessDPIAware()

WM_COMMAND, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0111, 0x0201, 0x0202, 0x0203
BM_CLICK = 0x00F5

# Reference dialog control IDs
REF_EDITOR_ID = 5500
REF_POSITION = (1095, 1096, 1097)
REF_ROTATION = (1113, 1115, 1117)
REF_SCALE = 1025
# Object Window control IDs
OW_FILTER, OW_TREE, OW_LIST = 2581, 2093, 1041


class CKError(RuntimeError):
    pass


@dataclass
class Status:
    selection: str          # "EDID (FORMID)" of the selected reference, or ''
    camera: tuple[float, float, float] | None
    cell: str
    raw: list[str]


@dataclass
class RefData:
    editor_id: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    scale: float


def _process_of(hwnd: int) -> int:
    return win32.window_pid(hwnd)


class CreationKit:
    @classmethod
    def launch(cls, game_dir: str | Path | None = None, timeout: float = 180) -> 'CreationKit':
        """Start CreationKit.exe (if it isn't running) and wait for its main window."""
        if not any(_cls(h) == 'Creation Kit' for h in _top_windows()):
            import subprocess
            from .. import config
            game = Path(game_dir) if game_dir else config.load().game_dir
            subprocess.Popen([str(game / 'CreationKit.exe')], cwd=str(game))
            end = time.time() + timeout
            while not any(_cls(h) == 'Creation Kit' for h in _top_windows()):
                if time.time() > end:
                    raise CKError('the Creation Kit did not start')
                time.sleep(1)
        ck = cls()
        ck.wait_idle(timeout, settle=3)
        return ck

    def __init__(self):
        mains = [h for h in _top_windows() if _cls(h) == 'Creation Kit']
        if not mains:
            raise CKError('the Creation Kit is not running')
        self.main = mains[0]
        self.pid = _process_of(self.main)
        self.remote = Remote(self.pid)
        dpi = ctypes.windll.user32.GetDpiForSystem() if hasattr(ctypes.windll.user32, 'GetDpiForSystem') else 96
        self.dpi_scale = dpi / 96.0
        self._menu = None

    # ---------------------------------------------------------------- windows
    def windows(self, visible_only: bool = True) -> list[win32.Window]:
        return win32.process_windows(self.pid, visible_only)

    def window(self, title: str = None, cls: str = None, visible_only: bool = True) -> int | None:
        for w in self.windows(visible_only):
            if (title is None or w.title == title or w.title.startswith(title)) and (cls is None or w.cls == cls):
                return w.hwnd
        return None

    @property
    def render(self) -> int:
        return self.window(cls='MonitorClass')

    @property
    def cell_view(self) -> int:
        return self.window('Cell View')

    def _cell_view_lists(self) -> tuple[int, int]:
        """(references of the loaded cell, cell list)"""
        lvs = [c.hwnd for c in win32.child_controls(self.cell_view) if c.cls == 'SysListView32']
        return lvs[0], lvs[1]

    @property
    def title(self) -> str:
        return win32._text(self.main)

    def focus(self) -> None:
        """Bring the Creation Kit to the front (needed for real input and captures)."""
        if user32.GetForegroundWindow() == self.main:
            return
        # Windows only lets the process that sent the last input take the foreground, so send a harmless key
        # first. (Alt is the usual trick, but it leaves the CK's menu bar active, which then swallows the wheel.)
        inputs.tap(inputs.VK['shift'])
        user32.SetForegroundWindow(self.main)
        time.sleep(0.3)

    def arrange(self, screen=(1920, 1080)) -> None:
        """Maximise the CK and lay out: Cell View top-left, Object Window bottom-left, big render window right."""
        user32.ShowWindow(self.main, 3)
        sw, sh = screen
        top, left_w = 95, int(sw * 0.29)
        user32.SetWindowPos(self.render, None, left_w, top, sw - left_w, sh - top - 95, 0x14)
        user32.SetWindowPos(self.cell_view, None, 0, top, left_w, int((sh - top) * 0.62), 0x14)
        ow = self.window('Object Window')
        if ow:
            user32.SetWindowPos(ow, None, 0, top + int((sh - top) * 0.62), left_w, int((sh - top) * 0.3), 0x14)

    # ---------------------------------------------------------------- menus and dialogs
    def menu_items(self) -> dict[str, int]:
        """'File/Data...' -> command ID, for every item of the main menu."""
        if self._menu is None:
            self._menu = {}

            def walk(menu, prefix):
                for i in range(user32.GetMenuItemCount(menu)):
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetMenuStringW(menu, i, buf, 256, 0x400)
                    name = buf.value.split('\t')[0].replace('&', '')
                    sub = user32.GetSubMenu(menu, i)
                    if sub:
                        walk(sub, prefix + name + '/')
                    elif name:
                        self._menu[prefix + name] = user32.GetMenuItemID(menu, i)

            walk(user32.GetMenu(self.main), '')
        return self._menu

    def menu(self, path: str) -> None:
        """Run a main-menu command by path ('NavMesh/Finalize Cell NavMeshes') or ID."""
        items = self.menu_items()
        cid = int(path) if str(path).isdigit() else items.get(path)
        if cid is None:
            matches = [k for k in items if k.lower().endswith(path.lower())]
            if len(matches) != 1:
                raise CKError(f'menu item {path!r}: {"ambiguous " + str(matches) if matches else "not found"}')
            cid = items[matches[0]]
        user32.PostMessageW(self.main, WM_COMMAND, cid, 0)

    def dialogs(self) -> dict[int, str]:
        return {w.hwnd: w.title for w in self.windows() if w.cls == '#32770'}

    def wait_dialog(self, title: str, timeout: float = 15, visible_only: bool = True) -> int:
        end = time.time() + timeout
        while time.time() < end:
            h = self.window(title, '#32770', visible_only)
            if h:
                return h
            time.sleep(0.25)
        raise CKError(f'no {title!r} dialog after {timeout}s')

    def press(self, dialog: int, button_text: str, post: bool = False) -> None:
        """Click a dialog button. post: don't wait for the click to be handled - for a button that opens a modal
        prompt (a sent click only returns once that prompt is answered, so nothing could answer it)."""
        for c in win32.child_controls(dialog):
            if c.text.replace('&', '') == button_text:
                (user32.PostMessageW if post else user32.SendMessageW)(c.hwnd, BM_CLICK, 0, 0)
                return
        raise CKError(f'no {button_text!r} button')

    def wait_idle(self, timeout: float = 600, settle: float = 2.0,
                  handle_dialog=None) -> list[tuple[str, list[str]]]:
        """Wait until the main window is enabled and no progress window is up. Dialogs that appear meanwhile are
        recorded; handle_dialog(hwnd, title, texts) may answer them (return True when handled)."""
        seen, events = set(), []
        end, quiet_since = time.time() + timeout, None
        known = {'Layers', 'Warnings', 'Navmesh', 'Cell View', 'Object Window'}
        while time.time() < end:
            busy = False
            for w in self.windows():
                if w.cls != '#32770' or w.title in known:
                    continue
                if w.title == '':
                    busy = True  # progress window
                    continue
                if w.hwnd not in seen:
                    seen.add(w.hwnd)
                    texts = [c.text for c in w.controls if c.text]
                    events.append((w.title, texts))
                    if handle_dialog and handle_dialog(w.hwnd, w.title, texts):
                        continue
                busy = True
            if not busy and user32.IsWindowEnabled(self.main):
                quiet_since = quiet_since or time.time()
                if time.time() - quiet_since >= settle:
                    return events
            else:
                quiet_since = None
            time.sleep(0.5)
        raise CKError(f'still busy after {timeout}s; dialogs seen: {events}')

    # ---------------------------------------------------------------- status
    def status(self) -> Status:
        sb = [c for c in win32.child_controls(self.main) if c.cls == 'msctls_statusbar32'][0].hwnd
        parts = self.remote.status_parts(sb)
        cam = re.search(r'cam: (-?[\d.]+), (-?[\d.]+), (-?[\d.]+) \(([^)]*)\)', parts[1] if len(parts) > 1 else '')
        return Status(parts[0] if parts else '', tuple(map(float, cam.groups()[:3])) if cam else None,
                      cam.group(4) if cam else '', parts)

    # ---------------------------------------------------------------- list clicks
    def _click_row(self, lv: int, row: int, xoff: int = 12, double: bool = True) -> None:
        """Click a list row with posted mouse messages (the CK tracks its own selection from clicks; setting the
        row state alone is not enough)."""
        self.remote.lv_ensure_visible(lv, row)
        self.remote.lv_select(lv, row)
        rc = self.remote.lv_rect(lv, row)
        s = self.dpi_scale
        lp = (int((rc.top + rc.bottom) / 2 * s) << 16) | int((rc.left + xoff) * s)
        msgs = [(WM_LBUTTONDOWN, 1), (WM_LBUTTONUP, 0)]
        if double:
            msgs += [(WM_LBUTTONDBLCLK, 1), (WM_LBUTTONUP, 0)]
        for msg, wp in msgs:
            user32.PostMessageW(lv, msg, wp, lp)

    def _dblclick_row(self, lv: int, row: int, xoff: int = 12) -> None:
        self._click_row(lv, row, xoff, double=True)

    @staticmethod
    def _name(row_text: str) -> str:
        return row_text.rstrip(' *')

    # ---------------------------------------------------------------- data
    def load(self, plugins: list[str], active: str | None = None, timeout: float = 600) -> list:
        """File > Data: tick exactly these plugins (masters load automatically), set the active file, OK."""
        before = {w.hwnd for w in self.windows(False) if w.title == 'Data'}
        self.menu('File/Data...')
        end = time.time() + 15
        dlg = None
        while time.time() < end and not dlg:
            time.sleep(0.3)
            dlg = next((w.hwnd for w in self.windows(False) if w.title == 'Data' and w.hwnd not in before), None) \
                or self.window('Data', '#32770', False)
        if not dlg:
            raise CKError('File > Data did not open')
        user32.ShowWindow(dlg, 5)  # it opens hidden
        controls = win32.child_controls(dlg)
        lv = next(c.hwnd for c in controls if c.cls == 'SysListView32')
        names = self.remote.lv_column(lv)
        missing = [p for p in plugins if p not in names]
        if missing:
            self.press(dlg, 'Cancel')
            raise CKError(f'not in the Data folder: {missing}')
        # The dialog remembers the last session's ticks: toggle every row whose tick differs from what is wanted.
        for row, name in enumerate(names):
            ticked = self.remote.lv_image(lv, row) == 1
            if ticked != (name in plugins):
                self._dblclick_row(lv, row)
                time.sleep(0.4)
                if (self.remote.lv_image(lv, row) == 1) == ticked:
                    self.press(dlg, 'Cancel')
                    raise CKError(f'could not toggle {name}')
        if active:
            row = names.index(active)
            if self.remote.lv_text(lv, row, 1) != 'Active File':  # the button toggles: never press it twice
                self._click_row(lv, row, xoff=60, double=False)  # click the name, not the tick box
                time.sleep(0.5)
                self.press(dlg, 'Set as Active File')
                time.sleep(0.5)
            if self.remote.lv_text(lv, row, 1) != 'Active File':
                self.press(dlg, 'Cancel')
                raise CKError(f'could not make {active} the active file')
        self.press(dlg, 'OK', post=True)  # OK may open the "no active file" prompt: answered in wait_idle below
        time.sleep(2)

        def answer(hwnd, title, texts):
            if title == 'IMPORTANT WARNING' or 'generated warnings on load' in ' '.join(texts):
                self.press(hwnd, 'OK')
                return True
            if not active and 'not set a file as the active file' in ' '.join(texts):
                self.press(hwnd, 'Yes')  # loading to look only: nothing can be saved into the plugins
                return True
            return False

        return self.wait_idle(timeout, settle=4, handle_dialog=answer)

    def save(self) -> list:
        self.menu('File/Save')
        return self.wait_idle(120, settle=2)

    # ---------------------------------------------------------------- cells and references
    def cells(self) -> list[str]:
        return [self._name(t) for t in self.remote.lv_column(self._cell_view_lists()[1])]

    def open_cell(self, editor_id: str, timeout: float = 120) -> None:
        """Load an interior cell into the render window (Cell View must be showing interiors)."""
        lv = self._cell_view_lists()[1]
        names = self.cells()
        want = editor_id.replace('_', '')
        rows = [i for i, n in enumerate(names) if n.replace('_', '') == want]
        if not rows:
            raise CKError(f'cell {editor_id} not in the Cell View list (is the worldspace set to Interiors?)')
        self._dblclick_row(lv, rows[0])
        end = time.time() + timeout
        while time.time() < end:
            if win32._text(self.render).replace('_', '').startswith(want + ' '):
                self.wait_idle(timeout, settle=1)
                return
            time.sleep(0.5)
        raise CKError(f'cell {editor_id} did not load')

    def references(self) -> list[tuple[str, str, str]]:
        """(editor ID or base name, form ID, type) for every reference in the loaded cell."""
        lv = self._cell_view_lists()[0]
        return [(self._name(self.remote.lv_text(lv, i, 0)), self.remote.lv_text(lv, i, 1),
                 self.remote.lv_text(lv, i, 3)) for i in range(self.remote.lv_count(lv))]

    def select(self, editor_id: str, attempts: int = 3) -> None:
        """Select a reference (editor ID, or form ID as shown in the Cell View) and move the camera to it."""
        lv, row = self._ref_row(editor_id)
        fid = self.remote.lv_text(lv, row, 1)
        for _ in range(attempts):
            self._dblclick_row(lv, row, xoff=40)
            end = time.time() + 5
            while time.time() < end:
                sel = self.status().selection
                if sel.startswith(editor_id + ' ') or sel.endswith(f'({fid})'):
                    time.sleep(0.5)  # let the camera arrive
                    return
                time.sleep(0.25)
        raise CKError(f'{editor_id} did not become the selection')

    def render_point(self, fx: float = 0.5, fy: float = 0.5) -> tuple[int, int]:
        """Screen pixel at a fraction of the render window's client area (0.5, 0.5 = centre)."""
        r = W.RECT()
        user32.GetClientRect(self.render, ctypes.byref(r))
        pt = W.POINT(int(r.right * fx), int(r.bottom * fy))
        user32.ClientToScreen(self.render, ctypes.byref(pt))
        return pt.x, pt.y

    def _ref_row(self, ref: str) -> tuple[int, int]:
        """(Cell View reference list, row) for an editor ID or a form ID."""
        lv = self._cell_view_lists()[0]
        names = [self._name(t) for t in self.remote.lv_column(lv)]
        ids = self.remote.lv_column(lv, 1)
        if ref in names:
            return lv, names.index(ref)
        if ref.upper() in ids:
            return lv, ids.index(ref.upper())
        raise CKError(f'reference {ref} is not in the loaded cell')

    def _row_menu(self, ref: str, downs: int) -> None:
        """Right-click a reference's Cell View row and pick the context-menu item `downs` places down
        (1 View, 2 Edit). (Its Delete item asks to confirm and then deletes nothing.)"""
        self.focus()
        lv, row = self._ref_row(ref)
        self.remote.lv_ensure_visible(lv, row)
        rc = self.remote.lv_rect(lv, row)
        origin = W.POINT(0, 0)
        user32.ClientToScreen(lv, ctypes.byref(origin))
        x, y = origin.x + (rc.left + 40) * self.dpi_scale, origin.y + (rc.top + rc.bottom) / 2 * self.dpi_scale
        inputs.click(x, y)
        time.sleep(0.3)
        inputs.click(x, y, name='right')
        time.sleep(0.8)
        for _ in range(downs):  # the menu drops keys sent faster than it redraws
            inputs.tap(inputs.VK['down'])
            time.sleep(0.25)
        inputs.tap(inputs.VK['enter'])

    def _open_reference(self, ref: str) -> int:
        """Open a reference's Reference dialog (Cell View row > right-click > Edit) and check it is that one."""
        self._row_menu(ref, 2)
        dlg = self.wait_dialog('Reference', 10)
        edid, form = self._dialog_identity(dlg)
        if ref not in (edid, form) and ref.upper() != form:
            self.press(dlg, 'Cancel')
            raise CKError(f'opened {edid or form} instead of {ref}')
        return dlg

    @staticmethod
    def _dialog_identity(dlg: int) -> tuple[str, str]:
        """(editor ID, form ID) shown in a Reference dialog."""
        labels = [c.text for c in win32.child_controls(dlg) if c.cls == 'Static']
        form = next((m.group(1) for t in labels if (m := re.match(r'\(([0-9A-F]{8})\)', t))), '')
        return win32.control_text(user32.GetDlgItem(dlg, REF_EDITOR_ID)), form

    @staticmethod
    def _read_ref(dlg: int) -> RefData:
        val = lambda cid: float(win32.control_text(user32.GetDlgItem(dlg, cid)) or 0)
        return RefData(win32.control_text(user32.GetDlgItem(dlg, REF_EDITOR_ID)),
                       tuple(val(c) for c in REF_POSITION), tuple(val(c) for c in REF_ROTATION), val(REF_SCALE))

    def read_reference(self, editor_id: str) -> RefData:
        dlg = self._open_reference(editor_id)
        data = self._read_ref(dlg)
        self.press(dlg, 'Cancel')
        return data

    def edit_reference(self, editor_id: str, position=None, rotation=None, scale=None) -> RefData:
        """Set any of position (x, y, z), rotation (degrees x, y, z) and scale through the Reference dialog.
        None leaves a value (or one axis) unchanged. Returns the values read back before pressing OK."""
        dlg = self._open_reference(editor_id)
        user32.SetForegroundWindow(dlg)
        time.sleep(0.2)
        fields = []
        for ids, values in ((REF_POSITION, position), (REF_ROTATION, rotation)):
            if values is not None:
                fields += [(cid, v) for cid, v in zip(ids, values) if v is not None]
        if scale is not None:
            fields.append((REF_SCALE, scale))
        for cid, v in fields:
            self._type_into(user32.GetDlgItem(dlg, cid), f'{v:.4f}')
        data = self._read_ref(dlg)
        self.press(dlg, 'OK')
        time.sleep(0.5)
        return data

    @staticmethod
    def _type_into(edit: int, text: str) -> None:
        """Click an edit box, replace its text by typing (the CK ignores text set by message), Tab out."""
        r = W.RECT()
        user32.GetWindowRect(edit, ctypes.byref(r))
        inputs.click((r.left + r.right) / 2, (r.top + r.bottom) / 2)
        inputs.tap(ord('A'), ('ctrl',))
        inputs.type_text(text)
        inputs.tap(inputs.VK['tab'])
        time.sleep(0.1)

    def place(self, base_editor_id: str, editor_id: str | None = None, position=None, rotation=None,
              scale=None) -> RefData:
        """Place a new reference like a designer: find the base object in the Object Window (*All, filtered),
        drag it into the middle of the render window, then set its editor ID and transform in its Reference
        dialog. New forms get IDs from the CK's own counter: run compact_form_ids() before saving an ESL."""
        self.focus()
        ow = self.window('Object Window')
        if not ow:
            raise CKError('the Object Window is not open')
        # Keep the list's first row visible: other tool windows (Cell View) like to sit on top of it.
        user32.SetWindowPos(ow, None, 0, 720, 560, 300, 0x10)
        tv, lv, flt = (user32.GetDlgItem(ow, i) for i in (OW_TREE, OW_LIST, OW_FILTER))
        everything = [h for h, t in self.remote.tv_items(tv) if t == '*All']
        if everything:
            self.remote.tv_select(tv, everything[0])
        self._type_into(flt, base_editor_id)
        time.sleep(1.5)
        rows = [self._name(t) for t in self.remote.lv_column(lv)]
        if base_editor_id not in rows:
            raise CKError(f'{base_editor_id} not found in the Object Window (got {rows[:5]})')
        row = rows.index(base_editor_id)
        self.remote.lv_ensure_visible(lv, row)
        rc = self.remote.lv_rect(lv, row)
        origin = W.POINT(0, 0)
        user32.ClientToScreen(lv, ctypes.byref(origin))
        start = (origin.x + (rc.left + 40) * self.dpi_scale, origin.y + (rc.top + rc.bottom) / 2 * self.dpi_scale)
        before = {r[1] for r in self.references()}
        drop = self.render_point()
        inputs.move(*start)
        time.sleep(0.3)
        inputs.drag('left', start, drop, steps=50)
        time.sleep(1.5)
        new = [r for r in self.references() if r[1] not in before]
        if len(new) != 1:
            raise CKError(f'drag and drop placed {len(new)} references')
        # Something else may be under the drop point, so open the new reference's dialog the safe way.
        return self.set_up_reference(new[0][1], editor_id, position, rotation, scale)

    def set_up_reference(self, ref: str, editor_id: str | None = None, position=None, rotation=None,
                         scale=None) -> RefData:
        """Give a reference (editor ID or form ID) an editor ID and transform through its Reference dialog."""
        dlg = self._open_reference(ref)
        user32.SetForegroundWindow(dlg)
        time.sleep(0.2)
        if editor_id:
            self._type_into(user32.GetDlgItem(dlg, REF_EDITOR_ID), editor_id)
        for ids, values in ((REF_POSITION, position), (REF_ROTATION, rotation)):
            for cid, v in zip(ids, values or ()):
                if v is not None:
                    self._type_into(user32.GetDlgItem(dlg, cid), f'{v:.4f}')
        if scale is not None:
            self._type_into(user32.GetDlgItem(dlg, REF_SCALE), f'{scale:.4f}')
        data = self._read_ref(dlg)
        self.press(dlg, 'OK')
        time.sleep(0.5)
        return data

    def delete(self, editor_id: str) -> None:
        """Delete a reference (editor ID or form ID)."""
        # The Cell View's own Delete (key or menu) asks to confirm and then does nothing; the render window's
        # Delete key removes its selection. Give the render window keyboard focus without clicking (a click
        # could select something else), check the selection, press Delete.
        self.focus()
        self.select(editor_id)
        selected = self.status().selection
        me, ck_thread = ctypes.windll.kernel32.GetCurrentThreadId(), user32.GetWindowThreadProcessId(self.main, None)
        user32.AttachThreadInput(me, ck_thread, True)
        user32.SetFocus(self.render)
        user32.AttachThreadInput(me, ck_thread, False)
        time.sleep(0.3)
        if self.status().selection != selected:
            raise CKError(f'the selection changed before deleting {editor_id}')
        inputs.tap(inputs.VK['delete'])
        time.sleep(1)
        confirm = self.window('Confirm', '#32770')
        if confirm:
            self.press(confirm, 'Yes')
        end = time.time() + 5  # the Cell View list catches up a moment later
        while time.time() < end:
            left = self.references()
            if editor_id not in [r[0] for r in left] and editor_id.upper() not in [r[1] for r in left]:
                return
            time.sleep(0.5)
        raise CKError(f'{editor_id} is still in the cell')

    # ---------------------------------------------------------------- camera
    def top_view(self) -> None:
        self.menu('View/Top')

    def zoom(self, clicks: int) -> None:
        """Positive zooms in (moves the camera along its view), negative zooms out. Needs focus()."""
        # The render window ignores the wheel until it has seen the cursor arrive: move, nudge, wait. (A middle
        # click to focus it made it ignore the wheel instead.)
        x, y = self.render_point()
        inputs.move(x, y)
        time.sleep(0.2)
        inputs.move(x + 3, y + 3)
        time.sleep(0.3)
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            inputs.wheel(step)
            time.sleep(0.05)
        self._nudge()

    def pan(self, dx: float, dy: float) -> None:
        """Drag the view by (dx, dy) screen pixels with the middle button. Needs focus()."""
        x, y = self.render_point()
        inputs.drag('middle', (x, y), (x + dx, y + dy), steps=30)
        self._nudge()

    def orbit(self, dx: float, dy: float, steps: int = 60) -> None:
        """Orbit the camera around the selection: hold Shift and move the mouse by (dx, dy) screen pixels
        (about 600 px per quarter turn horizontally; dy tilts). Needs focus()."""
        x, y = self.render_point()
        inputs.move(x, y)
        time.sleep(0.15)
        inputs.key(inputs.VK['shift'], True)
        for i in range(1, steps + 1):
            inputs.move(x + dx * i / steps, y + dy * i / steps)
            time.sleep(0.02)
        inputs.key(inputs.VK['shift'], False)
        self._nudge()

    def camera(self) -> tuple[float, float, float]:
        """Camera position from the status bar (fresh: nudges the cursor first)."""
        self._nudge()
        cam = self.status().camera
        if cam is None:
            raise CKError('no camera position in the status bar (is a cell loaded?)')
        return cam

    def look(self, yaw: float, pitch: float, distance: float | None = None, tolerance: float = 4.0,
             attempts: int = 12) -> tuple[float, float, float]:
        """Put the camera at compass bearing `yaw` (degrees; 0 = north of the selection, 90 = east) and elevation
        `pitch` (degrees above the selection; 90 = overhead), `distance` units from the orbit pivot, looking at
        the selection. Select something first. Closed loop: the pivot is found from a few probing orbits (the
        camera stays on a sphere around it), then orbits and wheel clicks are corrected until the status bar's
        camera position agrees. Returns the pivot."""
        self.focus()
        pitch = max(-80.0, min(80.0, pitch))  # stay clear of the poles
        # Start from the top view, then tilt with the mouse moving up: that swings the camera down the south side
        # and keeps it upright (tilting the other way over the pole turns the picture upside down). View/Top puts
        # the camera off the orbit sphere, so the probes start after the first tilt.
        self.top_view()
        pivot = None
        for size in (40, 80, 120):
            self.orbit(0, -size, steps=20)
            probes = [self.camera()]
            for dx, dy in ((size, 0), (size, 0), (0, -size)):
                self.orbit(dx, dy, steps=20)
                probes.append(self.camera())
            try:
                guess = _sphere_centre(probes)
            except CKError:
                continue
            radii = [math.dist(p, guess) for p in probes]
            # a good fit has every probe at the same distance, and the pivot no further than the camera can be
            if max(radii) - min(radii) < 0.05 * max(radii) + 10 and max(radii) < 20000:
                pivot = guess
                break
        if pivot is None:
            raise CKError('could not find the orbit pivot (is something selected?)')

        def angles(c):
            v = [c[i] - pivot[i] for i in range(3)]
            flat = math.hypot(v[0], v[1])
            return (math.degrees(math.atan2(v[0], v[1])) % 360, math.degrees(math.atan2(v[2], flat)),
                    math.hypot(flat, v[2]))

        def turn(a, b):
            return (b - a + 180) % 360 - 180

        # signed pixels per degree, measured from the probes and refined after every move
        a = [angles(c) for c in probes]
        kx = size / turn(a[1][0], a[2][0]) if abs(turn(a[1][0], a[2][0])) > 1 else 2.6
        ky = -size / (a[3][1] - a[2][1]) if abs(a[3][1] - a[2][1]) > 1 else 2.3
        cam = probes[-1]
        for _ in range(attempts):
            y0, p0, _d = angles(cam)
            ey, ep = turn(y0, yaw), pitch - p0
            if abs(ey) <= tolerance and abs(ep) <= tolerance:
                break
            dx = max(-400.0, min(400.0, ey * kx))
            dy = max(-400.0, min(400.0, ep * ky))
            self.orbit(dx, dy, steps=max(10, int(max(abs(dx), abs(dy)) / 5)))
            cam = self.camera()
            y1, p1, _d = angles(cam)
            if abs(dx) > 20 and abs(turn(y0, y1)) > 3 and abs(dx / turn(y0, y1)) < 15:
                kx = dx / turn(y0, y1)
            if abs(dy) > 20 and abs(p1 - p0) > 3 and abs(dy / (p1 - p0)) < 15:
                ky = dy / (p1 - p0)
        if distance:
            per_click = None
            for _ in range(8):
                d0 = angles(cam)[2]
                if abs(d0 - distance) <= max(20.0, distance * 0.05):
                    break
                clicks = 1 if per_click is None else int(round((d0 - distance) / per_click)) or (1 if d0 > distance else -1)
                self.zoom(max(-30, min(30, clicks)))
                cam = self.camera()
                moved = d0 - angles(cam)[2]
                if per_click is None and abs(moved) > 1:
                    per_click = moved / clicks
                elif per_click is None:
                    break
        return pivot

    def _nudge(self) -> None:
        """The status bar's camera position only refreshes when the cursor moves over the render window."""
        time.sleep(0.3)
        x, y = self.render_point()
        inputs.move(x + 7, y + 7)
        time.sleep(0.3)
        inputs.move(x, y)
        time.sleep(0.2)

    def bright_light(self) -> None:
        self.menu('View/Bright Light')

    # ---------------------------------------------------------------- output
    def screenshot(self, path: str | Path, what: str = 'render') -> Path:
        """Save the render window (or 'main' for the whole CK) as a PNG. Brings the CK to the front."""
        self.focus()
        time.sleep(0.5)
        return capture.save_window(self.render if what == 'render' else self.main, path,
                                   client_only=what == 'render')

    def compact_form_ids(self) -> str:
        """File > Compact Active File Form IDs (answers its confirmation). The CK hands out new form IDs from its
        own counter, which can be past 0xFFF in an ESL: run this after creating forms in the CK, then save.
        Renumbering invalidates saves made with the plugin and any other plugin that points at its records."""
        self.menu('File/Compact Active File Form IDs')
        confirm = self.wait_dialog('Confirm', 15)
        self.press(confirm, 'Yes')
        done = self.wait_dialog('Done', 120)
        message = ' '.join(c.text for c in win32.child_controls(done) if c.text and c.text != 'OK')
        self.press(done, 'OK')
        self.wait_idle(60, settle=1)
        return message

    # ---------------------------------------------------------------- navmesh
    def generate_navmesh(self, timeout: float = 2400) -> list:
        """Recast navmesh for the loaded cell with the default settings, then Finalize Cell NavMeshes. Recast only
        covers the selection when something is selected: clear it first for the whole cell. A big cell (over a
        thousand objects) takes several minutes."""
        if self.status().selection not in ('', 'Camera'):
            raise CKError(f'{self.status().selection} is selected: Recast would only cover it. Clear the selection.')
        self.menu('NavMesh/Generation/Recast-Based Generation')
        dlg = self.wait_dialog('Recast Navmesh Generation')
        self.press(dlg, 'OK')
        events = self.wait_idle(timeout, settle=3)
        self.menu('NavMesh/Finalize Cell NavMeshes')
        events += self.wait_idle(timeout / 2, settle=3)
        nav = self.window('Navmesh', '#32770')
        if nav:
            win32.close(nav)  # its toolbar blocks saving
        return events


def _sphere_centre(points) -> tuple[float, float, float]:
    """Centre of the sphere through four points: |p - c|^2 is the same for all, so (p_i - p_0) . c * 2 =
    |p_i|^2 - |p_0|^2 for i = 1..3, solved by Cramer's rule."""
    p0 = points[0]
    rows, rhs = [], []
    for p in points[1:4]:
        rows.append([2 * (p[i] - p0[i]) for i in range(3)])
        rhs.append(sum(p[i] ** 2 - p0[i] ** 2 for i in range(3)))

    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

    d = det(rows)
    if abs(d) < 1e-6:
        raise CKError('camera probes were coplanar; cannot find the orbit pivot')
    out = []
    for col in range(3):
        m = [r[:] for r in rows]
        for i in range(3):
            m[i][col] = rhs[i]
        out.append(det(m) / d)
    return tuple(out)


def _top_windows() -> list[int]:
    out = []
    win32.user32.EnumWindows(win32.WNDENUMPROC(lambda h, _: out.append(h) or True), 0)
    return out


def _cls(hwnd: int) -> str:
    return win32._cls(hwnd)
