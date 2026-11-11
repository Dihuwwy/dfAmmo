from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import win32con
import win32gui

from scripts.game_navigation import step_by_key
from scripts.window_binding import BoundWindow

# Windows closing mid-call, a refused foreground, or a screen that cannot be captured.
TRANSIENT_ERRORS = (OSError, RuntimeError, win32gui.error)


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


def _wait_for_game_window(workflow, timeout, action):
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        workflow.control.check()
        try:
            window = _active_game_window(workflow)
            if window is not None:
                return window
        except TRANSIENT_ERRORS as exc:
            last_error = str(exc)
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    raise RuntimeError(f"第四阶段未能取得游戏窗口，未发送{action}。{last_error}")


def _screen_shows(workflow, paths, threshold):
    """Look at the game once: the name of the first template on screen, or None."""
    try:
        window = _active_game_window(workflow)
        if window is None:
            return None
        source = workflow.locator.grab_window_bgr(window)
    except TRANSIENT_ERRORS:
        return None
    for path in paths:
        if path.is_file() and workflow.locator.match_in_source(source, path, window, threshold).matched:
            return path.name
    return None


def _forget(progress, *names):
    """Drop checkpoints, including per-key ones, so their inputs are sent again."""
    for key in list(progress.completed):
        if key in names or (isinstance(key, tuple) and key[0] in names):
            del progress.completed[key]


def _mark_keys_sent(progress, name, sequence):
    for index, (_, repeat) in enumerate(sequence):
        for number in range(repeat):
            progress.completed[(name, index, number)] = None


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
        except TRANSIENT_ERRORS as exc:
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
    last_error = ""
    while time.monotonic() < deadline:
        workflow.control.check()
        try:
            window = _active_game_window(workflow)
            if window is not None:
                source = workflow.locator.grab_window_bgr(window)
                for path in paths:
                    result = workflow.locator.match_in_source(source, path, window, threshold)
                    best_confidence = max(best_confidence, result.position.confidence)
                    if result.matched:
                        return window, result.position, path.name
        except TRANSIENT_ERRORS as exc:
            last_error = str(exc)
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    raise TimeoutError(
        f"第四阶段等待界面超时（{timeout:g}秒，{', '.join(p.name for p in paths)}）；"
        f"最高相似度={best_confidence:.3f}。未继续后续操作。{last_error}"
    )


def confirm_notices_and_enter_lobby(workflow, template_path, confirm_path, threshold, timeout):
    """One stage-four action: two notices, mode selection, activities and lobby."""
    progress = workflow.progress
    directory = template_path.parent
    step_timeout = workflow.game_navigator.step_timeout_seconds
    mode_step = step_by_key("select_mode")
    lobby_step = step_by_key("enter_lobby")
    mode_path = directory / mode_step.template_name
    lobby_paths = [directory / "df_map_choose.png", directory / workflow.game_navigator.selected_map_template,
                   directory / "df_start_manoeuver.png"]
    if progress.completed:
        # Resuming: checkpoints record what was sent, the screen shows what took effect.
        seen = _screen_shows(workflow, [*lobby_paths, mode_path, template_path], threshold)
        if seen in {path.name for path in lobby_paths}:
            progress.completed.update(first_notice=True, mode=None, second_notice=True)
            _mark_keys_sent(progress, "lobby", lobby_step.key_sequence)
        elif seen == mode_path.name:
            progress.completed["first_notice"] = True
            _forget(progress, "mode", "second_notice", "lobby")
        elif seen == template_path.name:
            _forget(progress, "second_notice" if "mode" in progress.completed else "first_notice", "lobby")
        if seen:
            workflow.report_progress(f"[对齐] 第四阶段当前画面：{seen}，据此继续。")
    if not progress.run("first_notice", lambda: wait_for_reconnect_notice(
            workflow, template_path, confirm_path, threshold, timeout)):
        return False
    workflow.report_progress("第四阶段：等待烽火模式选择...")
    def choose_mode():
        window, position, _ = _wait_for_game_ui(workflow, [mode_path], threshold, step_timeout)
        workflow.clicker.click(replace(position, width=0, height=0), window.handle)
    progress.run("mode", choose_mode)
    workflow.report_progress("第四阶段：已点击 df_mode_choose，等待第二次提示并确认...")
    workflow.control.wait(mode_step.delay_after)
    if not progress.run("second_notice", lambda: wait_for_reconnect_notice(
            workflow, template_path, confirm_path, threshold, step_timeout)):
        return False
    window = _wait_for_game_window(workflow, step_timeout, "空格或 Tab")
    workflow.control.wait(0.5)
    progress.keys("lobby", workflow.keyboard, lobby_step.key_sequence, window.handle)
    workflow.report_progress("第四阶段：已按两次空格跳过活动并按一次 Tab，等待大厅画面。")
    workflow.control.wait(lobby_step.delay_after)
    _, position, name = _wait_for_game_ui(workflow, lobby_paths, threshold, step_timeout)
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
    progress = workflow.progress
    if progress.completed:
        # Resuming: a later screen is handled below; an earlier one means its click must be redone.
        seen = _screen_shows(workflow, [panel, choice, *steps[0][0]], threshold)
        if seen in {path.name for path in steps[0][0]}:
            if "download" in progress.completed:
                _mark_keys_sent(progress, "return_lobby", ((win32con.VK_ESCAPE, 2),))
            else:
                _forget(progress, "map_0", "map_1")
        elif seen == choice.name and "download" not in progress.completed:
            _forget(progress, "map_1")
        if seen:
            workflow.report_progress(f"[对齐] 第四阶段当前画面：{seen}，据此继续。")
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
    window = _wait_for_game_window(workflow, timeout, "ESC")
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
        # Back in the lobby, an earlier E no longer counts.
        workflow.progress.completed.pop("warehouse_enter", None)
        window = workflow.window_binder.activate(window)
        workflow.progress.run("warehouse_enter", lambda: workflow.keyboard.press(ord("E"), window_handle=window.handle))
        workflow.report_progress("第四阶段：已在大厅按 E，等待仓库提示...")
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        workflow.control.check()
        try:
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
        except TRANSIENT_ERRORS as exc:
            last_error = str(exc)
        workflow.control.wait(min(0.7, max(0, deadline - time.monotonic())))
    raise TimeoutError(f"等待仓库提示及其确认按钮超时（{timeout:g}秒），未点击其他位置。{last_error}")
