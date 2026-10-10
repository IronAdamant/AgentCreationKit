"""Lossless reader/writer for Bethesda plugin files (Fallout 4 / Skyrim SE record format).

Design rule: anything not edited is written back byte-for-byte as it was read, including compressed
record payloads and unknown header fields. A record is only rebuilt when its subrecords were changed.

File structure:
    TES4 header record, then top-level GRUPs; GRUPs nest; records hold subrecords.
    Record header (24 bytes): sig, data size, flags, FormID, version control 1, form version, version control 2
    GRUP header (24 bytes):   'GRUP', total size incl. header, label, group type, stamp, unknown, version, unknown
    Subrecord: sig, uint16 size, data. A preceding XXXX subrecord carries a uint32 size for >65535-byte data.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Union

FLAG_COMPRESSED = 0x00040000
FLAG_DELETED = 0x00000020
FLAG_ESM = 0x00000001
FLAG_LOCALIZED = 0x00000080
FLAG_ESL = 0x00000200

_REC = struct.Struct('<4sIIIIHH')
_GRP = struct.Struct('<4sI4si8s')


@dataclass
class Subrecord:
    sig: str
    data: bytes

    def to_bytes(self) -> bytes:
        s = self.sig.encode('latin1')
        if len(self.data) > 0xFFFF:
            return b'XXXX' + struct.pack('<HI', 4, len(self.data)) + s + struct.pack('<H', 0) + self.data
        return s + struct.pack('<H', len(self.data)) + self.data

    @property
    def zstring(self) -> str:
        return self.data.rstrip(b'\0').decode('cp1252', errors='replace')


def parse_subrecords(data: bytes) -> list[Subrecord]:
    out, i, big = [], 0, None
    while i < len(data):
        sig = data[i:i + 4].decode('latin1')
        size, = struct.unpack_from('<H', data, i + 4)
        i += 6
        if sig == 'XXXX':
            big, = struct.unpack_from('<I', data, i)
            i += size
            continue
        if big is not None:
            size, big = big, None
        out.append(Subrecord(sig, data[i:i + size]))
        i += size
    return out


class Record:
    def __init__(self, sig: str, flags: int, formid: int, vc1: int, version: int, vc2: int, raw: bytes):
        self.sig, self.flags, self.formid = sig, flags, formid
        self.vc1, self.version, self.vc2 = vc1, version, vc2
        self._raw = raw                      # payload exactly as stored (compressed if flagged)
        self._subs: list[Subrecord] | None = None
        self._dirty = False

    # --- payload ---------------------------------------------------------
    @property
    def compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)

    def data(self) -> bytes:
        """Uncompressed subrecord bytes."""
        if self._subs is not None and self._dirty:
            return b''.join(s.to_bytes() for s in self._subs)
        if self.compressed:
            return zlib.decompress(self._raw[4:])
        return self._raw

    @property
    def subrecords(self) -> list[Subrecord]:
        """Parsed subrecords. Mutating this list or its items requires calling mark_dirty()."""
        if self._subs is None:
            self._subs = parse_subrecords(self.data())
        return self._subs

    def mark_dirty(self) -> None:
        self.subrecords  # ensure parsed
        self._dirty = True

    def get(self, sig: str) -> Subrecord | None:
        return next((s for s in self.subrecords if s.sig == sig), None)

    def set(self, sig: str, data: bytes) -> None:
        """Replace the first subrecord with this signature, or append it."""
        sub = self.get(sig)
        if sub:
            sub.data = data
        else:
            self.subrecords.append(Subrecord(sig, data))
        self.mark_dirty()

    @property
    def edid(self) -> str:
        s = self.get('EDID')
        return s.zstring if s else ''

    # --- serialisation ---------------------------------------------------
    def payload(self) -> bytes:
        if not self._dirty:
            return self._raw
        data = self.data()
        if self.compressed:
            return struct.pack('<I', len(data)) + zlib.compress(data)
        return data

    def to_bytes(self) -> bytes:
        p = self.payload()
        return _REC.pack(self.sig.encode('latin1'), len(p), self.flags, self.formid,
                         self.vc1, self.version, self.vc2) + p

    def copy(self) -> 'Record':
        r = Record(self.sig, self.flags, self.formid, self.vc1, self.version, self.vc2, self.payload())
        return r

    def __repr__(self):
        return f'<{self.sig} {self.formid:08X} {self.edid!r}>'


class Group:
    def __init__(self, label: bytes, gtype: int, tail: bytes, children: list['Node']):
        self.label, self.gtype, self.tail, self.children = label, gtype, tail, children

    @property
    def label_sig(self) -> str:
        return self.label.decode('latin1')

    def to_bytes(self) -> bytes:
        body = b''.join(c.to_bytes() for c in self.children)
        return _GRP.pack(b'GRUP', 24 + len(body), self.label, self.gtype, self.tail) + body

    def __repr__(self):
        return f'<GRUP type={self.gtype} label={self.label!r} children={len(self.children)}>'


Node = Union[Record, Group]


def _parse_nodes(buf: bytes, start: int, end: int) -> list[Node]:
    out: list[Node] = []
    i = start
    while i < end:
        sig = buf[i:i + 4]
        if sig == b'GRUP':
            _, size, label, gtype, tail = _GRP.unpack_from(buf, i)
            out.append(Group(label, gtype, tail, _parse_nodes(buf, i + 24, i + size)))
            i += size
        else:
            s, size, flags, fid, vc1, ver, vc2 = _REC.unpack_from(buf, i)
            out.append(Record(s.decode('latin1'), flags, fid, vc1, ver, vc2, buf[i + 24:i + 24 + size]))
            i += 24 + size
    if i != end:
        raise ValueError(f'structure overrun at {i} (expected {end})')
    return out


class Plugin:
    def __init__(self, header: Record, groups: list[Group], name: str = ''):
        self.header, self.groups, self.name = header, groups, name

    @classmethod
    def load(cls, path: str | Path) -> 'Plugin':
        path = Path(path)
        buf = path.read_bytes()
        nodes = _parse_nodes(buf, 0, len(buf))
        header = nodes[0]
        if not isinstance(header, Record) or header.sig != 'TES4':
            raise ValueError(f'{path.name}: not a plugin (no TES4 header)')
        groups = nodes[1:]
        if not all(isinstance(g, Group) for g in groups):
            raise ValueError(f'{path.name}: unexpected top-level record')
        return cls(header, groups, path.name)

    def to_bytes(self) -> bytes:
        return self.header.to_bytes() + b''.join(g.to_bytes() for g in self.groups)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # --- header info -----------------------------------------------------
    @property
    def masters(self) -> list[str]:
        return [s.zstring for s in self.header.subrecords if s.sig == 'MAST']

    @property
    def is_localized(self) -> bool:
        return bool(self.header.flags & FLAG_LOCALIZED)

    def owner_of(self, formid: int) -> str:
        """File a FormID belongs to, from this plugin's point of view (master index in the top byte)."""
        idx = formid >> 24
        m = self.masters
        return m[idx] if idx < len(m) else self.name

    def is_own(self, formid: int) -> bool:
        return (formid >> 24) >= len(self.masters)

    # --- traversal -------------------------------------------------------
    def records(self, sig: str | None = None) -> Iterator[Record]:
        def walk(nodes):
            for n in nodes:
                if isinstance(n, Group):
                    yield from walk(n.children)
                elif sig is None or n.sig == sig:
                    yield n
        yield from walk(self.groups)

    def top_group(self, sig: str) -> Group | None:
        return next((g for g in self.groups if g.gtype == 0 and g.label_sig == sig), None)

    def by_edid(self, edid: str) -> Record | None:
        return next((r for r in self.records() if r.edid == edid), None)

    def by_formid(self, formid: int) -> Record | None:
        return next((r for r in self.records() if r.formid == formid), None)
