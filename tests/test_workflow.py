"""Unit tests for Workflow business logic and Pak file management."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.workflow import Workflow


class TestWorkflowPakManagement(unittest.TestCase):
    """Test Suite for Workflow Pak management and path helpers."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.game_dir = Path(self.temp_dir.name)
        self.workflow = Workflow()
        self.pak_names = ["pak1.pak", "pak2.pak"]

        # Create standard directory structure
        self.paks_dir = Workflow.get_paks_dir(str(self.game_dir))
        self.paks_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_paks_dir_path(self) -> None:
        """Workflow.get_paks_dir should produce correct nested path."""
        pdir = Workflow.get_paks_dir(str(self.game_dir))
        expected = self.game_dir / "DeltaForce" / "PackContent" / "Paks"
        self.assertEqual(pdir, expected)

    def test_pak_status_missing_when_no_files(self) -> None:
        """When neither normal nor .disabled files exist, status is 'missing'."""
        status = self.workflow.get_pak_status(str(self.game_dir), self.pak_names)
        self.assertEqual(status, "missing")

    def test_pak_status_normal(self) -> None:
        """When normal .pak files exist, status is 'normal'."""
        for name in self.pak_names:
            (self.paks_dir / name).write_text("dummy")

        status = self.workflow.get_pak_status(str(self.game_dir), self.pak_names)
        self.assertEqual(status, "normal")

    def test_pak_status_disabled(self) -> None:
        """When .disabled files exist, status is 'disabled'."""
        for name in self.pak_names:
            (self.paks_dir / f"{name}.disabled").write_text("dummy")

        status = self.workflow.get_pak_status(str(self.game_dir), self.pak_names)
        self.assertEqual(status, "disabled")

    def test_rename_and_restore_cycle(self) -> None:
        """rename_pak_files should add .disabled and restore_pak_files should revert."""
        for name in self.pak_names:
            (self.paks_dir / name).write_text("dummy")

        # 1. Rename to .disabled
        rename_msgs = self.workflow.rename_pak_files(str(self.game_dir), self.pak_names)
        self.assertEqual(len(rename_msgs), 2)
        for name in self.pak_names:
            self.assertFalse((self.paks_dir / name).exists())
            self.assertTrue((self.paks_dir / f"{name}.disabled").exists())

        # 2. Status should be disabled
        self.assertEqual(
            self.workflow.get_pak_status(str(self.game_dir), self.pak_names),
            "disabled",
        )

        # 3. Restore back to normal
        restore_msgs = self.workflow.restore_pak_files(str(self.game_dir), self.pak_names)
        self.assertEqual(len(restore_msgs), 2)
        for name in self.pak_names:
            self.assertTrue((self.paks_dir / name).exists())
            self.assertFalse((self.paks_dir / f"{name}.disabled").exists())

        # 4. Status should be normal again
        self.assertEqual(
            self.workflow.get_pak_status(str(self.game_dir), self.pak_names),
            "normal",
        )

    def test_toggle_pak_files(self) -> None:
        """toggle_pak_files should alternate between disabled and restored."""
        for name in self.pak_names:
            (self.paks_dir / name).write_text("dummy")

        # Initial toggle -> disabled
        action, _ = self.workflow.toggle_pak_files(str(self.game_dir), self.pak_names)
        self.assertEqual(action, "disabled")

        # Second toggle -> restored
        action, _ = self.workflow.toggle_pak_files(str(self.game_dir), self.pak_names)
        self.assertEqual(action, "restored")


