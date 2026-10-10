"""Minimal Fallout 4 NIF (20.2.0.7, BS version 130+) header reader and string patcher.

Only parses what is needed to locate blocks and rewrite length-prefixed strings inside a block
(e.g. texture paths in BSEffectShaderProperty), fixing up the block-size table.
"""
import struct


class Nif:
    def __init__(self, data):
        self.data = bytearray(data)
        d = self.data
        nl = d.index(b'\n')
        self.header_line = bytes(d[:nl + 1])
        p = nl + 1
        self.version, = struct.unpack_from('<I', d, p); p += 4
        assert self.version == 0x14020007, hex(self.version)
        p += 1  # endian
        self.user_version, = struct.unpack_from('<I', d, p); p += 4
        self.num_blocks, = struct.unpack_from('<I', d, p); p += 4
        self.bs_version, = struct.unpack_from('<I', d, p); p += 4
        for _ in range(3):  # author, process script, export script
            l = d[p]; p += 1 + l
        if self.bs_version >= 130:
            l = d[p]; p += 1 + l  # max filepath
        nt, = struct.unpack_from('<H', d, p); p += 2
        self.block_types = []
        for _ in range(nt):
            l, = struct.unpack_from('<I', d, p); p += 4
            self.block_types.append(bytes(d[p:p + l]).decode('latin1')); p += l
        self.type_index = list(struct.unpack_from('<%dH' % self.num_blocks, d, p)); p += 2 * self.num_blocks
        self.sizes_offset = p
        self.sizes = list(struct.unpack_from('<%dI' % self.num_blocks, d, p)); p += 4 * self.num_blocks
        ns, self.max_str = struct.unpack_from('<II', d, p); p += 8
        self.strings = []
        for _ in range(ns):
            l, = struct.unpack_from('<I', d, p); p += 4
            self.strings.append(bytes(d[p:p + l]).decode('latin1')); p += l
        ng, = struct.unpack_from('<I', d, p); p += 4 + 4 * ng
        self.blocks_offset = p

    def block_ranges(self):
        p = self.blocks_offset
        for i, s in enumerate(self.sizes):
            yield i, self.block_types[self.type_index[i] & 0x7FFF], p, p + s
            p += s

    def replace_sized_string(self, old, new):
        """Replace every length-prefixed (uint32) occurrence of `old` inside blocks. Returns count.

        Matching ignores case: game paths are case-insensitive and vanilla models mix
        'textures\\Effects\\...' with 'textures\\effects\\...'.
        """
        old_b, new_b = old.encode('latin1'), new.encode('latin1')
        old_l = old_b.lower()
        count = 0
        for i, typ, start, end in reversed(list(self.block_ranges())):
            block = bytes(self.data[start:end])
            block_l = block.lower()
            j = 0
            pieces, last = [], 0
            while True:
                k = block_l.find(old_l, j)
                if k < 0:
                    break
                if k >= 4 and struct.unpack_from('<I', block, k - 4)[0] == len(old_b):
                    pieces.append(block[last:k - 4] + struct.pack('<I', len(new_b)) + new_b)
                    last = k + len(old_b)
                    count += 1
                j = k + 1
            if pieces:
                new_block = b''.join(pieces) + block[last:]
                self.data[start:end] = new_block
                self.sizes[i] = len(new_block)
                struct.pack_into('<I', self.data, self.sizes_offset + 4 * i, len(new_block))
        return count

    def sized_strings(self):
        """All length-prefixed printable strings found inside blocks (for inspection)."""
        out = []
        for i, typ, start, end in self.block_ranges():
            b = bytes(self.data[start:end])
            for k in range(len(b) - 4):
                l = struct.unpack_from('<I', b, k)[0]
                if 4 <= l < 260 and k + 4 + l <= len(b):
                    s = b[k + 4:k + 4 + l]
                    if all(32 <= c < 127 for c in s) and b'.' in s:
                        out.append((i, typ, s.decode('latin1')))
        return out


def parse_effect_shader(b):
    """Decode the start of a FO4 BSEffectShaderProperty block (bsver 130)."""
    p = 0
    name, nextra = struct.unpack_from('<iI', b, p); p += 8 + 4 * nextra
    ctrl, f1, f2 = struct.unpack_from('<iII', b, p); p += 12
    uvo = struct.unpack_from('<2f', b, p); p += 8
    uvs = struct.unpack_from('<2f', b, p); p += 8
    l, = struct.unpack_from('<I', b, p); p += 4; src = b[p:p + l].decode('latin1'); p += l
    clamp, lightinf, envlod, unused = struct.unpack_from('<4B', b, p); p += 4
    fall = struct.unpack_from('<4f', b, p); p += 16
    color_off = p
    color = struct.unpack_from('<4f', b, p); p += 16
    scale, = struct.unpack_from('<f', b, p); p += 4
    soft, = struct.unpack_from('<f', b, p); p += 4
    l, = struct.unpack_from('<I', b, p); p += 4; grey = b[p:p + l].decode('latin1'); p += l
    return dict(flags=(hex(f1), hex(f2)), src=src, falloff=fall, base_color=color, color_offset=color_off,
                color_scale=scale, soft_depth=soft, greyscale=grey)
