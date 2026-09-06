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

    def start_game_navigation(self, game_process: GameProcess) -> NavigationEvent:
        self._game_process = game_process
        return self.game_navigator.start(game_process.process_id)

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

    def rename_pak_files(
        self,
        game_install_dir: str,
        pak_names: tuple[str, ...] | list[str] = (
            "pak-0-2-pakchunk90-WindowsClient.pak",
            "pak-0-2-pakchunk90optional-WindowsClient.pak",
        ),
    ) -> list[str]:
        pak_dir = Path(game_install_dir) / "DeltaForce" / "PackContent" / "Paks"
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

    def wait_for_wegame_ready(
        self,
        bound_window: BoundWindow,
        template_names: tuple[str, ...],
        threshold: float = 0.78,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> tuple[ElementPosition, Path]:
        """Activate WeGame window and poll until the start button reappears."""
        deadline = time.monotonic() + timeout
        last_error = ""

        while time.monotonic() < deadline:
            QApplication.processEvents()
            try:
                current_window = self.window_binder.activate(bound_window)
                time.sleep(0.3)
                position, template_path = self.find_start_button(
                    current_window, template_names, threshold
                )
                return position, template_path
            except Exception as exc:
                last_error = str(exc)
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
    ) -> ElementPosition:
        """Find the resource management window and click delete for changgong map."""
        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"缺少删除长弓溪谷资源包模板：{template_name}")

        deadline = time.monotonic() + timeout
        best_confidence = 0.0

        while time.monotonic() < deadline:
            QApplication.processEvents()
            result = self.locator.match_on_screen(template_path, threshold)
            best_confidence = max(best_confidence, result.position.confidence)
            if result.matched:
                self.clicker.click(result.position)
                return result.position
            time.sleep(0.6)

        raise RuntimeError(
            f"未在资源包管理窗口中找到删除长弓溪谷按钮（{template_name}），"
            f"最高相似度={best_confidence:.3f}，阈值={threshold:.3f}"
        )

