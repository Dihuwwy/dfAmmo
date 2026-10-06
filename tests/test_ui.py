"""Unit tests for Qt GUI layout, component states, and Mixin behaviors."""

from __future__ import annotations

import os
import sys
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Ensure QApplication singleton exists
qt_app = QApplication.instance() or QApplication(sys.argv)

from scripts.config import AppConfig
from scripts.gui import MainWindow


class TestMainWindowUI(unittest.TestCase):
    """Test Suite for MainWindow UI layout and state transitions."""

    def setUp(self) -> None:
        self.config = AppConfig(
            game_install_dir="",
            window_title="Test Assistant",
        )
        self.window = MainWindow(config=self.config)

    def tearDown(self) -> None:
        self.window.close()

    def test_components_instantiation(self) -> None:
        """All main cards, splitters, and panels must be instantiated."""
        self.assertIsNotNone(self.window.bind_panel)
        self.assertIsNotNone(self.window.feature_panel)
        self.assertIsNotNone(self.window.debug_panel)
        self.assertIsNotNone(self.window.log_panel)
        self.assertIsNotNone(self.window.main_splitter)

    def test_vertical_layout_orientation(self) -> None:
        """Main splitter must be vertical with minimum window size (820, 560)."""
        self.assertEqual(self.window.main_splitter.orientation(), Qt.Vertical)
        self.assertEqual(self.window.minimumWidth(), 820)
        self.assertEqual(self.window.minimumHeight(), 560)

    def test_upper_panel_not_clipped(self) -> None:
        """The upper controls area in the splitter must not be smaller than its content sizeHint."""
        sizes = self.window.main_splitter.sizes()
        content_h = self.window.left_column.sizeHint().height()
        self.assertGreaterEqual(sizes[0], content_h)

    def test_step_state_transition(self) -> None:
        """set_step_state should update step button and step dot properties."""
        self.window.set_step_state("nav_game", "running")
        self.assertEqual(self.window.dbg_nav_start_btn.property("stepState"), "running")

        self.window.set_step_state("nav_game", "success")
        self.assertEqual(self.window.dbg_nav_start_btn.property("stepState"), "success")

        self.window.set_step_state("nav_game", "failed")
        self.assertEqual(self.window.dbg_nav_start_btn.property("stepState"), "failed")

        self.window.set_step_state("nav_game", "idle")
        self.assertEqual(self.window.dbg_nav_start_btn.property("stepState"), "idle")

    def test_substep_pills_progression(self) -> None:
        """update_nav_substep_pills should update pillState to done, active, or idle."""
        self.window.update_nav_substep_pills(3)
        pills = self.window.sub_step_pills

        # Steps 0, 1, 2 are done
        for i in range(3):
            self.assertEqual(pills[i].property("pillState"), "done")

        # Step 3 is active
        self.assertEqual(pills[3].property("pillState"), "active")

        # Steps 4..8 are pending
        for i in range(4, len(pills)):
            self.assertEqual(pills[i].property("pillState"), "")

    def test_reset_all_step_states(self) -> None:
        """reset_all_step_states should return all buttons and pills to idle."""
        self.window.set_step_state("nav_game", "running")
        self.window.update_nav_substep_pills(2)

        self.window.reset_all_step_states()
        self.assertEqual(self.window.dbg_nav_start_btn.property("stepState"), "idle")
        for pill in self.window.sub_step_pills:
            self.assertEqual(pill.property("pillState"), "")

    def test_running_controls_toggle(self) -> None:
        """_set_running_controls should invert enable/disable states of control buttons."""
        # When running=True
        self.window._set_running_controls(True)
        self.assertFalse(self.window.start_card_mail_button.isEnabled())
        self.assertTrue(self.window.pause_resume_button.isEnabled())
        self.assertTrue(self.window.stop_button.isEnabled())
        self.assertTrue(self.window.resync_button.isEnabled())

        # When running=False
        self.window._set_running_controls(False)
        self.assertTrue(self.window.start_card_mail_button.isEnabled())
        self.assertFalse(self.window.pause_resume_button.isEnabled())
        self.assertFalse(self.window.stop_button.isEnabled())
        self.assertFalse(self.window.resync_button.isEnabled())

    def test_log_buffer_and_flush(self) -> None:
        """write_log buffers lines and _flush_log_buffer inserts them into QPlainTextEdit."""
        test_msg = "Automated Unit Test Log Line"
        self.window.write_log(test_msg)
        self.window._flush_log_buffer()

        full_log = self.window.log_output.toPlainText()
        self.assertIn(test_msg, full_log)

    def test_status_badge_error_formatting_and_constraints(self) -> None:
        """Status badge must stay compact without raw error messages, with maximum width capped."""
        badge = self.window.workflow_status_badge
        self.assertLessEqual(badge.maximumWidth(), 250)

        long_exc = (
            "[WinError 32] 另一个程序正在使用此文件，进程无法访问。: "
            "'D:\\Program Files\\Steam\\steamapps\\common\\Delta Force\\Game\\DeltaForce\\PackContent\\Paks\\pak.pak'"
        )
        self.window.set_step_state("rename_pak", "failed", long_exc)

        # Badge text must NOT contain the raw exception or long path
        self.assertEqual(badge.text(), "步骤失败：屏蔽 Pak")
        self.assertNotIn("WinError", badge.text())
        self.assertNotIn("Delta Force", badge.text())

        # Detail should be stored in toolTip
        self.assertIn("WinError 32", badge.toolTip())

    def test_step_mode_toggle_state(self) -> None:
        """step_mode_toggle should switch between single-step and continuous mode."""
        toggle = self.window.step_mode_toggle
        self.assertIsNotNone(toggle)
        self.assertEqual(toggle.currentData(), "step")
        self.assertFalse(self.window.is_continuous_mode)
        self.assertEqual(toggle.currentText(), "单步")

        # Click to switch to continuous mode
        toggle.setCurrentIndex(1)
        self.assertEqual(self.window.execution_mode, "stage")
        self.assertFalse(self.window.is_continuous_mode)
        toggle.setCurrentIndex(2)
        self.assertTrue(self.window.is_continuous_mode)
        self.assertEqual(toggle.currentText(), "连续")

        # Click again to switch back to single-step mode
        toggle.setCurrentIndex(0)
        self.assertFalse(self.window.is_continuous_mode)
        self.assertEqual(toggle.currentText(), "单步")

    def test_continuous_mode_substep_chain(self) -> None:
        """_run_wegame_post_process starting from assets_manage should skip earlier steps."""
        from unittest.mock import MagicMock
        from scripts.window_binding import BoundWindow

        self.window.bound_window = BoundWindow(handle=12345, title="WeGame")
        self.window.step_mode_toggle.setCurrentIndex(2)
        self.window.workflow.wait_for_wegame_ready = MagicMock()
        self.window.workflow.click_wegame_more = MagicMock()
        self.window.workflow.click_assets_manage = MagicMock()
        from pathlib import Path
        self.window.workflow.delete_changgong_map = MagicMock(return_value=MagicMock(x=100, y=100))
        self.window.workflow.click_start_button = MagicMock(return_value=(MagicMock(x=200, y=200), Path("template.png")))

        # Run from assets_manage (patch sleep to keep tests fast)
        from unittest.mock import patch
        with patch.object(self.window.workflow.control, "wait"):
            self.window._run_wegame_post_process(start_step="assets_manage")
            import time
            deadline = time.monotonic() + 2
            while self.window.task_runner.busy:
                qt_app.processEvents()
                self.assertLess(time.monotonic(), deadline, "Background chain timed out")
                time.sleep(0.002)

        self.window.workflow.wait_for_wegame_ready.assert_not_called()
        self.window.workflow.click_wegame_more.assert_not_called()
        self.window.workflow.click_assets_manage.assert_called_once()
        self.window.workflow.delete_changgong_map.assert_called_once()
        self.window.workflow.click_start_button.assert_called_once()

    def test_dbg_handlers_respect_mode(self) -> None:
        """Debug handlers should call _run_wegame_post_process in continuous mode."""
        from unittest.mock import MagicMock

        # Single step mode
        self.window.step_mode_toggle.setCurrentIndex(0)
        self.window._run_wegame_post_process = MagicMock()
        self.window._run_debug_step = MagicMock()

        self.window._dbg_assets_manage()
        self.window._run_debug_step.assert_called_once()
        self.window._run_wegame_post_process.assert_not_called()

        # Continuous mode
        self.window.step_mode_toggle.setCurrentIndex(2)
        self.window._run_debug_step.reset_mock()
        self.window._run_wegame_post_process.reset_mock()

        self.window._dbg_assets_manage()
        self.window._run_wegame_post_process.assert_called_once_with(start_step="assets_manage")
        self.window._run_debug_step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
