"""Process exit confirmation with mocked Windows handles only."""
import unittest
from unittest.mock import Mock, patch

import win32event

from scripts.game_process import GameProcess
from scripts.task_control import TaskCancelled
from scripts.workflow import Workflow


class ProcessExitTests(unittest.TestCase):
    def setUp(self):
        self.workflow = Workflow()
        self.game = GameProcess(123, "mock.exe", create_time=1.0)
        self.workflow._game_process = self.game
        self.proc = Mock()
        self.proc.name.return_value = self.game.name
        self.proc.create_time.return_value = self.game.create_time
        self.handle = Mock()
        self.patchers = [
            patch("scripts.workflow.psutil.Process", return_value=self.proc),
            patch("scripts.workflow.win32api.OpenProcess", return_value=self.handle),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_signalled_original_handle_confirms_exit_even_if_pid_exists(self):
        with patch("scripts.workflow.win32event.WaitForSingleObject",
                   return_value=win32event.WAIT_OBJECT_0), \
                patch("scripts.workflow.psutil.pid_exists", return_value=True) as exists:
            exited, _ = self.workflow.kill_game_process()
        self.assertTrue(exited)
        exists.assert_not_called()
        self.assertIsNone(self.workflow._game_process)
        self.handle.Close.assert_called_once()

    def test_timeout_retains_record(self):
        self.proc.is_running.return_value = True
        with patch("scripts.workflow.win32event.WaitForSingleObject",
                   return_value=win32event.WAIT_TIMEOUT):
            exited, message = self.workflow.kill_game_process(timeout=0)
        self.assertFalse(exited)
        self.assertIn("超时", message)
        self.assertIs(self.workflow._game_process, self.game)
        self.handle.Close.assert_called_once()

    def test_final_identity_check_detects_exit(self):
        self.proc.is_running.return_value = False
        with patch("scripts.workflow.win32event.WaitForSingleObject",
                   return_value=win32event.WAIT_TIMEOUT):
            exited, _ = self.workflow.kill_game_process(timeout=0)
        self.assertTrue(exited)
        self.assertIsNone(self.workflow._game_process)

    def test_cancel_closes_handle_and_retains_record(self):
        def wait(*args):
            self.workflow.control.cancelled.set()
            return win32event.WAIT_TIMEOUT
        with patch("scripts.workflow.win32event.WaitForSingleObject", side_effect=wait):
            with self.assertRaises(TaskCancelled):
                self.workflow.kill_game_process()
        self.handle.Close.assert_called_once()
        self.assertIs(self.workflow._game_process, self.game)


if __name__ == "__main__":
    unittest.main()
