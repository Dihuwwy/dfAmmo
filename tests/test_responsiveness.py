"""Regression checks with mocked game/Win32 actions; no real clicks or files."""
import ctypes
import os
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import win32con
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from scripts.clicker import Clicker, MOUSEEVENTF_LEFTUP
from scripts.config import AppConfig
from scripts.element_locator import ElementLocator, ElementPosition
from scripts.game_navigation import NavigationEvent, NavigationStatus
from scripts.game_process import GameProcess
from scripts.gui import MainWindow
from scripts.keyboard import KeyboardController
from scripts.task_control import TaskControl, TaskCancelled
from scripts.task_runner import TaskRunner
from scripts.window_binding import BoundWindow
from scripts.workflow import Workflow


APP = QApplication.instance() or QApplication([])


def pump_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate():
        APP.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("Qt/worker operation timed out")
        time.sleep(0.002)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.control = TaskControl()
        self.runner = TaskRunner(self.control)
        self.addCleanup(self.runner.shutdown)

    def test_slow_recognition_does_not_block_qt_and_callbacks_stay_on_gui(self):
        gui_thread = threading.get_ident()
        ticks = []
        threads = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start()
        def operation():
            threads.append(threading.get_ident())
            time.sleep(0.2)
            return 42
        def flow():
            value = yield operation
            threads.append(threading.get_ident())
            self.assertEqual(value, 42)
        self.runner.start(flow())
        pump_until(lambda: not self.runner.busy)
        timer.stop()
        self.assertGreaterEqual(len(ticks), 8)
        self.assertNotEqual(threads[0], gui_thread)
        self.assertEqual(threads[1], gui_thread)

    def test_stop_discards_non_interruptible_result_and_blocks_new_work(self):
        entered = threading.Event()
        release = threading.Event()
        effects = []
        def slow():
            entered.set()
            release.wait(1)
        def flow():
            yield slow
            effects.append("old continuation")
            yield lambda: effects.append("old click")
        self.runner.start(flow())
        self.assertTrue(entered.wait(1))
        self.runner.cancel()
        self.assertTrue(self.runner.busy)
        def new_flow():
            yield lambda: effects.append("new click")
        self.runner.start(new_flow())
        release.set()
        pump_until(lambda: not self.runner.busy)
        self.assertEqual(effects, [])
        self.runner.start(new_flow())
        pump_until(lambda: not self.runner.busy)
        self.assertEqual(effects, ["new click"])

    def test_long_wait_stops_promptly(self):
        entered = threading.Event()
        def operation():
            entered.set()
            self.control.wait(60)
        def flow():
            yield operation
            self.fail("Cancelled flow continued")
        self.runner.start(flow())
        self.assertTrue(entered.wait(1))
        start = time.monotonic()
        self.runner.cancel()
        pump_until(lambda: not self.runner.busy)
        self.assertLess(time.monotonic() - start, 0.5)


class InputTests(unittest.TestCase):
    def test_keyboard_releases_held_key_when_stopped(self):
        control = TaskControl()
        keyboard = KeyboardController(control)
        def interrupt(seconds):
            control.cancelled.set()
            control.check()
        with patch("scripts.keyboard.win32api.keybd_event") as send, patch.object(control, "wait", interrupt):
            with self.assertRaises(TaskCancelled):
                keyboard.press(win32con.VK_SPACE, repeat=5)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args.args[2], win32con.KEYEVENTF_KEYUP)

    def test_mouse_releases_and_does_not_fallback_after_stop(self):
        control = TaskControl()
        clicker = Clicker(control)
        calls = []
        def interrupt(seconds):
            control.cancelled.set()
            control.check()
        with patch.object(clicker, "_screen_bounds", return_value=(0, 0, 1920, 1080)), patch.object(clicker, "_send_inputs", side_effect=lambda events, x, y: calls.append(events)), patch.object(control, "wait", interrupt):
            with self.assertRaises(TaskCancelled):
                clicker._click_with_send_input(100, 100)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1][0].union.mi.dwFlags, MOUSEEVENTF_LEFTUP)
        control.cancelled.clear()
        with patch.object(clicker, "_move_to_point"), patch.object(control, "wait"), patch.object(clicker, "_click_with_send_input", side_effect=TaskCancelled), patch.object(clicker, "_click_with_user32") as fallback:
            with self.assertRaises(TaskCancelled):
                clicker.click(ElementPosition(100, 100))
            fallback.assert_not_called()


