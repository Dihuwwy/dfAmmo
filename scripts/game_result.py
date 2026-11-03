from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import win32con

from scripts.game_navigation import step_by_key
from scripts.window_binding import BoundWindow


def notice_confirmation_region(notice, window):
    left = max(window.left, notice.x - notice.width // 2)
    top = notice.y - notice.height // 2 + notice.height
    return BoundWindow(0, left=left, top=top,
                       right=min(window.right, left + notice.width),
                       bottom=min(window.bottom, top + notice.height * 5))


def _active_game_window(workflow):
    """Return the game window, bringing it back if a long wait cost it the foreground."""
    process = workflow.find_game_process()
    window = workflow.window_binder.bind_by_process_id(process.process_id) if process else None
    if window is not None and not workflow.clicker.foreground_belongs_to(window.handle):
        window = workflow.window_binder.activate(window)
        workflow.control.wait(0.15)
    return window


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
        try:
            window = _active_game_window(workflow)
            if window is not None:
                if window.handle != active_handle:
                    active_handle = window.handle
                    workflow.report_progress(f"第四阶段已绑定游戏窗口：handle={window.handle}")
                result = workflow.locator.match_by_image(template_path, window, threshold)
                best_confidence = max(best_confidence, result.position.confidence)
                confirmation = None
                if result.matched:
                    region = notice_confirmation_region(result.position, window)
                    if region.right > region.left and region.bottom > region.top:
                        confirmation = workflow.locator.match_by_image(confirm_path, region, threshold)
                if confirmation is not None and confirmation.matched:
                    workflow.control.check()
                    workflow.clicker.click(replace(confirmation.position, width=0, height=0), window.handle)
                    workflow.report_progress(
                        f"已识别成功大退标志：存在未下载的资源，无法重连入局。"
                        f"相似度={result.position.confidence:.3f}；"
                        f"已点击确认：x={confirmation.position.x}, y={confirmation.position.y}"
                    )
                    return True
        except (OSError, RuntimeError) as exc:
            active_handle = None
            workflow.report_progress(f"第四阶段等待游戏窗口就绪：{exc}")
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    workflow.report_progress(
        f"第四阶段识别或确认按钮等待超时（{timeout:g}秒），结果未确认，未据此判定死亡；"
        f"最高相似度={best_confidence:.3f}"
    )
    return False


def _wait_for_game_ui(workflow, template_paths, threshold, timeout):
    """Wait for a known screen without sending recovery keys."""
    paths = [path for path in template_paths if path.is_file()]
    if not paths:
        raise FileNotFoundError("缺少第四阶段界面模板：" + ", ".join(p.name for p in template_paths))
    deadline = time.monotonic() + timeout
    best_confidence = 0.0
    while time.monotonic() < deadline:
        workflow.control.check()
        window = _active_game_window(workflow)
        if window is not None:
            source = workflow.locator.grab_window_bgr(window)
            for path in paths:
                result = workflow.locator.match_in_source(source, path, window, threshold)
                best_confidence = max(best_confidence, result.position.confidence)
                if result.matched:
                    return window, result.position, path.name
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    raise TimeoutError(
        f"第四阶段等待界面超时（{timeout:g}秒，{', '.join(p.name for p in paths)}）；"
        f"最高相似度={best_confidence:.3f}。未继续后续操作。"
    )


def confirm_notices_and_enter_lobby(workflow, template_path, confirm_path, threshold, timeout):
    """One stage-four action: two notices, mode selection, activities and lobby."""
    progress = workflow.progress
    if not progress.run("first_notice", lambda: wait_for_reconnect_notice(
            workflow, template_path, confirm_path, threshold, timeout)):
        return False
    directory = template_path.parent
    step_timeout = workflow.game_navigator.step_timeout_seconds
    mode_step = step_by_key("select_mode")
    lobby_step = step_by_key("enter_lobby")
    workflow.report_progress("第四阶段：等待烽火模式选择...")
    def choose_mode():
        window, position, _ = _wait_for_game_ui(
            workflow, [directory / mode_step.template_name], threshold, step_timeout)
        workflow.clicker.click(replace(position, width=0, height=0), window.handle)
    progress.run("mode", choose_mode)
    workflow.report_progress("第四阶段：已点击 df_mode_choose，等待第二次提示并确认...")
    workflow.control.wait(mode_step.delay_after)
    if not progress.run("second_notice", lambda: wait_for_reconnect_notice(
            workflow, template_path, confirm_path, threshold, step_timeout)):
        return False
    window = _active_game_window(workflow)
    if window is None:
        raise RuntimeError("第四阶段游戏窗口已退出，未发送空格或 Tab。")
    workflow.control.wait(0.5)
    progress.keys("lobby", workflow.keyboard, lobby_step.key_sequence, window.handle)
    workflow.report_progress("第四阶段：已按两次空格跳过活动并按一次 Tab，等待大厅画面。")
    workflow.control.wait(lobby_step.delay_after)
    _, position, name = _wait_for_game_ui(
        workflow, [directory / "df_map_choose.png", directory / workflow.game_navigator.selected_map_template,
                   directory / "df_start_manoeuver.png"],
        threshold, step_timeout)
    workflow.report_progress(f"第四阶段已进入烽火大厅：{name}，相似度={position.confidence:.3f}；本步完成。")
    return True


def request_map_redownload(workflow, directory, choice_name, panel_name, threshold, timeout):
    """Request the map in-game, then leave verification to the game's own loader."""
    choice, panel = [directory / name for name in (choice_name, panel_name)]
    for path in (choice, panel):
        if not path.is_file():
            raise FileNotFoundError(f"缺少第四阶段地图恢复模板：{path.name}")
    steps = [([directory / "df_map_choose.png", directory / workflow.game_navigator.selected_map_template], "打开地图选择"),
             ([choice], "选择待恢复的地图")]
    def choose(paths, label, following):
        window, position, name = _wait_for_game_ui(workflow, following + paths, threshold, timeout)
        if name in {path.name for path in paths}:
            workflow.clicker.click(replace(position, width=0, height=0), window.handle)
        workflow.report_progress(f"第四阶段：{label} | template={name}, confidence={position.confidence:.3f}")
    for index, (paths, label) in enumerate(steps):
        following = [panel, choice] if index == 0 else [panel]
        workflow.progress.run(f"map_{index}", lambda: choose(paths, label, following))
        workflow.control.wait(0.5)
    workflow.progress.run("download", lambda: _click_map_download(
        workflow, panel, threshold, timeout))
    workflow.control.wait(0.5)
    window = _active_game_window(workflow)
    if window is None:
        raise RuntimeError("第四阶段游戏窗口已退出，未发送 ESC。")
    workflow.progress.keys("return_lobby", workflow.keyboard, ((win32con.VK_ESCAPE, 2),), window.handle)
    workflow.report_progress("第四阶段：已按两次 ESC 返回大厅，地图恢复请求已发送；由游戏自行校验文件。")


def _click_map_download(workflow, panel, threshold, timeout):
    window, position, _ = _wait_for_game_ui(workflow, [panel], threshold, timeout)
    left, top = position.x - position.width // 2, position.y - position.height // 2
    # The download icon is 41px below the 528px-wide upper panel, at x=190.
    download = replace(position, x=left + round(position.width * 190 / 528),
                       y=top + position.height + round(position.width * 41 / 528),
                       width=0, height=0)
    workflow.control.check()
    workflow.clicker.click(download, window.handle)
    workflow.report_progress(f"第四阶段：已点击地图下载图标：x={download.x}, y={download.y}")


def enter_warehouse_and_confirm(workflow, notice_path, confirm_path, threshold, timeout):
    """Finish semi-auto mode without equipping, reconnecting or looping."""
    for path in (notice_path, confirm_path):
        if not path.is_file():
            raise FileNotFoundError(f"缺少仓库提示模板：{path.name}")
    directory = notice_path.parent
    if "warehouse_confirm" in workflow.progress.completed:
        return
    # A retry may already be at the notice; never toggle E on an unknown screen.
    window, _, name = _wait_for_game_ui(
        workflow, [notice_path, directory / "df_map_choose.png",
                   directory / workflow.game_navigator.selected_map_template, directory / "df_start_manoeuver.png"],
        threshold, timeout)
    if name != notice_path.name:
        workflow.control.check()
        window = workflow.window_binder.activate(window)
        workflow.progress.run("warehouse_enter", lambda: workflow.keyboard.press(ord("E"), window_handle=window.handle))
        workflow.report_progress("第四阶段：已在大厅按 E，等待仓库提示...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        workflow.control.check()
        window = _active_game_window(workflow)
        if window is not None:
            source = workflow.locator.grab_window_bgr(window)
            notice = workflow.locator.match_in_source(source, notice_path, window, threshold)
            if notice.matched:
                region = notice_confirmation_region(notice.position, window)
                if region.right > region.left and region.bottom > region.top:
                    cropped = source[region.top - window.top:region.bottom - window.top,
                                     region.left - window.left:region.right - window.left]
                    confirmation = workflow.locator.match_in_source(cropped, confirm_path, region, threshold)
                    if confirmation.matched:
                        workflow.control.check()
                        workflow.progress.run("warehouse_confirm", lambda: workflow.clicker.click(
                            replace(confirmation.position, width=0, height=0), window.handle))
                        workflow.report_progress(
                            f"已识别仓库提示并点击确认：x={confirmation.position.x}, "
                            f"y={confirmation.position.y}, confidence={confirmation.position.confidence:.3f}")
                        return
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    raise TimeoutError(f"等待仓库提示及其确认按钮超时（{timeout:g}秒），未点击其他位置。")
