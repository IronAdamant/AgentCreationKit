"""ack.plugin.check on small plugins built in memory (no game files needed)."""
import struct
import tempfile
import unittest
from pathlib import Path

from ack import games
from ack.plugin.check import NAVM_UNINDEXED, check
from ack.plugin.records import FLAG_ESL, Group, Plugin, Record, Subrecord

FO4 = games.GAMES['fo4']


def record(sig, formid, subs, flags=0):
    return Record(sig, flags, formid, 0, 131, 0, b''.join(s.to_bytes() for s in subs))


def group(sig, records):
    return Group(sig.encode('latin1'), 0, bytes(8), records)


def make(masters, records, esl=True, next_id=0x801, hedr_version=1.0):
    subs = [Subrecord('HEDR', struct.pack('<fII', hedr_version, len(records), next_id))]
    for m in masters:
        subs += [Subrecord('MAST', m.encode() + b'\0'), Subrecord('DATA', bytes(8))]
    header = record('TES4', 0, subs, FLAG_ESL if esl else 0)
    by_sig = {}
    for r in records:
        by_sig.setdefault(r.sig, []).append(r)
    return Plugin(header, [group(sig, rs) for sig, rs in by_sig.items()], 'Test.esp')


def navi(*navmesh_ids):
    return record('NAVI', 0x00000FF1, [Subrecord('NVER', b'\x0c\0\0\0')] +
                  [Subrecord('NVMI', struct.pack('<I', fid) + bytes(12)) for fid in navmesh_ids])


class CheckTest(unittest.TestCase):
    def run_check(self, plugin, **kw):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / plugin.name
            plugin.save(path)
            return check(path, FO4, **kw)

    def errors(self, report):
        return [f.text for f in report.findings if f.level == 'error']

    def test_clean_light_plugin_with_navmesh(self):
        p = make(['Fallout4.esm'], [record('NAVM', 0x01000801, []), navi(0x01000801, 0x0001F00D)])
        self.assertEqual(self.errors(self.run_check(p)), [])

    def test_navmesh_index_left_on_the_old_file_index(self):
        # the Sandbox Room crash: a master was added, the plugin's own index moved from 01 to 02, the NAVI did not
        p = make(['Fallout4.esm', 'DLCRobot.esm'], [record('NAVM', 0x02000801, []), navi(0x01000801)])
        errors = self.errors(self.run_check(p))
        self.assertTrue(any('no navmesh index entry: 02000801' in e for e in errors), errors)

    def test_index_entry_for_a_file_that_does_not_exist(self):
        p = make(['Fallout4.esm'], [record('NAVM', 0x01000801, []), navi(0x01000801, 0x05000900)])
        self.assertTrue(any('no such file' in e for e in self.errors(self.run_check(p))))

    def test_unindexed_navmesh_flag_needs_no_entry(self):
        p = make(['Fallout4.esm'], [record('NAVM', 0x01000801, [], NAVM_UNINDEXED), navi()])
        self.assertEqual(self.errors(self.run_check(p)), [])

    def test_new_navmesh_without_any_index(self):
        p = make(['Fallout4.esm'], [record('NAVM', 0x01000801, [])])
        self.assertTrue(any('no navmesh index (NAVI)' in e for e in self.errors(self.run_check(p))))

    def test_master_added_since_before(self):
        p = make(['Fallout4.esm', 'DLCCoast.esm'], [])
        errors = self.errors(self.run_check(p, masters_before=['Fallout4.esm']))
        self.assertTrue(any('masters added since before: DLCCoast.esm' in e for e in errors), errors)

    def test_expected_masters(self):
        p = make(['Fallout4.esm'], [])
        self.assertEqual(self.errors(self.run_check(p, expected_masters=['Fallout4.esm'])), [])
        self.assertTrue(self.errors(self.run_check(p, expected_masters=['Fallout4.esm', 'DLCRobot.esm'])))

    def test_light_range(self):
        p = make(['Fallout4.esm'], [record('GLOB', 0x01001010, []), record('GLOB', 0x01000FFF, [])])
        errors = self.errors(self.run_check(p))
        self.assertTrue(any('1 record(s) outside the light range: GLOB 1010' in e for e in errors), errors)
        # before HEDR 1.0 a Fallout 4 light plugin starts at 0x800
        low = make(['Fallout4.esm'], [record('GLOB', 0x01000500, [])], hedr_version=0.95)
        self.assertTrue(self.errors(self.run_check(low)))
        self.assertEqual(self.errors(self.run_check(make(['Fallout4.esm'], [record('GLOB', 0x01000500, [])]))), [])

    def test_regular_plugin_has_no_light_range(self):
        p = make(['Fallout4.esm'], [record('GLOB', 0x01123456, [])], esl=False)
        self.assertEqual(self.errors(self.run_check(p)), [])

    def test_next_object_id_past_the_range_is_a_warning(self):
        report = self.run_check(make(['Fallout4.esm'], [], next_id=0x1732))
        self.assertTrue(report.ok)
        self.assertTrue(any(f.level == 'warning' and '1732' in f.text for f in report.findings))

    def test_unreadable_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'Broken.esp'
            path.write_bytes(b'not a plugin')
            self.assertFalse(check(path, FO4).ok)


if __name__ == '__main__':
    unittest.main()
