"""Game profiles and the Creation Kit session rules (no game or Creation Kit needed)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ack import config, games
from ack.ck import lifecycle


class GamesTest(unittest.TestCase):
    def test_light_range_by_header_version(self):
        fo4, sse = games.GAMES['fo4'], games.GAMES['sse']
        self.assertEqual(fo4.light_range(1.0), (0x001, 0xFFF))
        self.assertEqual(fo4.light_range(0.95), (0x800, 0xFFF))
        self.assertEqual(sse.light_range(1.70), (0x800, 0xFFF))
        self.assertEqual(sse.light_range(1.71), (0x001, 0xFFF))

    def test_unknown_game(self):
        with self.assertRaises(SystemExit):
            games.get('morrowind')

    def test_masters_start_with_the_base_game(self):
        for g in games.GAMES.values():
            self.assertTrue(g.masters[0].lower().endswith('.esm'), g.key)


class SaveBlockerTest(unittest.TestCase):
    """xEdit runs that save must not start while a Creation Kit could save over their plugin."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cfg = config.Config(Path('C:/Game'), Path('C:/xEdit/FO4Edit.exe'), Path(self.dir.name))

    def tearDown(self):
        self.dir.cleanup()

    def blocker(self, pids, state, plugins=('MyMod.esp',)):
        with mock.patch.object(lifecycle, 'running', return_value=pids), \
                mock.patch.object(lifecycle, 'read_state', return_value=state):
            return lifecycle.save_blocker(list(plugins), self.cfg)

    def test_no_creation_kit(self):
        self.assertIsNone(self.blocker([], None))

    def test_unknown_creation_kit_blocks(self):
        self.assertIn('did not start it', self.blocker([42], None))

    def test_our_creation_kit_with_the_plugin_active_blocks(self):
        state = lifecycle.SessionState(42, plugins=['MyMod.esp'], active='MyMod.esp')
        self.assertIn('MyMod.esp as its active file', self.blocker([42], state))

    def test_our_creation_kit_with_another_or_no_active_file_is_fine(self):
        self.assertIsNone(self.blocker([42], lifecycle.SessionState(42, plugins=['Other.esp'], active='Other.esp')))
        self.assertIsNone(self.blocker([42], lifecycle.SessionState(42, plugins=['MyMod.esp'], active=None)))

    def test_a_second_creation_kit_blocks(self):
        state = lifecycle.SessionState(42, plugins=['Other.esp'], active='Other.esp')
        self.assertIsNotNone(self.blocker([42, 43], state))

    def test_state_round_trip(self):
        state = lifecycle.SessionState(12345, plugins=['A.esp'], active='A.esp')
        lifecycle.write_state(state, self.cfg)
        with mock.patch.object(lifecycle.win32, 'process_alive', return_value=True):
            self.assertEqual(lifecycle.read_state(self.cfg), state)
        with mock.patch.object(lifecycle.win32, 'process_alive', return_value=False):
            self.assertIsNone(lifecycle.read_state(self.cfg))  # that CK is gone: the record is stale
        lifecycle.clear_state(self.cfg)
        self.assertIsNone(lifecycle.read_state(self.cfg))


if __name__ == '__main__':
    unittest.main()
