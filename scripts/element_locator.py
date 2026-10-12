from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab

from scripts.task_control import TaskControl
from scripts.dpi import physical_coordinates
from scripts.window_binding import BoundWindow


@dataclass(frozen=True)
class ElementPosition:
    """Screen position for a recognized UI element."""

    x: int
    y: int
    confidence: float = 0.0
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class MatchResult:
    """Best template match result, even when below threshold."""

    position: ElementPosition
    matched: bool


class ElementLocator:
    """Responsible for recognizing UI element positions."""

    def __init__(self, control: TaskControl | None = None) -> None:
        self.control = control or TaskControl()
        self._template_cache: dict[str, tuple[tuple[int, int], np.ndarray]] = {}

    def get_template(self, template_path: str | Path) -> np.ndarray:
        self.control.check()
        path = Path(template_path)
        key = str(path.resolve())
        stat = path.stat()
        version = (stat.st_mtime_ns, stat.st_size)
        cached = self._template_cache.get(key)
        if cached is None or cached[0] != version:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"模板图片无法读取：{template_path}")
            cached = (version, img)
            self._template_cache[key] = cached
        return cached[1]


    def match_on_screen(self, template_path: str | Path, threshold: float = 0.78) -> MatchResult:
        source = self.grab_window_bgr()
        height, width = source.shape[:2]
        return self.match_in_source(source, template_path,
                                    BoundWindow(0, right=width, bottom=height), threshold)


    def grab_window_bgr(self, bound_window: BoundWindow | None = None) -> np.ndarray:
        self.control.check()
        bbox = ((bound_window.left, bound_window.top, bound_window.right, bound_window.bottom)
                if bound_window else None)
        with physical_coordinates():
            screenshot = ImageGrab.grab(bbox=bbox)
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


    def match_in_source(
        self,
        source: np.ndarray,
        template_path: str | Path,
        bound_window: BoundWindow,
        threshold: float = 0.82,
    ) -> MatchResult:
        template = self.get_template(template_path)
        source_height, source_width = source.shape[:2]
        template_height, template_width = template.shape[:2]

        if template_width > source_width or template_height > source_height:
            return MatchResult(
                position=ElementPosition(
                    x=bound_window.left,
                    y=bound_window.top,
                    confidence=0.0,
                    width=template_width,
                    height=template_height,
                ),
                matched=False,
            )

        result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        self.control.check()
        _, max_value, _, max_location = cv2.minMaxLoc(result)

        window_width = bound_window.right - bound_window.left
        window_height = bound_window.bottom - bound_window.top
        scale_x = window_width / source_width
        scale_y = window_height / source_height
        center_x = bound_window.left + round((max_location[0] + template_width / 2) * scale_x)
        center_y = bound_window.top + round((max_location[1] + template_height / 2) * scale_y)

        return MatchResult(
            position=ElementPosition(
                x=center_x,
                y=center_y,
                confidence=float(max_value),
                width=template_width,
                height=template_height,
            ),
            matched=max_value >= threshold,
        )

    def match_by_image(
        self,
        template_path: str | Path,
        bound_window: BoundWindow,
        threshold: float = 0.82,
    ) -> MatchResult:
        source = self.grab_window_bgr(bound_window)
        return self.match_in_source(source, template_path, bound_window, threshold)

    def delete_confirmation_offset(self, template_path: str | Path) -> tuple[float, float]:
        """Locate the orange confirm button inside the complete dialog template."""
        template = self.get_template(template_path)
        height, width = template.shape[:2]
        if height < 150 or width < 300:
            raise ValueError("确认删除模板必须包含整个弹窗，不能只截按钮。")
        hsv = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([5, 120, 150]), np.array([40, 255, 255]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        buttons = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            # Exclude the top border and warning icon; the orange command is below.
            if y > height / 2 and w > width * 0.15 and height * 0.05 < h < height * 0.25:
                buttons.append((x, y, w, h))
        if len(buttons) != 1:
            raise ValueError("无法在弹窗模板中唯一定位橙色确定按钮，请重新采集完整弹窗。")
        x, y, w, h = buttons[0]
        return (x + w / 2) / width, (y + h / 2) / height
