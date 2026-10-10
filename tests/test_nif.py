"""NIF string patching: paths are matched case-insensitively and the block table stays valid."""
import os
import tempfile
import unittest
from pathlib import Path

from ack.archive import extract_general
from ack.nif import Nif

MESHES = Path(os.environ.get('ACK_GAME_DATA', 'D:/Steam/steamapps/common/Fallout 4/Data')) / 'Fallout4 - Meshes.ba2'
BS = chr(92)


class Patch(unittest.TestCase):
    def test_case_insensitive_replace_keeps_structure(self):
        if not MESHES.exists():
            self.skipTest('game meshes archive not found')
        with tempfile.TemporaryDirectory() as d:
            got = extract_general(MESHES, ['meshes' + BS + 'effects' + BS + 'muzlaserrifle01.nif'], d)
            nif = Nif((Path(d) / 'Meshes' / 'Effects' / 'MuzLaserRifle01.nif').read_bytes())
        # The model stores 'textures\effects\gradients\...' (lower case); search with different casing.
        old = BS.join(['textures', 'Effects', 'Gradients', 'WepLaserRed01Grad.dds'])
        new = BS.join(['textures', 'Effects', 'Gradients', 'Test', 'NewGrad.dds'])
        self.assertGreater(nif.replace_sized_string(old, new), 0)
        out = bytes(nif.data)
        again = Nif(out)
        self.assertEqual(again.blocks_offset + sum(again.sizes) + 8, len(out))
        paths = {p.lower() for _, _, p in again.sized_strings()}
        self.assertIn(new.lower(), paths)
        self.assertNotIn(old.lower(), paths)


if __name__ == '__main__':
    unittest.main()
