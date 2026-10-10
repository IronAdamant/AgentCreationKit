"""Plugin reader/writer: unmodified files round-trip byte-for-byte; edits touch only the edited record."""
import os
import tempfile
import unittest
from pathlib import Path

from ack.plugin import Plugin

DATA = Path(os.environ.get('ACK_GAME_DATA', 'D:/Steam/steamapps/common/Fallout 4/Data'))
SAMPLES = ['Custom Legendary Modifications Remade.esp', 'DLCRobot.esm', 'DLCCoast.esm']


def available():
    return [n for n in SAMPLES if (DATA / n).exists()]


class RoundTrip(unittest.TestCase):
    def test_unmodified_roundtrip_is_identical(self):
        names = available()
        if not names:
            self.skipTest(f'no sample plugins in {DATA}')
        for name in names:
            with self.subTest(plugin=name):
                raw = (DATA / name).read_bytes()
                self.assertEqual(Plugin.load(DATA / name).to_bytes(), raw)

    def test_edit_changes_only_that_record(self):
        names = available()
        if not names:
            self.skipTest(f'no sample plugins in {DATA}')
        plugin = Plugin.load(DATA / names[0])
        target = next(plugin.records('GLOB'))
        untouched = {r.formid: r.to_bytes() for r in plugin.records() if r is not target}

        target.set('EDID', b'ACK_TestRename\0')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'edited.esp'
            plugin.save(path)
            again = Plugin.load(path)

        self.assertEqual(again.by_formid(target.formid).edid, 'ACK_TestRename')
        for r in again.records():
            if r.formid != target.formid:
                self.assertEqual(r.to_bytes(), untouched[r.formid], r)


if __name__ == '__main__':
    unittest.main()
