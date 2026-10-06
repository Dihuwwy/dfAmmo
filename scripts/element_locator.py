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
        template = self.get_template(template_path)
        source = self.grab_window_bgr()
        height, width = source.shape[:2]
        if template.shape[1] > width or template.shape[0] > height:
            raise ValueError(f"模板尺寸大于全屏截图：template={template.shape[1]}x{template.shape[0]}, screen={width}x{height}")
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
        scale_x = window_width / source_width if source_width else 1.0
        scale_y = window_height / source_height if source_height else 1.0
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