class TestGameNavigatorModeSwitch(unittest.TestCase):
    """Test Suite for GameNavigator handling mode switch via ESC and df_change_mode."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.template_dir = Path(self.temp_dir.name)
        # Create dummy template files
        (self.template_dir / "df_mode_choose.png").write_text("dummy")
        (self.template_dir / "df_change_mode.png").write_text("dummy")

        from unittest.mock import MagicMock
        from scripts.element_locator import ElementPosition, MatchResult
        self.mock_binder = MagicMock()
        self.mock_locator = MagicMock()
        self.mock_locator.match_in_source.return_value = MatchResult(
            position=ElementPosition(x=0, y=0, confidence=0.0), matched=False
        )
        self.mock_locator.match_by_image.return_value = MatchResult(
            position=ElementPosition(x=0, y=0, confidence=0.0), matched=False
        )
        self.mock_clicker = MagicMock()
        self.mock_keyboard = MagicMock()

        from scripts.window_binding import BoundWindow
        self.bound_window = BoundWindow(handle=9999, title="三角洲行动")
        self.mock_binder.bind_by_handle.return_value = self.bound_window
        self.mock_binder.activate.return_value = self.bound_window
        self.mock_binder.bind_by_process_id.return_value = self.bound_window

        from scripts.game_navigation import GameNavigator
        self.navigator = GameNavigator(
            template_dir=self.template_dir,
            threshold=0.78,
            step_timeout_seconds=60,
            window_timeout_seconds=90,
            window_binder=self.mock_binder,
            locator=self.mock_locator,
            clicker=self.mock_clicker,
            keyboard=self.mock_keyboard,
        )
        self.navigator.start(process_id=12345, initial_step=0)
        self.navigator.bound_window = self.bound_window

        from unittest.mock import patch
        self.patcher_is_window = patch("win32gui.IsWindow", return_value=True)
        self.patcher_is_window.start()

    def tearDown(self) -> None:
        self.patcher_is_window.stop()
        self.temp_dir.cleanup()

    def test_step0_matches_df_change_mode(self) -> None:
        """When df_mode_choose is absent but df_change_mode matches, click it and advance."""
        from scripts.element_locator import ElementPosition, MatchResult
        from scripts.game_navigation import NavigationStatus

        def side_effect(source, path, window, threshold):
            if "df_change_mode.png" in str(path):
                return MatchResult(position=ElementPosition(x=400, y=300, confidence=0.92), matched=True)
            return MatchResult(position=ElementPosition(x=0, y=0, confidence=0.3), matched=False)

        self.mock_locator.match_in_source.side_effect = side_effect

        event = self.navigator.tick()
        self.assertIsNotNone(event)
        self.assertEqual(event.status, NavigationStatus.RUNNING)
        self.assertIn("模式切换菜单", event.message)
        self.mock_clicker.click.assert_called_once()
        self.assertEqual(self.navigator.step_index, 1)

    def test_step0_triggers_esc_when_not_matched(self) -> None:
        """When step 0 has elapsed > 3.5s without matching, press ESC to open mode menu."""
        import win32con
        from scripts.element_locator import ElementPosition, MatchResult
        from scripts.game_navigation import NavigationStatus

        self.mock_locator.match_by_image.return_value = MatchResult(
            position=ElementPosition(x=0, y=0, confidence=0.35), matched=False
        )

        # Simulate 4.0s elapsed in step 0
        import time
        now = time.monotonic()
        self.navigator.deadline = now + self.navigator.step_timeout_seconds - 4.0

        event = self.navigator.tick()
        self.assertIsNotNone(event)
        self.assertEqual(event.status, NavigationStatus.RUNNING)
        self.assertIn("ESC", event.message)
        self.mock_keyboard.press.assert_called_with(win32con.VK_ESCAPE, repeat=1)

    def test_resync_state_matches_df_change_mode(self) -> None:
        """resync_state should detect df_change_mode and align to step 0."""
        from unittest.mock import patch
        from scripts.element_locator import ElementPosition, MatchResult

        self.navigator.step_index = 5  # arbitrary different step

        def side_effect(source, path, window, threshold):
            if "df_change_mode.png" in str(path):
                return MatchResult(position=ElementPosition(x=400, y=300, confidence=0.91), matched=True)
            return MatchResult(position=ElementPosition(x=0, y=0, confidence=0.2), matched=False)

        self.mock_locator.match_in_source.side_effect = side_effect
        self.mock_locator.grab_window_bgr.return_value = "dummy_image"

        with patch("win32gui.IsWindow", return_value=True):
            event = self.navigator.resync_state()

        self.assertIsNotNone(event)
        self.assertEqual(self.navigator.step_index, 0)


class TestResourceDeleteConfirmation(unittest.TestCase):
    def test_delete_waits_for_confirmation_before_returning(self):
        from unittest.mock import Mock, patch
        from scripts.element_locator import ElementPosition, MatchResult
        from scripts.window_binding import BoundWindow

        workflow = Workflow()
        window = BoundWindow(123, "游戏资源包管理")
        position = ElementPosition(100, 100, 0.99, 200, 50)
        events = []
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "wegame_delete_map.png").touch()
            (directory / "wegame_confirmdelete.png").touch()
            with patch("scripts.workflow.TEMPLATE_DIR", directory), \
                    patch.object(workflow.window_binder, "bind_by_title", return_value=window), \
                    patch.object(workflow.window_binder, "activate", return_value=window), \
                    patch.object(workflow.locator, "match_on_screen", return_value=MatchResult(position, True)), \
                    patch.object(workflow.clicker, "click", side_effect=lambda *args: events.append("delete")), \
                    patch.object(workflow, "confirm_resource_delete", side_effect=lambda *args: events.append("confirm")):
                workflow.delete_changgong_map()
        self.assertEqual(events, ["delete", "confirm"])

    def test_confirmation_polls_until_matched(self):
        from unittest.mock import patch
        from scripts.element_locator import ElementPosition, MatchResult
        from scripts.window_binding import BoundWindow

        workflow = Workflow()
        position = ElementPosition(200, 300, 0.98)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "wegame_confirmdelete.png").touch()
            with patch("scripts.workflow.TEMPLATE_DIR", directory), \
                    patch.object(workflow.window_binder, "bind_by_title", return_value=BoundWindow(123)), \
                    patch.object(workflow.locator, "match_by_image", side_effect=[
                        MatchResult(position, False), MatchResult(position, True)]), \
                    patch.object(workflow.control, "wait"), \
                    patch.object(workflow.clicker, "click") as click:
                self.assertEqual(workflow.confirm_resource_delete(), position)
                click.assert_called_once_with(position)

    def test_confirmation_timeout_never_clicks(self):
        from unittest.mock import patch
        workflow = Workflow()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "wegame_confirmdelete.png").touch()
            with patch("scripts.workflow.TEMPLATE_DIR", directory), \
                    patch.object(workflow.clicker, "click") as click:
                with self.assertRaises(TimeoutError):
                    workflow.confirm_resource_delete(timeout=0)
                click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
