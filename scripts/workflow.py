from __future__ import annotations

import time
from pathlib import Path

import psutil
from PySide6.QtWidgets import QApplication

from scripts.clicker import Clicker
from scripts.config import TEMPLATE_DIR
from scripts.element_locator import ElementLocator, ElementPosition, MatchResult
from scripts.game_process import GameProcess, GameProcessFinder
from scripts.game_navigation import GameNavigator, NavigationEvent
from scripts.keyboard import KeyboardController
from scripts.ocr import OcrReader
from scripts.privileges import ensure_can_control_process
from scripts.screenshot import ScreenshotService
from scripts.window_binding import BoundWindow, WindowBinder


class Workflow:
    """High-level workflow orchestration placeholder."""

    def __init__(
        self,
        game_process_names: tuple[str, ...] = (),
        template_threshold: float = 0.78,
        navigation_step_timeout_seconds: int = 60,
        game_window_timeout_seconds: int = 90,
    ) -> None:
        self.window_binder = WindowBinder()
        self.screenshot = ScreenshotService()
        self.ocr = OcrReader()
        self.locator = ElementLocator()
        self.clicker = Clicker()
        self.keyboard = KeyboardController()
        self.game_process_finder = GameProcessFinder(game_process_names)
        self._game_process: GameProcess | None = None
        self.game_navigator = GameNavigator(
            template_dir=TEMPLATE_DIR,
            threshold=template_threshold,
            step_timeout_seconds=navigation_step_timeout_seconds,
            window_timeout_seconds=game_window_timeout_seconds,
            window_binder=self.window_binder,
            locator=self.locator,
            clicker=self.clicker,
            keyboard=self.keyboard,
        )

    def run_once(self) -> bool:
        return False

    def find_start_button(
        self,
        bound_window: BoundWindow,
        template_names: tuple[str, ...],
        threshold: float = 0.78,
    ) -> tuple[ElementPosition, Path]:
        existing_templates = [TEMPLATE_DIR / name for name in template_names if (TEMPLATE_DIR / name).exists()]
        if not existing_templates:
            names = ", ".join(template_names)
            raise FileNotFoundError(f"没有找到启动按钮模板，请先采集模板：{names}")

        best_result: tuple[MatchResult, Path] | None = None
        for template_path in existing_templates:
            result = self.locator.match_by_image(template_path, bound_window, threshold)
            if best_result is None or result.position.confidence > best_result[0].position.confidence:
                best_result = (result, template_path)
            if result.matched:
                return result.position, template_path

        if best_result is None:
            raise RuntimeError("没有可用模板。")

        result, template_path = best_result
        raise RuntimeError(
            "没有在绑定窗口里匹配到启动按钮。"
            f"最佳模板={template_path.name}，"
            f"最高相似度={result.position.confidence:.3f}，"
            f"阈值={threshold:.3f}，"
            f"最佳坐标=({result.position.x}, {result.position.y})。"
        )

    def click_start_button(
        self,
        bound_window: BoundWindow,
        template_names: tuple[str, ...],
        threshold: float = 0.78,
    ) -> tuple[ElementPosition, Path]:
        ensure_can_control_process(bound_window.process_id)
        current_window = self.window_binder.activate(bound_window)
        time.sleep(0.25)
        position, template_path = self.find_start_button(current_window, template_names, threshold)
        self.clicker.click(position, current_window.handle)
        return position, template_path

    def find_game_process(self) -> GameProcess | None:
        return self.game_process_finder.find()

    def start_game_navigation(self, game_process: GameProcess, initial_step: int = 0) -> NavigationEvent:
        self._game_process = game_process
        return self.game_navigator.start(game_process.process_id, initial_step=initial_step)

    def jump_to_navigation_step(self, step_index: int) -> NavigationEvent:
        return self.game_navigator.jump_to_step(step_index)

    def advance_game_navigation(self) -> NavigationEvent | None:
        return self.game_navigator.tick()

    def cancel_game_navigation(self) -> None:
        self.game_navigator.cancel()

    def pause_game_navigation(self) -> NavigationEvent:
        return self.game_navigator.pause()

    def resume_game_navigation(self) -> NavigationEvent:
        return self.game_navigator.resume()

    def resync_game_navigation(self) -> NavigationEvent | None:
        return self.game_navigator.resync_state()

    @property
    def is_navigation_paused(self) -> bool:
        return self.game_navigator.is_paused

    def kill_game_process(self) -> tuple[bool, str]:
        if self._game_process is None:
            return False, "没有已记录的三角洲行动游戏进程。"

        game_process = self._game_process
        try:
            proc = psutil.Process(game_process.process_id)
            same_name = proc.name().casefold() == game_process.name.casefold()
            same_start = abs(proc.create_time() - game_process.create_time) < 0.01
            if not (same_name and same_start):
                self._game_process = None
                return False, "原游戏进程已退出，PID 已被其他进程复用。"
            proc.terminate()
            try:
                proc.wait(timeout=5)
                self._game_process = None
                return True, "游戏进程已终止并退出。"
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                pass
        except psutil.NoSuchProcess:
            self._game_process = None
            return True, "游戏进程已经退出。"
        except psutil.AccessDenied:
            return False, "没有权限终止游戏进程。"

        self._game_process = None
        if psutil.pid_exists(game_process.process_id):
            return False, "已发送终止请求，但尚未确认进程退出；已停止后续文件操作。"
        return True, "游戏进程已终止并退出。"

    @staticmethod
    def get_paks_dir(game_install_dir: str) -> Path:
        """Return the Delta Force Paks directory path for given game install directory."""
        return Path(game_install_dir) / "DeltaForce" / "PackContent" / "Paks"

    def rename_pak_files(
        self,
        game_install_dir: str,
        pak_names: tuple[str, ...] | list[str] = (
            "pak-0-2-pakchunk90-WindowsClient.pak",
            "pak-0-2-pakchunk90optional-WindowsClient.pak",
        ),
    ) -> list[str]:
        pak_dir = self.get_paks_dir(game_install_dir)
        results: list[str] = []

        for pak_name in pak_names:
            pak_path = pak_dir / pak_name
            disabled_path = pak_dir / f"{pak_name}.disabled"

            if not pak_path.exists():
                if disabled_path.exists():
                    results.append(f"文件已是重命名状态：{disabled_path.name}")
                else:
                    results.append(f"文件不存在：{pak_path.name}")
                continue

            if disabled_path.exists():
                results.append(f"已存在同名重命名文件：{disabled_path.name}")
                continue

            pak_path.rename(disabled_path)
            results.append(f"已重命名：{pak_name} -> {disabled_path.name}")

        return results

    def rename_pak_file(self, game_install_dir: str) -> str:
        results = self.rename_pak_files(game_install_dir)
        return "\n".join(results)

    def restore_pak_files(
        self,
        game_install_dir: str,
        pak_names: tuple[str, ...] | list[str] = (
            "pak-0-2-pakchunk90-WindowsClient.pak",
            "pak-0-2-pakchunk90optional-WindowsClient.pak",
        ),
    ) -> list[str]:
        pak_dir = self.get_paks_dir(game_install_dir)
        results: list[str] = []

        if not pak_dir.is_dir():
            raise FileNotFoundError(f"Paks 目录不存在：{pak_dir}")

        for pak_name in pak_names:
            pak_path = pak_dir / pak_name
            disabled_path = pak_dir / f"{pak_name}.disabled"

            if not disabled_path.exists():
                if pak_path.exists():
                    results.append(f"文件已是正常状态：{pak_name}")
                else:
                    results.append(f"文件不存在：{pak_name}（及 .disabled）")
                continue

            if pak_path.exists():
                results.append(f"检测到同名正常文件 {pak_name}，正在覆盖恢复...")
                try:
                    pak_path.unlink()
                except OSError as exc:
                    results.append(f"删除同名文件失败：{exc}")
                    continue

            disabled_path.rename(pak_path)
            results.append(f"已恢复正常：{disabled_path.name} -> {pak_name}")

        return results

    def get_pak_status(
        self,
        game_install_dir: str,
        pak_names: tuple[str, ...] | list[str] = (
            "pak-0-2-pakchunk90-WindowsClient.pak",
            "pak-0-2-pakchunk90optional-WindowsClient.pak",
        ),
    ) -> str:
        """Return 'disabled' if any target pak has .disabled extension, 'normal' if present without .disabled, or 'missing'."""
        if not game_install_dir:
            return "unknown"
        pak_dir = self.get_paks_dir(game_install_dir)
        if not pak_dir.is_dir():
            return "unknown"

        disabled_count = 0
        normal_count = 0
        for pak_name in pak_names:
            disabled_path = pak_dir / f"{pak_name}.disabled"
            pak_path = pak_dir / pak_name
            if disabled_path.exists():
                disabled_count += 1
            elif pak_path.exists():
                normal_count += 1

        if disabled_count > 0:
            return "disabled"
        if normal_count > 0:
            return "normal"
        return "missing"

    def toggle_pak_files(
        self,
        game_install_dir: str,
        pak_names: tuple[str, ...] | list[str] = (
            "pak-0-2-pakchunk90-WindowsClient.pak",
            "pak-0-2-pakchunk90optional-WindowsClient.pak",
        ),
    ) -> tuple[str, list[str]]:
        """Toggle pak files between .disabled and normal .pak.

        Returns:
            ("disabled", results): if files were renamed to .disabled
            ("restored", results): if files were restored back to normal .pak
        """
        status = self.get_pak_status(game_install_dir, pak_names)
        if status == "disabled":
            results = self.restore_pak_files(game_install_dir, pak_names)
            return "restored", results
        else:
            results = self.rename_pak_files(game_install_dir, pak_names)
            return "disabled", results

    def wait_for_wegame_ready(
        self,
        bound_window: BoundWindow,
        template_names: tuple[str, ...],
        threshold: float = 0.78,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> tuple[ElementPosition, Path]:
        """Activate WeGame window and poll until the start button reappears.

        If the originally-bound handle has become stale (e.g. WeGame rebuilt its
        main window after the game process exited), this method re-enumerates all
        visible windows owned by the same WeGame process and retries with the
        refreshed handle instead of failing outright.
        """
        deadline = time.monotonic() + timeout
        last_error = ""
        current_bound = bound_window  # may be refreshed inside the loop

        while time.monotonic() < deadline:
            QApplication.processEvents()
            try:
                current_window = self.window_binder.activate(current_bound)
                time.sleep(0.3)
                position, template_path = self.find_start_button(
                    current_window, template_names, threshold
                )
                return position, template_path
            except Exception as exc:
                last_error = str(exc)
                # If handle is stale, try re-locating the WeGame window by process id
                if current_bound.process_id is not None:
                    try:
                        refreshed = self.window_binder.bind_by_process_id(
                            current_bound.process_id
                        )
                        if refreshed is not None and refreshed.handle != current_bound.handle:
                            current_bound = refreshed
                    except Exception:
                        pass
                time.sleep(poll_interval)

        raise TimeoutError(f"等待 WeGame 启动按钮重新出现超时（{timeout:.0f}秒）：{last_error}")

    def click_wegame_more(
        self,
        bound_window: BoundWindow,
        template_name: str = "wegame_more.png",
        threshold: float = 0.78,
    ) -> ElementPosition:
        """Click the '...' (more) button on the WeGame window."""
        current_window = self.window_binder.activate(bound_window)
        time.sleep(0.3)
        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"缺少 WeGame 更多按钮模板：{template_name}")

        result = self.locator.match_by_image(template_path, current_window, threshold)
        if not result.matched:
            raise RuntimeError(
                f"未能匹配到 WeGame 更多按钮（{template_name}），"
                f"最高相似度={result.position.confidence:.3f}，阈值={threshold:.3f}"
            )

        self.clicker.click(result.position, current_window.handle)
        return result.position

    def click_assets_manage(
        self,
        bound_window: BoundWindow,
        template_name: str = "wegame_assets_manage.png",
        threshold: float = 0.78,
        timeout: float = 6.0,
    ) -> ElementPosition:
        """Click '游戏资源包管理' from the popup menu."""
        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"缺少游戏资源包管理模板：{template_name}")

        deadline = time.monotonic() + timeout
        best_confidence = 0.0

        while time.monotonic() < deadline:
            QApplication.processEvents()
            current_window = self.window_binder.activate(bound_window)
            result = self.locator.match_by_image(template_path, current_window, threshold)
            best_confidence = max(best_confidence, result.position.confidence)
            if result.matched:
                self.clicker.click(result.position, current_window.handle)
                return result.position

            screen_result = self.locator.match_on_screen(template_path, threshold)
            best_confidence = max(best_confidence, screen_result.position.confidence)
            if screen_result.matched:
                self.clicker.click(screen_result.position)
                return screen_result.position

            time.sleep(0.5)

        raise RuntimeError(
            f"未能匹配到“游戏资源包管理”菜单项（{template_name}），"
            f"最高相似度={best_confidence:.3f}，阈值={threshold:.3f}"
        )

    def delete_changgong_map(
        self,
        template_name: str = "wegame_delete_map.png",
        threshold: float = 0.78,
        timeout: float = 30.0,
        scroll_step: int = 3,
        scroll_interval: float = 0.8,
    ) -> ElementPosition:
        """Find the resource management window and click delete for changgong map.

        The template covers the entire card row (thumbnail + text).  After
        matching, the click is redirected to the right edge of the card where
        the trash-can delete icon lives, rather than the card center.

        If the delete button is not visible immediately the method scrolls the
        window downward by *scroll_step* wheel-clicks every *scroll_interval*
        seconds until the button appears or *timeout* is reached.
        """
        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"缺少删除长弓溪谷资源包模板：{template_name}")

        deadline = time.monotonic() + timeout
        best_confidence = 0.0
        last_scroll_at = 0.0

        while time.monotonic() < deadline:
            QApplication.processEvents()
            result = self.locator.match_on_screen(template_path, threshold)
            best_confidence = max(best_confidence, result.position.confidence)
            if result.matched:
                pos = result.position
                # The template spans the whole row; the trash-can icon sits at
                # the far-right edge of the card.  Shift the click from the
                # matched center to (left_edge + card_width - 18px).
                # pos.x is already the center of the matched region, and
                # pos.width is the template width, so right_edge = pos.x + pos.width // 2.
                # We back off ~18 px from the right to land on the icon.
                click_x = pos.x + pos.width // 2 - 18
                click_pos = ElementPosition(
                    x=click_x, y=pos.y,
                    confidence=pos.confidence,
                    width=pos.width, height=pos.height,
                )
                self.clicker.click(click_pos)
                return click_pos

            # Scroll the resource-manager window downward every scroll_interval seconds
            now = time.monotonic()
            if now - last_scroll_at >= scroll_interval:
                last_scroll_at = now
                self._scroll_active_window_down(scroll_step)

            time.sleep(0.3)

        raise RuntimeError(
            f"未在资源包管理窗口中找到删除长弓溪谷按钮（{template_name}），"
            f"最高相似度={best_confidence:.3f}，阈值={threshold:.3f}"
        )

    def _scroll_active_window_down(self, clicks: int = 3) -> None:
        """Send WM_MOUSEWHEEL scroll-down messages to the foreground window."""
        import win32api as _win32api
        import win32con as _win32con
        import win32gui as _win32gui

        try:
            hwnd = _win32gui.GetForegroundWindow()
            if not hwnd:
                return
            rect = _win32gui.GetWindowRect(hwnd)
            cx = (rect[0] + rect[2]) // 2
            cy = (rect[1] + rect[3]) // 2
            lparam = _win32api.MAKELONG(cx, cy)
            # WHEEL_DELTA = 120; negative = downward scroll
            wheel_delta = -120 * clicks
            wparam = _win32api.MAKELONG(0, wheel_delta & 0xFFFF)
            _win32gui.PostMessage(hwnd, _win32con.WM_MOUSEWHEEL, wparam, lparam)
        except Exception:
            pass

