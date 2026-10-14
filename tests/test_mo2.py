"""Mod Organizer 2: reading an instance, resolving files the way MO2 does, and the command that runs a tool in it.
Uses a made-up instance in a temporary folder."""
import struct
import tempfile
import unittest
from pathlib import Path

from ack import config, doctor, mo2
from ack.archive import pack


class Mo2Instance(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        self.game = root / 'Fallout 4'
        self.base = root / 'MO2 Files'
        self.inst = root / 'instance'
        for d in (self.game / 'Data', self.base / 'overwrite', self.inst):
            d.mkdir(parents=True)
        ini = (f'[General]\ngameName=Fallout 4\ngamePath=@ByteArray({self.game})\n'
               f'selected_profile=@ByteArray(Default)\n\n[Settings]\nbase_directory={self.base}\n'
               f'profile_local_inis=true\n').replace('\\', '\\\\')
        (self.inst / 'ModOrganizer.ini').write_text(ini, encoding='utf8')
        profile = self.base / 'profiles' / 'Default'
        profile.mkdir(parents=True)
        # modlist.txt lists the highest priority first
        (profile / 'modlist.txt').write_text('# generated\n+High\n-Disabled\n+Tools_separator\n+Low\n*DLC: Automatron\n',
                                             encoding='utf8')
        (profile / 'plugins.txt').write_text('# comment\n*Low.esp\nInactive.esp\n*High.esp\n', encoding='utf8')
        for mod, files in {'High': ['Shared.esp', 'High.esp'], 'Low': ['Shared.esp', 'Low.esp', 'Over.esp'],
                           'Disabled': ['Off.esp']}.items():
            for f in files:
                p = self.base / 'mods' / mod / f
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(mod, encoding='utf8')
        (self.base / 'overwrite' / 'Over.esp').write_text('overwrite', encoding='utf8')
        (self.game / 'Data' / 'Fallout4.esm').write_text('data', encoding='utf8')
        self.m = mo2.load({'exe': str(root / 'MO2' / 'ModOrganizer.exe'), 'instance': str(self.inst)})

    def tearDown(self):
        self.dir.cleanup()

    def test_reads_the_instance(self):
        m = self.m
        self.assertEqual((m.game_dir, m.base_dir, m.profile), (self.game, self.base, 'Default'))
        self.assertEqual(m.mods_dir, self.base / 'mods')
        self.assertTrue(m.local_inis)
        self.assertEqual(m.enabled_mods(), ['High', 'Low'])
        self.assertEqual(m.plugins(), ['Low.esp', 'High.esp'])

    def test_resolves_like_mo2(self):
        m = self.m
        self.assertEqual(m.origin('Shared.esp')[0], 'High')          # the higher priority mod wins
        self.assertEqual(m.origin('Over.esp')[0], 'overwrite')       # overwrite beats every mod
        self.assertEqual(m.origin('Fallout4.esm')[0], 'Data')        # then the real Data folder
        self.assertIsNone(m.origin('Off.esp'))                       # disabled mods are not there
        self.assertEqual(m.resolve('New.esp'), self.base / 'overwrite' / 'New.esp')

    def test_config_uses_it(self):
        cfg = config.Config(self.game, Path('C:/xEdit/FO4Edit.exe'), Path(self.dir.name) / 'runs', mo2=self.m)
        self.assertEqual(cfg.data_path('Low.esp'), self.base / 'mods' / 'Low' / 'Low.esp')
        self.assertEqual(cfg.write_targets('Low.esp'),
                         [self.base / 'mods' / 'Low' / 'Low.esp', self.base / 'overwrite' / 'Low.esp'])
        self.assertEqual(cfg.custom_ini, self.base / 'profiles' / 'Default' / 'Fallout4Custom.ini')
        plain = config.Config(self.game, Path('C:/xEdit/FO4Edit.exe'), Path(self.dir.name) / 'runs')
        self.assertEqual(plain.data_path('Low.esp'), self.game / 'Data' / 'Low.esp')
        self.assertEqual(plain.command(Path('C:/x.exe'), ['-a']), ['C:\\x.exe', '-a'])

    def test_run_command(self):
        m = mo2.load({'exe': 'D:/MO2/ModOrganizer.exe', 'instance': str(self.inst), 'profile': 'Test'})
        cmd = m.run_command(Path('D:/xEdit/FO4Edit.exe'), ['-autoload', '-P:C:/a b/plugins.txt'], Path('D:/xEdit'))
        # an instance given as a path has no name to pass with -i
        self.assertEqual(cmd, ['D:\\MO2\\ModOrganizer.exe', '-p', 'Test', 'run', '-a',
                               '-autoload "-P:C:/a b/plugins.txt"', '-c', 'D:\\xEdit', 'D:\\xEdit\\FO4Edit.exe'])

    def test_qt_ini_values(self):
        ini = Path(self.dir.name) / 'q.ini'
        ini.write_text('[A]\nx=@ByteArray(C:\\\\Games\\\\FO4)\ny="quoted value"\n1\\binary=D:/a.exe\n', encoding='utf8')
        self.assertEqual(mo2.read_ini(ini)['A'], {'x': 'C:\\Games\\FO4', 'y': 'quoted value', '1\\binary': 'D:/a.exe'})


class Ba2Header(unittest.TestCase):
    def test_stamp_and_info(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'a.ba2'
            name = b'Scripts\\X.pex'
            names_at = 24 + 36
            path.write_bytes(struct.pack('<4sI4sIQ', b'BTDX', 8, b'GNRL', 1, names_at) + bytes(36) +
                             struct.pack('<H', len(name)) + name)
            pack.stamp(path, 1)
            got = pack.info(path)
            self.assertEqual((got.version, got.kind, got.files), (1, 'GNRL', ['Scripts\\X.pex']))


class Doctor(unittest.TestCase):
    def test_missing_config_fails(self):
        r = doctor.check(Path(tempfile.gettempdir()) / 'no_such_ack_config.json')
        self.assertTrue(r.failed)
        self.assertIn('no no_such_ack_config.json', r.text())


if __name__ == '__main__':
    unittest.main()
