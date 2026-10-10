"""Parts of ack.ck that work without a running Creation Kit."""
import struct
import unittest
import zlib

from ack.__main__ import _axes
from ack.ck.capture import png_bytes


class PngTest(unittest.TestCase):
    def test_encodes_bgra_as_rgb_rows(self):
        # 2x2 image, top-down BGRA: red, green / blue, white
        bgra = bytes([0, 0, 255, 255, 0, 255, 0, 255, 255, 0, 0, 255, 255, 255, 255, 255])
        png = png_bytes(2, 2, bgra)
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        width, height, depth, colour = struct.unpack('>IIBB', png[16:26])
        self.assertEqual((width, height, depth, colour), (2, 2, 8, 2))
        idat_len = struct.unpack('>I', png[33:37])[0]
        self.assertEqual(png[37:41], b'IDAT')
        rows = zlib.decompress(png[41:41 + idat_len])
        self.assertEqual(rows, b'\x00' + bytes([255, 0, 0, 0, 255, 0]) + b'\x00' + bytes([0, 0, 255, 255, 255, 255]))
        self.assertTrue(png.endswith(b'IEND\xaeB`\x82'))


class AxesTest(unittest.TestCase):
    def test_underscore_keeps_an_axis(self):
        self.assertEqual(_axes(['10', '_', '-2.5']), (10.0, None, -2.5))
        self.assertIsNone(_axes(None))


if __name__ == '__main__':
    unittest.main()
