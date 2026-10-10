"""Read files out of Fallout 4 BA2 archives: General (GNRL) archives and texture (DX10) archives.

DX10 entries are rebuilt into standalone .dds files with a DX10 header.
"""
import struct, zlib, os, fnmatch, glob

BS = chr(92)


def extract_general(archive, patterns, outdir):
    got = []
    with open(archive, 'rb') as f:
        magic, ver, typ, n, nto = struct.unpack('<4sI4sIQ', f.read(24))
        assert typ == b'GNRL', typ
        recs = [struct.unpack('<I4sIIQIII', f.read(36)) for _ in range(n)]
        f.seek(nto)
        names = []
        for _ in range(n):
            l = struct.unpack('<H', f.read(2))[0]
            names.append(f.read(l).decode('latin1'))
        for (h, ext, dh, fl, off, packed, size, al), name in zip(recs, names):
            if any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns):
                f.seek(off)
                d = f.read(packed or size)
                d = zlib.decompress(d) if packed else d
                out = os.path.join(outdir, *name.split(BS))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                open(out, 'wb').write(d)
                got.append(name)
    return got

# DXGI formats used by Fallout 4 texture archives -> (bytes per block or pixel, block-compressed)
DXGI = {28: (4, False), 87: (4, False), 61: (1, False), 71: (8, True), 74: (16, True), 77: (16, True),
        80: (8, True), 83: (16, True), 98: (16, True), 72: (8, True), 75: (16, True), 78: (16, True)}


def dds_header(w, h, mips, fmt, cube):
    bpp, bc = DXGI.get(fmt, (4, False))
    pitch = max(1, (w + 3) // 4) * bpp if bc else w * bpp
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | (0x80000 if bc else 0x8)
    caps = 0x1000 | 0x8 | 0x400000
    caps2 = 0xFE00 if cube else 0
    hdr = struct.pack('<4sIIIIIII11I', b'DDS ', 124, flags, h, w, pitch, 0, mips, *([0] * 11))
    pf = struct.pack('<II4sIIIII', 32, 0x4, b'DX10', 0, 0, 0, 0, 0)
    hdr += pf + struct.pack('<IIIII', caps, caps2, 0, 0, 0)
    dx10 = struct.pack('<IIIII', fmt, 3, 0x4 if cube else 0, 1, 0)
    return hdr + dx10


def extract_textures(archive, patterns, outdir):
    got = []
    with open(archive, 'rb') as f:
        magic, ver, typ, n, nto = struct.unpack('<4sI4sIQ', f.read(24))
        if typ != b'DX10':
            return got
        entries = []
        for _ in range(n):
            h, ext, dh, unk, nch, chs, ht, wd, mips, fmt, cube, tile = struct.unpack('<I4sIBBHHHBBBB', f.read(24))
            chunks = [struct.unpack('<QIIHHI', f.read(24)) for _ in range(nch)]
            entries.append((ht, wd, mips, fmt, cube, chunks))
        f.seek(nto)
        names = []
        for _ in range(n):
            l = struct.unpack('<H', f.read(2))[0]
            names.append(f.read(l).decode('latin1'))
        for (ht, wd, mips, fmt, cube, chunks), name in zip(entries, names):
            if not any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns):
                continue
            data = b''
            for off, packed, size, smip, emip, al in chunks:
                f.seek(off)
                d = f.read(packed or size)
                data += zlib.decompress(d) if packed else d
            out = os.path.join(outdir, *name.split(BS))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'wb').write(dds_header(wd, ht, mips, fmt, cube) + data)
            got.append((name, wd, ht, mips, fmt))
    return got


def extract_all(data_dir, patterns, outdir, prefix='Fallout4 - Textures'):
    got = []
    for a in sorted(glob.glob(os.path.join(data_dir, prefix + '*.ba2'))):
        got += extract_textures(a, patterns, outdir)
    return got
