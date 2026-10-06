from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import psutil
import win32api
import win32con
import win32event
from scripts.task_control import TaskControl, ControlInterrupted

from scripts.clicker import Clicker
from scripts.config import TEMPLATE_DIR, DEFAULT_PAK_NAMES
from scripts.element_locator import ElementLocator, ElementPosition, MatchResult
from scripts.game_process import GameProcess, GameProcessFinder
from scripts.game_navigation import GameNavigator, NavigationEvent
from scripts.keyboard import KeyboardController
from scripts.privileges import ensure_can_control_process
from scripts.screenshot import ScreenshotService
from scripts.window_binding import BoundWindow, WindowBinder


class Workflow:
    """Game navigation, WeGame actions and Pak file operations."""

    def __init__(
        self,
        game_process_names: tuple[str, ...] = (),
        template_threshold: float = 0.78,
        navigation_step_timeout_seconds: int = 60,
        game_window_timeout_seconds: int = 90,
    ) -> None:
        self.control = TaskControl()
        self.report_progress = lambda message: None
        self.window_binder = WindowBinder()
        self.screenshot = ScreenshotService()
        self.locator = ElementLocator(self.control)
        self.clicker = Clicker(self.control)
        self.keyboard = KeyboardController(self.control)
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
            control=self.control,
        )


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
        source = self.locator.grab_window_bgr(bound_window)
        for template_path in existing_templates:
            self.control.check()
            result = self.locator.match_in_source(source, template_path, bound_window, threshold)
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
        self.control.check()
        current_window = self.window_binder.activate(bound_window)
        self.control.wait(0.25)
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
        self.control.cancelled.set()
        self.game_navigator.cancel()


    def resume_game_navigation(self) -> NavigationEvent:
        return self.game_navigator.resume()

    def resync_game_navigation(self) -> NavigationEvent | None:
        return self.game_navigator.resync_state()

    @property
    def is_navigation_paused(self) -> bool:
        return self.game_navigator.is_paused

    def kill_game_process(self, timeout: float = 15.0) -> tuple[bool, str]:
        if self._game_process is None:
            return False, "没有已记录的三角洲行动游戏进程。"

        game_process = self._game_process
        handle = None
        try:
            proc = psutil.Process(game_process.process_id)
            same_name = proc.name().casefold() == game_process.name.casefold()
            same_start = abs(proc.create_time() - game_process.create_time) < 0.01
            if not (same_name and same_start):
                self._game_process = None
                return False, "原游戏进程已退出，PID 已被其他进程复用。"
            self.control.check()
            # Wait on the original kernel object, not a PID that may be reused.
            handle = win32api.OpenProcess(win32con.SYNCHRONIZE, False, game_process.process_id)
            proc.terminate()
            deadline = time.monotonic() + max(0, timeout)
            while True:
                self.control.check()
                remaining = max(0, deadline - time.monotonic())
                result = win32event.WaitForSingleObject(handle, min(100, int(remaining * 1000)))
                if result == win32event.WAIT_OBJECT_0:
                    self._game_process = None
                    return True, "游戏进程已终止并退出。"
                if result != win32event.WAIT_TIMEOUT:
                    raise RuntimeError(f"等待游戏进程退出失败：返回码={result}")
                if time.monotonic() >= deadline:
                    # A fresh identity check also covers a disappearing process.
                    if not proc.is_running():
                        self._game_process = None
                        return True, "原游戏进程已退出。"
                    return False, (
                        f"等待游戏进程退出超时（{timeout:g}秒，PID={game_process.process_id}）；"
                        "已保留进程记录，停止后续文件操作。"
                    )
        except psutil.NoSuchProcess:
            self._game_process = None
            return True, "游戏进程已经退出。"
        except psutil.AccessDenied:
            return False, "没有权限终止游戏进程。"
        except win32api.error as exc:
            if not proc.is_running():
                self._game_process = None
                return True, "原游戏进程已退出。"
            return False, f"无法确认游戏进程退出：{exc}"
        finally:
            if handle is not None:
                handle.Close()

    @staticmethod
    def get_paks_dir(game_install_dir: str) -> Path:
        """Return the Delta Force Paks directory path for given game install directory."""
        return Path(game_install_dir) / "DeltaForce" / "PackContent" / "Paks"

    def rename_pak_files(self, game_install_dir: str, pak_names=DEFAULT_PAK_NAMES) -> list[str]:
        return self._rename_paks(game_install_dir, pak_names, restore=False)



    def restore_pak_files(self, game_install_dir: str, pak_names=DEFAULT_PAK_NAMES) -> list[str]:
        return self._rename_paks(game_install_dir, pak_names, restore=True)

    def _rename_paks(self, game_install_dir, pak_names, restore):
        pak_dir = self.get_paks_dir(game_install_dir)
        if restore and not pak_dir.is_dir():
            raise FileNotFoundError(f"Paks 目录不存在：{pak_dir}")
        results = []
        for name in pak_names:
            self.control.check()
            normal, disabled = pak_dir / name, pak_dir / f"{name}.disabled"
            source, target = (disabled, normal) if restore else (normal, disabled)
            if not source.exists():
                state = "正常" if restore else "重命名"
                results.append(f"文件已是{state}状态：{target.name}" if target.exists()
                               else f"文件不存在：{name}")
                continue
            if target.exists():
                if not restore:
                    results.append(f"已存在同名重命名文件：{target.name}")
                    continue
                results.append(f"检测到同名正常文件 {name}，正在覆盖恢复...")
                try:
                    self.control.check()
                    target.unlink()
                except OSError as exc:
                    results.append(f"删除同名文件失败：{exc}")
                    continue
            self.control.check()
            source.rename(target)
            action = "恢复正常" if restore else "重命名"
            results.append(f"已{action}：{source.name} -> {target.name}")
        return results


    def get_pak_status(self, game_install_dir: str, pak_names=DEFAULT_PAK_NAMES) -> str:
        pak_dir = self.get_paks_dir(game_install_dir)
        if not game_install_dir or not pak_dir.is_dir():
            return "unknown"
        if any((pak_dir / f"{name}.disabled").exists() for name in pak_names):
            return "disabled"
        return "normal" if any((pak_dir / name).exists() for name in pak_names) else "missing"


    def toggle_pak_files(self, game_install_dir: str, pak_names=DEFAULT_PAK_NAMES) -> tuple[str, list[str]]:
        if self.get_pak_status(game_install_dir, pak_names) == "disabled":
            return "restored", self.restore_pak_files(game_install_dir, pak_names)
        return "disabled", self.rename_pak_files(game_install_dir, pak_names)


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
            self.control.check()
            try:
                self.control.check()
                current_window = self.window_binder.activate(current_bound)
                current_bound = current_window
                self.control.wait(0.3)
                position, template_path = self.find_start_button(
                    current_window, template_names, threshold
                )
                return position, template_path
            except ControlInterrupted:
                raise
            except Exception as exc:
                last_error = str(exc)
                self.control.wait(min(poll_interval, max(0, deadline - time.monotonic())))

        raise TimeoutError(f"等待 WeGame 启动按钮重新出现超时（{timeout:.0f}秒）：{last_error}")

    def click_wegame_more(
        self,
        bound_window: BoundWindow,
        template_name: str = "wegame_more.png",
        threshold: float = 0.78,
    ) -> ElementPosition:
        """Click the '...' (more) button on the WeGame window."""
        self.control.check()
        current_window = self.window_binder.activate(bound_window)
        self.control.wait(0.3)
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
            self.control.check()
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

            self.control.wait(0.5)

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
        confirm_template_name: str = "wegame_confirmdelete.png",
        confirm_timeout: float = 10.0,
        game_install_dir: str = "",
        pak_names: tuple[str, ...] = DEFAULT_PAK_NAMES,
        deletion_timeout: float = 30.0,
        bin_template_name: str = "wegame_bin.png",
    ) -> ElementPosition:
        """Find the resource management window and click delete for changgong map.

        Match the card, hover to reveal its controls, then match the trash icon
        within that card before clicking. No fixed icon offsets are used.

        If the delete button is not visible immediately the method scrolls the
        window downward by *scroll_step* wheel-clicks every *scroll_interval*
        seconds until the button appears or *timeout* is reached.
        """
        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"缺少删除长弓溪谷资源包模板：{template_name}")
        if not (TEMPLATE_DIR / confirm_template_name).exists():
            raise FileNotFoundError(f"缺少确认删除资源包模板：{confirm_template_name}")
        bin_path = TEMPLATE_DIR / bin_template_name
        if not bin_path.exists():
            raise FileNotFoundError(f"缺少垃圾桶图标模板：{bin_template_name}")
        pak_dir = self.get_paks_dir(game_install_dir)
        if not game_install_dir or not pak_dir.is_dir():
            raise ValueError("请先配置正确的游戏安装目录，以核验资源包删除结果。")

        deadline = time.monotonic() + timeout
        best_confidence = 0.0
        last_scroll_at = 0.0

        while time.monotonic() < deadline:
            self.control.check()
            # Ensure the resource manager window is active so it renders in focus (better match confidence)
            # and receives the scroll events properly.
            resource_window = self.window_binder.bind_by_title("游戏资源包管理")
            if resource_window:
                try:
                    self.window_binder.activate(resource_window)
                except ControlInterrupted:
                    raise
                except Exception:
                    pass
            result = self.locator.match_on_screen(template_path, threshold)
            best_confidence = max(best_confidence, result.position.confidence)
            if result.matched:
                pos = result.position
                self.report_progress(
                    f"卡片匹配：中心=({pos.x}, {pos.y}), 尺寸={pos.width}x{pos.height}, "
                    f"confidence={pos.confidence:.3f}；悬停后识别 {bin_template_name}"
                )
                self.clicker.move(pos)
                self.control.wait(0.4)
                try:
                    screenshot_path = self.screenshot.capture_delete_target(
                        pos.x - pos.width // 2, pos.y - pos.height // 2,
                        pos.x - pos.width // 2 + pos.width,
                        pos.y - pos.height // 2 + pos.height,
                    )
                except OSError as exc:
                    self.report_progress(f"保存删除目标截图失败：{exc}")
                else:
                    self.report_progress(f"悬停后的删除目标截图：{screenshot_path}")
                click_pos = self.click_card_bin(pos, bin_path, threshold)
                self.report_progress(f"已发送删除点击：x={click_pos.x}, y={click_pos.y}；等待确认删除弹窗验证。")
                self.confirm_resource_delete(confirm_template_name, threshold, confirm_timeout)
                self.report_progress("确认弹窗已关闭，正在核验资源包文件删除结果。")
                self.wait_for_resource_deletion(game_install_dir, pak_names, deletion_timeout)
                return click_pos

            # Scroll the resource-manager window downward every scroll_interval seconds
            now = time.monotonic()
            if now - last_scroll_at >= scroll_interval:
                last_scroll_at = now
                hwnd_to_scroll = resource_window.handle if resource_window else None
                self._scroll_active_window_down(scroll_step, hwnd_to_scroll)

            self.control.wait(0.3)

        raise RuntimeError(
            f"未在资源包管理窗口中找到删除长弓溪谷按钮（{template_name}），"
            f"最高相似度={best_confidence:.3f}，阈值={threshold:.3f}"
        )

    def click_card_bin(
        self, card: ElementPosition, template_path: Path,
        threshold: float = 0.78, timeout: float = 3.0,
    ) -> ElementPosition:
        if card.width <= 0 or card.height <= 0:
            raise ValueError("卡片识别区域无效，无法定位垃圾桶。")
        left, top = card.x - card.width // 2, card.y - card.height // 2
        region = BoundWindow(0, left=left, top=top,
                             right=left + card.width, bottom=top + card.height)
        deadline = time.monotonic() + timeout
        best_confidence = 0.0
        while time.monotonic() < deadline:
            self.control.check()
            result = self.locator.match_by_image(template_path, region, threshold)
            best_confidence = max(best_confidence, result.position.confidence)
            if result.matched:
                position = result.position
                self.report_progress(
                    f"垃圾桶已匹配：x={position.x}, y={position.y}, "
                    f"confidence={position.confidence:.3f}, template={template_path.name}"
                )
                self.control.check()
                self.clicker.click(replace(position, width=0, height=0))
                return position
            self.control.wait(min(0.2, max(0, deadline - time.monotonic())))
        raise TimeoutError(
            f"悬停后未在长弓卡片内匹配到垃圾桶（{template_path.name}）；"
            f"最高相似度={best_confidence:.3f}，阈值={threshold:.3f}。未发送删除点击。"
        )

    def wait_for_resource_deletion(
        self,
        game_install_dir: str,
        pak_names: tuple[str, ...] = DEFAULT_PAK_NAMES,
        timeout: float = 30.0,
    ) -> None:
        """Confirm actual removal instead of treating mouse input as success."""
        pak_dir = self.get_paks_dir(game_install_dir)
        if not game_install_dir or not pak_dir.is_dir() or not pak_names:
            raise ValueError("无法核验资源包删除：安装目录或目标文件列表无效。")
        paths = [pak_dir / filename for name in pak_names
                 for filename in (name, f"{name}.disabled")]
        deadline = time.monotonic() + timeout
        while True:
            self.control.check()
            if not pak_dir.is_dir():
                raise RuntimeError("Paks 目录不可访问，无法确认删除完成。")
            remaining = [path.name for path in paths if path.exists()]
            if not remaining:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"已点击确认，但资源包删除未完成（{timeout:g}秒）；"
                    f"仍存在：{', '.join(remaining)}。已阻止后续启动游戏。"
                )
            self.control.wait(min(0.3, max(0, deadline - time.monotonic())))

    def confirm_resource_delete(
        self,
        template_name: str = "wegame_confirmdelete.png",
        threshold: float = 0.78,
        timeout: float = 10.0,
    ) -> ElementPosition:
        """Wait for the resource manager's confirmation button and click it."""
        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"缺少确认删除资源包模板：{template_name}")
        self.report_progress(f"确认删除使用模板：{template_path.resolve()}")
        deadline = time.monotonic() + timeout
        best_confidence = 0.0
        window_matches = 0
        screen_matches = 0
        while time.monotonic() < deadline:
            self.control.check()
            resource_window = self.window_binder.bind_by_title("游戏资源包管理")
            if resource_window is not None:
                result = self.locator.match_by_image(template_path, resource_window, threshold)
                window_matches += 1
                best_confidence = max(best_confidence, result.position.confidence)
                if result.matched:
                    self.control.check()
                    return self._click_delete_confirmation(result.position, template_path, threshold)
            # Confirmation dialogs may have a different title or extend beyond
            # the resource manager. Do not refocus its parent over the dialog.
            self.control.check()
            result = self.locator.match_on_screen(template_path, threshold)
            screen_matches += 1
            best_confidence = max(best_confidence, result.position.confidence)
            if result.matched:
                self.control.check()
                return self._click_delete_confirmation(result.position, template_path, threshold)
            self.control.wait(min(0.2, max(0, deadline - time.monotonic())))
        raise TimeoutError(
            f"等待确认删除资源包按钮超时（{timeout:g}秒，{template_name}）；"
            f"最高相似度={best_confidence:.3f}，阈值={threshold:.3f}，"
            f"窗口匹配次数={window_matches}，全屏匹配次数={screen_matches}"
        )

    def _click_delete_confirmation(self, position, template_path, threshold):
        """Click the exact button center and verify the dialog reacts."""
        for attempt in range(1, 4):
            self.control.check()
            self.report_progress(
                f"点击确认删除（第 {attempt} 次）：x={position.x}, y={position.y}, "
                f"confidence={position.confidence:.3f}"
            )
            self.clicker.click(replace(position, width=0, height=0))
            self.control.wait(0.6)
            result = self.locator.match_on_screen(template_path, threshold)
            if not result.matched:
                return position
            position = result.position
            self.report_progress("确认按钮仍显示，点击尚未确认生效。")
        raise RuntimeError("确认删除按钮点击 3 次后仍显示，已停止后续操作。")

    def _scroll_active_window_down(self, clicks: int = 3, hwnd: int | None = None) -> None:
        """Send mouse wheel scroll-down messages to the specified window or foreground window.

        Physically moves the mouse to the center of the window to ensure UI frameworks
        that require mouse-hover (like WeGame's CEF) process the scroll correctly.
        """
        import ctypes
        import win32con as _win32con
        import win32gui as _win32gui

        try:
            self.control.check()
            target_hwnd = hwnd or _win32gui.GetForegroundWindow()
            if not target_hwnd:
                return

            # Find window center
            rect = _win32gui.GetWindowRect(target_hwnd)
            cx = (rect[0] + rect[2]) // 2
            cy = (rect[1] + rect[3]) // 2

            # Move mouse to center
            ctypes.windll.user32.SetCursorPos(cx, cy)

            # Perform scroll (-120 per click for downward scroll)
            wheel_delta = -120 * clicks
            ctypes.windll.user32.mouse_event(_win32con.MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
        except ControlInterrupted:
            raise
        except Exception:
            pass

