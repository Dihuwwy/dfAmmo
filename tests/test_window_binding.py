"""Window recovery checks without activating any real desktop windows."""
import unittest
from unittest.mock import patch

from scripts.window_binding import BoundWindow, WindowBinder


class WindowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.binder = WindowBinder()
        self.original = BoundWindow(10, "WeGame", "browser.exe", 100)
        self.rebuilt = BoundWindow(20, "WeGame", "browser.exe", 100,
                                   right=1280, bottom=800)

    def test_recovers_destroyed_handle(self):
        with patch("scripts.window_binding.win32gui.IsWindow", return_value=False), \
                patch.object(self.binder, "_window_candidates", return_value=[self.rebuilt]):
            self.assertEqual(self.binder.resolve(self.original), self.rebuilt)

    def test_recovers_after_process_restart(self):
        restarted = BoundWindow(30, "WeGame", "browser.exe", 200)
        with patch("scripts.window_binding.win32gui.IsWindow", return_value=False), \
                patch.object(self.binder, "_window_candidates", return_value=[restarted]):
            self.assertEqual(self.binder.resolve(self.original), restarted)

    def test_rejects_reused_handle(self):
        unrelated = BoundWindow(10, "Other app", "other.exe", 300)
        with patch("scripts.window_binding.win32gui.IsWindow", return_value=True), \
                patch.object(self.binder, "bind_by_handle", return_value=unrelated), \
                patch.object(self.binder, "_window_candidates", return_value=[unrelated, self.rebuilt]):
            self.assertEqual(self.binder.resolve(self.original), self.rebuilt)

    def test_rejects_ambiguous_restarted_processes(self):
        candidates = [BoundWindow(20, "WeGame", "browser.exe", 200),
                      BoundWindow(30, "WeGame", "browser.exe", 300)]
        with patch("scripts.window_binding.win32gui.IsWindow", return_value=False), \
                patch.object(self.binder, "_window_candidates", return_value=candidates):
            with self.assertRaisesRegex(RuntimeError, "多个"):
                self.binder.resolve(self.original)

    def test_missing_window_reports_binding_identity(self):
        with patch("scripts.window_binding.win32gui.IsWindow", return_value=False), \
                patch.object(self.binder, "_window_candidates", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "WeGame.*browser.exe"):
                self.binder.resolve(self.original)


if __name__ == "__main__":
    unittest.main()
