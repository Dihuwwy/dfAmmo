from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab

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

    def __init__(self) -> None:
        self._template_cache: dict[str, np.ndarray] = {}

    def get_template(self, template_path: str | Path) -> np.ndarray:
        key = str(template_path)
        if key not in self._template_cache:
            img = cv2.imread(key, cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"模板图片无法读取：{template_path}")
            self._template_cache[key] = img
        return self._template_cache[key]

    def find_by_text(self, text: str) -> ElementPosition | None:
        return None

    def find_by_image(
        self,
        template_path: str | Path,
        bound_window: BoundWindow,
        threshold: float = 0.82,
    ) -> ElementPosition | None:
        result = self.match_by_image(template_path, bound_window, threshold)
        if not result.matched:
            return None
        return result.position

    def find_on_screen(
        self,
        template_path: str | Path,
        threshold: float = 0.78,
    ) -> ElementPosition | None:
        result = self.match_on_screen(template_path, threshold)
        if not result.matched:
            return None
        return result.position

    def match_on_screen(
        self,
        template_path: str | Path,
        threshold: float = 0.78,
    ) -> MatchResult:
        template = self.get_template(template_path)

        with physical_coordinates():
            screenshot = ImageGrab.grab()
        source = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        source_height, source_width = source.shape[:2]
        template_height, template_width = template.shape[:2]

        if template_width > source_width or template_height > source_height:
            raise ValueError(
                "模板尺寸大于全屏截图，无法匹配："
                f"template={template_width}x{template_height}, "
                f"screen={source_width}x{source_height}"
            )

        result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_location = cv2.minMaxLoc(result)

        center_x = round(max_location[0] + template_width / 2)
        center_y = round(max_location[1] + template_height / 2)

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

    def grab_window_bgr(self, bound_window: BoundWindow) -> np.ndarray:
        with physical_coordinates():
            screenshot = ImageGrab.grab(
                bbox=(
                    bound_window.left,
                    bound_window.top,
                    bound_window.right,
                    bound_window.bottom,
                )
            )
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
