from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import win32con

from scripts.game_navigation import NAVIGATION_STEPS
from scripts.task_control import ControlInterrupted
from scripts.window_binding import BoundWindow


def notice_confirmation_region(notice, window):
    left = max(window.left, notice.x - notice.width // 2)
    top = notice.y - notice.height // 2 + notice.height
    return BoundWindow(0, left=left, top=top,
                       right=min(window.right, left + notice.width),
                       bottom=min(window.bottom, top + notice.height * 5))


def wait_for_reconnect_notice(workflow, template_path: Path, confirm_path: Path,
                             threshold: float, timeout: float) -> bool:
    """Recognize the notice, then click its associated confirmation command."""
    for path in (template_path, confirm_path):
        if not path.is_file():
            raise FileNotFoundError(f"缺少第四阶段识别模板：{path.name}")
    deadline = time.monotonic() + timeout
    best_confidence = 0.0
    active_handle = None
    while time.monotonic() < deadline:
        workflow.control.check()
        process = workflow.find_game_process()
        window = workflow.window_binder.bind_by_process_id(process.process_id) if process else None
        if window is not None:
            try:
                if window.handle != active_handle:
                    window = workflow.window_binder.activate(window)
                    active_handle = window.handle
                    workflow.report_progress(f"第四阶段已绑定游戏窗口：handle={window.handle}")
                result = workflow.locator.match_by_image(template_path, window, threshold)
                confirmation = None
                if result.matched:
                    region = notice_confirmation_region(result.position, window)
                    if region.right > region.left and region.bottom > region.top:
                        confirmation = workflow.locator.match_by_image(confirm_path, region, threshold)
            except ControlInterrupted:
                raise
            except (OSError, RuntimeError) as exc:
                active_handle = None
                workflow.report_progress(f"第四阶段等待游戏窗口就绪：{exc}")
            else:
                best_confidence = max(best_confidence, result.position.confidence)
                if result.matched and confirmation is not None and confirmation.matched:
                    workflow.control.check()
                    workflow.clicker.click(replace(confirmation.position, width=0, height=0), window.handle)
                    workflow.report_progress(
                        f"已识别成功大退标志：存在未下载的资源，无法重连入局。"
                        f"相似度={result.position.confidence:.3f}；"
                        f"已点击确认：x={confirmation.position.x}, y={confirmation.position.y}"
                    )
                    return True
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    workflow.report_progress(
        f"第四阶段识别或确认按钮等待超时（{timeout:g}秒），结果未确认，未据此判定死亡；"
        f"最高相似度={best_confidence:.3f}"
    )
    return False


def _wait_for_game_ui(workflow, template_paths, threshold, timeout, entrance_path=None):
    """Wait for a known screen; Tab is allowed once, only at the entrance prompt."""
    paths = [path for path in template_paths if path.is_file()]
    if not paths:
        raise FileNotFoundError("缺少第四阶段界面模板：" + ", ".join(p.name for p in template_paths))
    deadline = time.monotonic() + timeout
    active_handle = None
    tab_sent = False
    best_confidence = 0.0
    while time.monotonic() < deadline:
        workflow.control.check()
        process = workflow.find_game_process()
        window = workflow.window_binder.bind_by_process_id(process.process_id) if process else None
        if window is not None:
            if window.handle != active_handle:
                window = workflow.window_binder.activate(window)
                active_handle = window.handle
            source = workflow.locator.grab_window_bgr(window)
            for path in paths:
                result = workflow.locator.match_in_source(source, path, window, threshold)
                best_confidence = max(best_confidence, result.position.confidence)
                if result.matched:
                    return window, result.position, path.name
            if not tab_sent and entrance_path is not None and entrance_path.is_file():
                entrance = workflow.locator.match_in_source(source, entrance_path, window, threshold)
                if entrance.matched:
                    workflow.window_binder.activate(window)
                    workflow.keyboard.press(win32con.VK_TAB, repeat=1)
                    tab_sent = True
                    workflow.report_progress("第四阶段：已识别特勤处入口，按一次 Tab 进入烽火大厅。")
                    workflow.control.wait(1.0)
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    raise TimeoutError(
        f"第四阶段等待界面超时（{timeout:g}秒，{', '.join(p.name for p in paths)}）；"
        f"最高相似度={best_confidence:.3f}。未继续后续操作。"
    )


def confirm_notices_and_enter_lobby(workflow, template_path, confirm_path, threshold, timeout):
    """One stage-four action: two notices, mode selection, activities and lobby."""
    if not wait_for_reconnect_notice(workflow, template_path, confirm_path, threshold, timeout):
        return False
    directory = template_path.parent
    step_timeout = workflow.game_navigator.step_timeout_seconds
    workflow.report_progress("第四阶段：等待烽火模式选择...")
    window, position, _ = _wait_for_game_ui(
        workflow, [directory / NAVIGATION_STEPS[0].template_name], threshold, step_timeout)
    workflow.control.check()
    workflow.clicker.click(replace(position, width=0, height=0), window.handle)
    workflow.report_progress("第四阶段：已点击 df_mode_choose，等待第二次提示并确认...")
    workflow.control.wait(NAVIGATION_STEPS[0].delay_after)
    if not wait_for_reconnect_notice(workflow, template_path, confirm_path, threshold, step_timeout):
        return False
    process = workflow.find_game_process()
    window = workflow.window_binder.bind_by_process_id(process.process_id) if process else None
    if window is None:
        raise RuntimeError("第四阶段游戏窗口已退出，未发送空格或 Tab。")
    workflow.window_binder.activate(window)
    workflow.control.wait(0.5)
    workflow.keyboard.press_sequence(NAVIGATION_STEPS[1].key_sequence)
    workflow.report_progress("第四阶段：已按五次空格跳过活动，等待大厅或特勤处入口。")
    workflow.control.wait(NAVIGATION_STEPS[1].delay_after)
    _, position, name = _wait_for_game_ui(
        workflow, [directory / "df_map_choose.png", directory / "df_map_choose_selected.png",
                   directory / "df_start_manoeuver.png"],
        threshold, step_timeout, entrance_path=directory / "df_enter_game.png")
    workflow.report_progress(f"第四阶段已进入烽火大厅：{name}，相似度={position.confidence:.3f}；本步完成。")
    return True
