from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

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
