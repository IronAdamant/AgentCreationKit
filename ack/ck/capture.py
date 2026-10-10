"""Screen captures saved as PNG, with no image library.

The render window draws with Direct3D and only while it is visible, so captures copy what is on screen: the window
must be uncovered (CreationKit.focus() first).
"""
from __future__ import annotations

import ctypes
import struct
import zlib
from ctypes import wintypes as W
from pathlib import Path

from .. import win32

user32, gdi32 = win32.user32, win32.gdi32
user32.GetDC.argtypes = [W.HWND]
user32.GetDC.restype = W.HDC
gdi32.BitBlt.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HDC, ctypes.c_int,
                         ctypes.c_int, W.DWORD]
SRCCOPY = 0x00CC0020


def grab_screen(left: int, top: int, width: int, height: int) -> tuple[int, int, bytes]:
    """Copy a screen rectangle; returns (width, height, top-down BGRA pixels)."""
    sdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, width, height)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        gdi32.BitBlt(mdc, 0, 0, width, height, sdc, left, top, SRCCOPY)
        info = ctypes.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0), 44)
        pixels = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(mdc, bmp, 0, height, pixels, info, 0)
        return width, height, pixels.raw
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(None, sdc)


def png_bytes(width: int, height: int, bgra: bytes) -> bytes:
    """Encode top-down BGRA pixels as an RGB PNG."""
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        rgb = bytearray(width * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        rows += b'\x00' + rgb  # filter type 0 per row

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 6)) + chunk(b'IEND', b''))


def save_window(hwnd: int, path: str | Path, client_only: bool = True) -> Path:
    """Save what is on screen inside a window (its client area by default) as a PNG."""
    if client_only:
        r = W.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(r))
        pt = W.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        left, top, width, height = pt.x, pt.y, r.right, r.bottom
    else:
        r = W.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        left, top, width, height = r.left, r.top, r.right - r.left, r.bottom - r.top
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes(*grab_screen(left, top, width, height)))
    return path