class WindowTests(unittest.TestCase):
    def setUp(self):
        # Keep tests from claiming real global keyboard shortcuts.
        with patch("scripts.gui.ctypes.windll.user32.RegisterHotKey", return_value=0):
            self.window = MainWindow(AppConfig(game_install_dir=""))
        self.addCleanup(self.window.close)
        self.game = GameProcess(123, "mock.exe", create_time=1)

    def test_mode_toggle_remains_responsive_during_recognition(self):
        self.window.bound_window = BoundWindow(123)
        with patch.object(self.window.workflow, "wait_for_wegame_ready", side_effect=lambda *a, **k: time.sleep(0.2)):
            self.window._dbg_wait_wegame()
            self.assertTrue(self.window.stop_button.isEnabled())
            self.window.step_mode_toggle.setCurrentIndex(2)
            self.assertTrue(self.window.is_continuous_mode)
            self.assertEqual(self.window.step_mode_toggle.currentText(), "连续")
            pump_until(lambda: not self.window.task_runner.busy)

    def test_shift_f12_native_routes_to_stop(self):
        msg = ctypes.wintypes.MSG()
        msg.message = win32con.WM_HOTKEY
        msg.wParam = 1002
        with patch.object(self.window, "emergency_stop") as stop, patch.object(self.window, "toggle_pause_resume") as pause:
            result = self.window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))
            self.assertEqual(result, (True, 0))
            stop.assert_called_once()
            pause.assert_not_called()

    def test_poll_fallback_triggers_once_per_press(self):
        held = True
        shift = True
        def state(key):
            return 0x8000 if (held if key == win32con.VK_F12 else shift) else 0
        with patch("scripts.gui.win32api.GetAsyncKeyState", side_effect=state), patch.object(self.window, "emergency_stop") as stop, patch.object(self.window, "toggle_pause_resume") as pause:
            for _ in range(20):
                self.window._check_hotkey()
            stop.assert_called_once()
            pause.assert_not_called()
            held = False
            self.window._check_hotkey()
            held = True
            shift = False
            self.window._check_hotkey()
            pause.assert_called_once()

    def test_registered_hotkey_has_no_poll_duplicate(self):
        self.window._registered_hotkeys = {1001, 1002}
        with patch("scripts.gui.win32api.GetAsyncKeyState", return_value=0x8000), patch.object(self.window, "emergency_stop") as stop:
            self.window._check_hotkey()
            stop.assert_not_called()
        self.window._registered_hotkeys.clear()

    def test_pause_interrupts_navigation_and_resume_uses_existing_api(self):
        nav = self.window.workflow.game_navigator
        nav.start(123)
        entered = threading.Event()
        def tick():
            entered.set()
            self.window.workflow.control.wait(60)
        with patch.object(self.window.workflow, "advance_game_navigation", tick):
            self.window.navigation_timer.start()
            self.window.advance_game_navigation()
            self.assertTrue(entered.wait(1))
            self.window.toggle_pause_resume()
            pump_until(lambda: not self.window.task_runner.busy)
            self.assertTrue(nav.is_paused)
            self.assertFalse(self.window.navigation_timer.isActive())
        with patch.object(nav, "resync_state", return_value=None):
            self.window.toggle_pause_resume()
            pump_until(lambda: not self.window.task_runner.busy)
            self.assertFalse(nav.is_paused)
            self.assertTrue(self.window.navigation_timer.isActive())

    def test_stop_after_recognition_prevents_post_processing(self):
        entered = threading.Event()
        release = threading.Event()
        def tick():
            entered.set()
            release.wait(1)
            return NavigationEvent(NavigationStatus.COMPLETE, "mock complete")
        with patch.object(self.window.workflow, "advance_game_navigation", tick), patch.object(self.window.workflow, "kill_game_process") as kill, patch.object(self.window.workflow, "rename_pak_files") as rename, patch("scripts.gui_actions.win32gui.SetForegroundWindow"):
            self.window.advance_game_navigation()
            self.assertTrue(entered.wait(1))
            self.window.emergency_stop()
            release.set()
            pump_until(lambda: not self.window.task_runner.busy)
            kill.assert_not_called()
            rename.assert_not_called()
            self.assertFalse(self.window.navigation_timer.isActive())

    def test_start_failure_reports_in_gui_without_nested_dialog(self):
        self.window.bound_window = BoundWindow(123)
        with patch.object(self.window.workflow, "find_game_process", return_value=None), patch.object(self.window.workflow, "click_start_button", side_effect=RuntimeError("mock failure")), patch("scripts.gui_actions.QMessageBox.warning") as dialog:
            self.window.start_card_mail()
            pump_until(lambda: not self.window.task_runner.busy)
            dialog.assert_not_called()
            self.assertEqual(self.window.workflow_status_badge.property("state"), "failed")
            self.assertTrue(self.window.start_card_mail_button.isEnabled())

    def test_full_wegame_chain_runs_in_order(self):
        self.window.step_mode_toggle.setCurrentIndex(2)
        self.window.bound_window = BoundWindow(123)
        workflow = self.window.workflow
        order = []
        def operation(name, result=None):
            return lambda *a, **k: (order.append(name), result)[1]
        position = ElementPosition(1, 1)
        with patch.object(workflow, "wait_for_wegame_ready", operation("wait")), patch.object(workflow, "click_wegame_more", operation("more")), patch.object(workflow, "click_assets_manage", operation("assets")), patch.object(workflow, "delete_changgong_map", operation("delete", position)), patch.object(workflow, "click_start_button", operation("restart", (position, Path("mock.png")))), patch.object(workflow.control, "wait"):
            self.window._run_wegame_post_process()
            pump_until(lambda: not self.window.task_runner.busy)
        self.assertEqual(order, ["wait", "more", "assets", "delete", "restart"])

    def test_single_navigation_action_pauses_without_finishing_stage(self):
        nav = self.window.workflow.game_navigator
        nav.start(123)
        self.window._navigation_mode = "step"
        event = NavigationEvent(NavigationStatus.RUNNING, "step done", step_completed=True)
        self.window.navigation_timer.start()
        self.window.task_runner.start(self.window._advance_game_navigation_result(event))
        pump_until(lambda: not self.window.task_runner.busy)
        self.assertTrue(nav.is_paused)
        self.assertFalse(nav.finished)
        self.assertFalse(self.window.navigation_timer.isActive())

    def test_stage_mode_keeps_navigation_running_between_actions(self):
        self.window.step_mode_toggle.setCurrentIndex(1)
        nav = self.window.workflow.game_navigator
        nav.start(123)
        event = NavigationEvent(NavigationStatus.RUNNING, "step done", step_completed=True)
        self.window.navigation_timer.start()
        self.window.task_runner.start(self.window._advance_game_navigation_result(event))
        pump_until(lambda: not self.window.task_runner.busy)
        self.assertFalse(nav.is_paused)
        self.assertTrue(self.window.navigation_timer.isActive())

    def test_single_detection_does_not_trigger_stage_post_processing(self):
        self.window._navigation_mode = "step"
        event = NavigationEvent(NavigationStatus.COMPLETE, "detected")
        with patch.object(self.window.workflow, "kill_game_process") as kill:
            self.window.task_runner.start(self.window._advance_game_navigation_result(event))
            pump_until(lambda: not self.window.task_runner.busy)
            kill.assert_not_called()

    def test_stage_finishes_without_starting_next_stage(self):
        self.window.step_mode_toggle.setCurrentIndex(1)
        event = NavigationEvent(NavigationStatus.COMPLETE, "detected")
        with patch.object(self.window.workflow, "kill_game_process", return_value=(True, "exited")), \
                patch.object(self.window.workflow, "rename_pak_files") as rename:
            self.window.task_runner.start(self.window._advance_game_navigation_result(event))
            pump_until(lambda: not self.window.task_runner.busy)
            rename.assert_not_called()


class RecognitionTests(unittest.TestCase):
    def test_recaptured_unicode_template_invalidates_cache(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "模板.png"
            image = np.zeros((12, 12, 3), dtype=np.uint8)
            cv2.imencode(".png", image)[1].tofile(path)
            locator = ElementLocator()
            first = locator.get_template(path)
            image[:] = 255
            cv2.imencode(".png", image)[1].tofile(path)
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            second = locator.get_template(path)
            self.assertFalse(np.array_equal(first, second))

    def test_initial_resync_preserves_completion_event(self):
        workflow = Workflow()
        nav = workflow.game_navigator
        nav.start(123)
        window = BoundWindow(1, title="mock", right=100, bottom=100)
        event = NavigationEvent(NavigationStatus.COMPLETE, "done")
        with patch.object(workflow.window_binder, "bind_by_process_id", return_value=window), patch.object(nav, "resync_state", return_value=event):
            self.assertIs(nav.tick(), event)


if __name__ == "__main__":
    unittest.main()
