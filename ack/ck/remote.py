"""Read and drive common controls that live in another process (the Creation Kit).

List views and status bars take pointers to structures, which only mean something inside the owning process, so
those structures are written into a block of memory allocated in the Creation Kit with VirtualAllocEx.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W

from .. import win32

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenProcess.restype = W.HANDLE
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD, W.DWORD]
kernel32.VirtualFreeEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD]
kernel32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
kernel32.WriteProcessMemory.argtypes = kernel32.ReadProcessMemory.argtypes
kernel32.CloseHandle.argtypes = [W.HANDLE]

send = win32.user32.SendMessageW

PROCESS_VM = 0x0008 | 0x0010 | 0x0020 | 0x0400  # VM_OPERATION | VM_READ | VM_WRITE | QUERY_INFORMATION
LVM_GETITEMCOUNT, LVM_GETITEMRECT, LVM_ENSUREVISIBLE = 0x1004, 0x100E, 0x1013
LVM_SETITEMSTATE, LVM_GETITEMTEXTW, LVM_GETITEMW = 0x102B, 0x1073, 0x104B
SB_GETPARTS, SB_GETTEXTLENGTHW, SB_GETTEXTW = 0x0406, 0x040C, 0x040D
TEXT_AT = 4096  # offset of the text buffer inside the remote block


class LVITEM(ctypes.Structure):
    _fields_ = [('mask', W.UINT), ('iItem', ctypes.c_int), ('iSubItem', ctypes.c_int), ('state', W.UINT),
                ('stateMask', W.UINT), ('pszText', ctypes.c_void_p), ('cchTextMax', ctypes.c_int),
                ('iImage', ctypes.c_int), ('lParam', ctypes.c_ssize_t), ('iIndent', ctypes.c_int),
                ('iGroupId', ctypes.c_int), ('cColumns', W.UINT), ('puColumns', ctypes.c_void_p),
                ('piColFmt', ctypes.c_void_p), ('iGroup', ctypes.c_int)]


class TVITEMW(ctypes.Structure):
    _fields_ = [('mask', W.UINT), ('hItem', ctypes.c_void_p), ('state', W.UINT), ('stateMask', W.UINT),
                ('pszText', ctypes.c_void_p), ('cchTextMax', ctypes.c_int), ('iImage', ctypes.c_int),
                ('iSelectedImage', ctypes.c_int), ('cChildren', ctypes.c_int), ('lParam', ctypes.c_ssize_t)]


TVM_GETNEXTITEM, TVM_SELECTITEM, TVM_GETITEMW = 0x110A, 0x110B, 0x113E
TVGN_ROOT, TVGN_NEXT, TVGN_CHILD, TVGN_CARET = 0x0, 0x1, 0x4, 0x9


class Remote:
    """A scratch block of memory inside another process, plus the list-view/status-bar calls that need it."""

    SIZE = 65536

    def __init__(self, pid: int):
        self.process = kernel32.OpenProcess(PROCESS_VM, False, pid)
        if not self.process:
            raise OSError(f'cannot open process {pid}')
        self.mem = kernel32.VirtualAllocEx(self.process, None, self.SIZE, 0x3000, 0x04)  # COMMIT|RESERVE, RW

    def close(self):
        if self.process:
            kernel32.VirtualFreeEx(self.process, self.mem, 0, 0x8000)  # MEM_RELEASE
            kernel32.CloseHandle(self.process)
            self.process = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, offset: int, obj) -> None:
        kernel32.WriteProcessMemory(self.process, self.mem + offset, ctypes.byref(obj), ctypes.sizeof(obj), None)

    def read(self, offset: int, obj):
        kernel32.ReadProcessMemory(self.process, self.mem + offset, ctypes.byref(obj), ctypes.sizeof(obj), None)
        return obj

    def _text(self, n_chars: int) -> str:
        buf = ctypes.create_unicode_buffer(n_chars)
        return self.read(TEXT_AT, buf).value

    # --- list views
    def lv_count(self, lv: int) -> int:
        return send(lv, LVM_GETITEMCOUNT, 0, 0)

    def lv_text(self, lv: int, item: int, column: int = 0) -> str:
        self.write(0, LVITEM(iItem=item, iSubItem=column, cchTextMax=1024, pszText=self.mem + TEXT_AT))
        send(lv, LVM_GETITEMTEXTW, item, self.mem)
        return self._text(1024)

    def lv_column(self, lv: int, column: int = 0) -> list[str]:
        return [self.lv_text(lv, i, column) for i in range(self.lv_count(lv))]

    def lv_image(self, lv: int, item: int) -> int:
        """The row's image index (the CK's Data dialog draws its tick boxes as images: 1 = ticked)."""
        self.write(0, LVITEM(mask=0x2, iItem=item))  # LVIF_IMAGE
        send(lv, LVM_GETITEMW, 0, self.mem)
        return self.read(0, LVITEM()).iImage

    def lv_rect(self, lv: int, item: int) -> W.RECT:
        self.write(0, W.RECT(0, 0, 0, 0))  # left = LVIR_BOUNDS
        send(lv, LVM_GETITEMRECT, item, self.mem)
        return self.read(0, W.RECT())

    def lv_ensure_visible(self, lv: int, item: int) -> None:
        send(lv, LVM_ENSUREVISIBLE, item, 0)

    def lv_select(self, lv: int, item: int) -> None:
        self.write(0, LVITEM(stateMask=0x3, state=0x3))  # LVIS_SELECTED | LVIS_FOCUSED
        send(lv, LVM_SETITEMSTATE, item, self.mem)

    # --- tree views
    def tv_text(self, tv: int, item: int) -> str:
        self.write(0, TVITEMW(mask=0x1, hItem=item, pszText=self.mem + TEXT_AT, cchTextMax=512))  # TVIF_TEXT
        send(tv, TVM_GETITEMW, 0, self.mem)
        return self._text(512)

    def tv_items(self, tv: int, parent: int | None = None) -> list[tuple[int, str]]:
        """(handle, text) of the top-level items, or of parent's children."""
        item = send(tv, TVM_GETNEXTITEM, TVGN_CHILD, parent) if parent else send(tv, TVM_GETNEXTITEM, TVGN_ROOT, 0)
        out = []
        while item:
            out.append((item, self.tv_text(tv, item)))
            item = send(tv, TVM_GETNEXTITEM, TVGN_NEXT, item)
        return out

    def tv_select(self, tv: int, item: int) -> None:
        send(tv, TVM_SELECTITEM, TVGN_CARET, item)

    # --- status bars
    def status_parts(self, sb: int) -> list[str]:
        out = []
        for i in range(send(sb, SB_GETPARTS, 0, 0)):
            n = send(sb, SB_GETTEXTLENGTHW, i, 0) & 0xFFFF
            send(sb, SB_GETTEXTW, i, self.mem + TEXT_AT)
            out.append(self._text(n + 1))
        return out
