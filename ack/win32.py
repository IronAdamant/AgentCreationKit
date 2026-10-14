"""Thin ctypes wrappers over the Win32 calls needed to inspect and drive another program's windows.

No third-party dependencies. Windows only.
"""
from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from dataclasses import dataclass, field

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowEnabled.argtypes = [wintypes.HWND]
user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetWindow.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

GW_OWNER = 4
BM_CLICK = 0x00F5
WM_CLOSE = 0x0010
PW_RENDERFULLCONTENT = 0x2


@dataclass
class Control:
    hwnd: int
    cls: str
    text: str
    visible: bool
    enabled: bool

    @property
    def is_button(self) -> bool:
        # Standard and Delphi VCL button classes all subclass the Win32 BUTTON control.
        return self.cls.lower() in ('button', 'tbutton', 'tbitbtn')


@dataclass
class Window:
    hwnd: int
    pid: int
    cls: str
    title: str
    owner: int
    controls: list[Control] = field(default_factory=list)

    @property
    def buttons(self) -> list[Control]:
        return [c for c in self.controls if c.is_button and c.visible]

    @property
    def texts(self) -> list[str]:
        return [c.text for c in self.controls if c.text and not c.is_button and c.visible]


def _text(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _cls(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def child_controls(hwnd: int) -> list[Control]:
    out: list[Control] = []

    def cb(h, _):
        out.append(Control(h, _cls(h), _text(h), bool(user32.IsWindowVisible(h)), bool(user32.IsWindowEnabled(h))))
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return out


def process_windows(pid: int, visible_only: bool = True) -> list[Window]:
    """Top-level windows belonging to a process, with their child controls."""
    found: list[Window] = []

    def cb(h, _):
        if window_pid(h) == pid and (not visible_only or user32.IsWindowVisible(h)):
            found.append(Window(h, pid, _cls(h), _text(h), user32.GetWindow(h, GW_OWNER) or 0))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    for w in found:
        w.controls = child_controls(w.hwnd)
    return found


def click(control: Control) -> None:
    """Press a button without moving the mouse or needing focus."""
    user32.SendMessageW(control.hwnd, BM_CLICK, 0, 0)


def close(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def screenshot_bmp(hwnd: int) -> bytes | None:
    """Render a window (even if covered) to a 32-bit BMP. Returns None if it can't be captured."""
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)
        # BITMAPINFOHEADER for a top-down 32bpp DIB
        bih = struct.pack('<IiiHHIIiiII', 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        info = ctypes.create_string_buffer(bih, 44)
        pixels = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mdc, bmp, 0, h, pixels, info, 0):
            return None
        file_hdr = struct.pack('<2sIHHI', b'BM', 14 + 40 + w * h * 4, 0, 0, 54)
        return file_hdr + bih + pixels.raw
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, wdc)


def control_text(hwnd: int) -> str:
    """Full text of a control in another process (WM_GETTEXT; GetWindowText only returns captions there).

    xEdit's log memo answers WM_GETTEXTW with 8-bit text, so read raw bytes and decode them as UTF-8 if the
    buffer does not hold real UTF-16."""
    n = user32.SendMessageW(hwnd, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
    buf = ctypes.create_string_buffer(2 * n + 4)
    user32.SendMessageW(hwnd, 0x000D, n + 1, ctypes.cast(buf, ctypes.c_void_p).value)  # WM_GETTEXT
    raw = buf.raw
    if n > 1 and raw[1:2] == b'\x00':  # real UTF-16 text
        return raw.decode('utf-16-le', 'replace').split('\x00')[0]
    return raw.split(b'\x00')[0].decode('utf-8', 'replace')


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
SYNCHRONIZE, PROCESS_TERMINATE = 0x00100000, 0x0001


def process_alive(pid: int) -> bool:
    h = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        return False
    try:
        return kernel32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT: still running
    finally:
        kernel32.CloseHandle(h)


def kill(pid: int) -> bool:
    """Terminate a process. A terminated program writes nothing more (no save on the way out)."""
    h = kernel32.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, False, pid)
    if not h:
        return False
    try:
        kernel32.TerminateProcess(h, 1)
        return kernel32.WaitForSingleObject(h, 10000) == 0
    finally:
        kernel32.CloseHandle(h)


def pids_of(exe_name: str) -> list[int]:
    """Process IDs of every running program with this exe name."""
    import csv
    import subprocess
    out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {exe_name}', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout
    return [int(row[1]) for row in csv.reader(out.splitlines()) if len(row) > 1 and row[0].lower() == exe_name.lower()]
