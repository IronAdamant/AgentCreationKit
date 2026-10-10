"""DialogWatcher safety: unknown dialogs are captured and never clicked; allowlisted ones are."""
import ctypes
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ack.xedit.dialogs import DialogWatcher, Rule

IDOK, IDCANCEL = 1, 2
MB_OKCANCEL = 0x1


def show_box(title, result):
    result['ret'] = ctypes.windll.user32.MessageBoxW(None, 'Save changed files?', title, MB_OKCANCEL)


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class Watcher(unittest.TestCase):
    def _open(self, title):
        result = {}
        t = threading.Thread(target=show_box, args=(title, result), daemon=True)
        t.start()
        time.sleep(0.8)  # let the box appear
        return t, result

    def _dismiss(self, t, result):
        if t.is_alive():  # close it ourselves so the test never leaves a window behind
            from ack import win32
            for w in win32.process_windows(os.getpid()):
                if w.title.startswith('ACK test'):
                    win32.close(w.hwnd)
        t.join(5)

    def test_unknown_dialog_is_captured_not_clicked(self):
        t, result = self._open('ACK test unknown')
        with tempfile.TemporaryDirectory() as d:
            w = DialogWatcher(os.getpid(), Path(d), save=False, rules=[])
            for _ in range(3):
                w.poll()
                time.sleep(0.2)
            self.assertTrue(t.is_alive(), 'watcher must not dismiss an unknown dialog')
            self.assertTrue(any('ACK test unknown' == e.title for e in w.unknown))
            self.assertTrue(list(Path(d).glob('unknown_*.json')))
        self._dismiss(t, result)

    def test_allowlisted_dialog_is_clicked(self):
        t, result = self._open('ACK test known')
        rule = Rule(name='test', title='ACK test known', buttons=['OK', 'Cancel'], action='click:Cancel')
        with tempfile.TemporaryDirectory() as d:
            w = DialogWatcher(os.getpid(), Path(d), save=False, rules=[rule])
            w.poll()
            t.join(5)
        self.assertEqual(result.get('ret'), IDCANCEL)

    def test_save_only_rule_ignored_in_read_runs(self):
        t, result = self._open('ACK test saveonly')
        rule = Rule(name='test', title='ACK test saveonly', buttons=['OK'], action='click:OK', when='save')
        with tempfile.TemporaryDirectory() as d:
            w = DialogWatcher(os.getpid(), Path(d), save=False, rules=[rule])
            w.poll()
            time.sleep(0.3)
            self.assertTrue(t.is_alive(), 'save-only rule must not fire when save=False')
        self._dismiss(t, result)


if __name__ == '__main__':
    unittest.main()
