"""Real mouse and keyboard input (SendInput), for the parts of the Creation Kit that only respond to a person:
the render window, and dialogs that ignore text set by message.

This moves the actual cursor and types into whatever window has focus, so the Creation Kit must be in the
foreground and nobody should be using the PC at the time.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes as W

user32 = ctypes.WinDLL('user32', use_last_error=True)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', W.DWORD), ('dwFlags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD), ('time', W.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class _Union(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('pad', ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', W.DWORD), ('u', _Union)]


user32.SendInput.argtypes = [W.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.VkKeyScanW.argtypes = [W.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short

MOUSE_MOVE_ABSOLUTE = 0x0001 | 0x8000
MOUSE_WHEEL = 0x0800
BUTTONS = {'left': (0x0002, 0x0004), 'right': (0x0008, 0x0010), 'middle': (0x0020, 0x0040)}
VK = {'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12, 'tab': 0x09, 'enter': 0x0D, 'esc': 0x1B, 'delete': 0x2E,
      'space': 0x20, 'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28}


def _send(*inputs: INPUT) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags: int, data: int = 0, x: int = 0, y: int = 0) -> INPUT:
    return INPUT(0, _Union(mi=MOUSEINPUT(x, y, data & 0xFFFFFFFF, flags, 0, 0)))


def move(x: float, y: float) -> None:
    """Put the cursor at screen pixel (x, y)."""
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    _send(_mouse(MOUSE_MOVE_ABSOLUTE, x=round(x * 65535 / (sw - 1)), y=round(y * 65535 / (sh - 1))))


def button(name: str, down: bool) -> None:
    _send(_mouse(BUTTONS[name][0 if down else 1]))


def click(x: float, y: float, name: str = 'left', double: bool = False) -> None:
    move(x, y)
    time.sleep(0.05)
    for _ in range(2 if double else 1):
        button(name, True)
        button(name, False)
        time.sleep(0.06)


def wheel(clicks: int) -> None:
    """Positive = wheel up (away from the user)."""
    _send(_mouse(MOUSE_WHEEL, data=120 * clicks))


def key(vk: int, down: bool) -> None:
    _send(INPUT(1, _Union(ki=KEYBDINPUT(vk, 0, 0 if down else 0x0002, 0, 0))))


def tap(vk: int, mods: tuple[str, ...] = ()) -> None:
    for m in mods:
        key(VK[m], True)
    key(vk, True)
    time.sleep(0.02)
    key(vk, False)
    for m in reversed(mods):
        key(VK[m], False)


def type_text(text: str) -> None:
    for ch in text:
        scan = user32.VkKeyScanW(ch)
        tap(scan & 0xFF, ('shift',) if scan & 0x100 else ())
        time.sleep(0.01)


def drag(name: str, start: tuple[float, float], end: tuple[float, float], steps: int = 25,
         mods: tuple[str, ...] = ()) -> None:
    """Press a button at start, move in small steps to end, release (with modifier keys held throughout)."""
    for m in mods:
        key(VK[m], True)
    move(*start)
    time.sleep(0.05)
    button(name, True)
    time.sleep(0.05)
    for i in range(1, steps + 1):
        move(start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
        time.sleep(0.015)
    time.sleep(0.05)
    button(name, False)
    for m in reversed(mods):
        key(VK[m], False)
