from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import weakref

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
        self._half_templates: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._half_source: tuple[weakref.ref, np.ndarray] | None = None

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

    def match_resource_card(self, template_path: Path, threshold: float) -> MatchResult:
        source = self.grab_window_bgr()
        height, width = source.shape[:2]
        result = self.match_in_source(source, template_path, BoundWindow(0, right=width, bottom=height), threshold)
        if not result.matched:
            return result
        template = self.get_template(template_path)
        position = result.position
        left = position.x - position.width // 2
        bottom = position.y - position.height // 2 + position.height
        tail = template.shape[0] // 3
        body_width = position.width * 3 // 4
        # Exclude the hover-only trash icon while checking the card's lower edge.
        footer = source[bottom - tail:bottom, left:left + body_width]
        confidence = float(cv2.matchTemplate(footer, template[-tail:, :body_width], cv2.TM_CCOEFF_NORMED)[0, 0])
        return MatchResult(position, confidence >= threshold)


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

        max_value, max_location = self._best_match(source, template, threshold)
        self.control.check()
        center_x = bound_window.left + round(max_location[0] + template_width / 2)
        center_y = bound_window.top + round(max_location[1] + template_height / 2)

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

    def _best_match(self, source: np.ndarray, template: np.ndarray, threshold: float):
        """Return (score, top-left) of the best match.

        A full-resolution search of a whole screen takes about 0.2 s per
        template. Large frames are searched at half size first; the best
        candidates are then scored at full resolution, so a hit has the same
        score and position as the exhaustive search. A near miss falls back
        to the exhaustive search rather than trusting the small image.
        """
        source_height, source_width = source.shape[:2]
        template_height, template_width = template.shape[:2]
        if source_height * source_width < 1_000_000 or min(template_height, template_width) < 32:
            return self._full_match(source, template)

        if self._half_source is None or self._half_source[0]() is not source:
            self._half_source = (weakref.ref(source), cv2.resize(source, None, fx=0.5, fy=0.5,
                                                                 interpolation=cv2.INTER_AREA))
        half_source = self._half_source[1]
        cached = self._half_templates.get(id(template))
        if cached is None or cached[0] is not template:
            cached = (template, cv2.resize(template, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
            self._half_templates[id(template)] = cached
        half_template = cached[1]
        coarse = np.nan_to_num(cv2.matchTemplate(half_source, half_template, cv2.TM_CCOEFF_NORMED),
                               nan=-1.0, posinf=-1.0, neginf=-1.0)
        coarse_best = float(coarse.max())
        best_value, best_location = -1.0, (0, 0)
        margin = 4
        for _ in range(3):
            _, value, _, (x, y) = cv2.minMaxLoc(coarse)
            if value < coarse_best - 0.2:
                break
            left, top = max(0, 2 * x - margin), max(0, 2 * y - margin)
            region = source[top:2 * y + margin + template_height, left:2 * x + margin + template_width]
            if region.shape[0] >= template_height and region.shape[1] >= template_width:
                fine_value, (fine_x, fine_y) = self._full_match(region, template)
                if fine_value > best_value:
                    best_value, best_location = fine_value, (left + fine_x, top + fine_y)
            # Suppress this peak before looking for the next candidate.
            coarse[max(0, y - half_template.shape[0] // 2):y + half_template.shape[0] // 2 + 1,
                   max(0, x - half_template.shape[1] // 2):x + half_template.shape[1] // 2 + 1] = -1.0
        if best_value < threshold and coarse_best >= threshold - 0.2:
            return self._full_match(source, template)
        return best_value, best_location

    @staticmethod
    def _full_match(source: np.ndarray, template: np.ndarray):
        _, value, _, location = cv2.minMaxLoc(cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED))
        return float(value), location

    def match_by_image(
        self,
        template_path: str | Path,
        bound_window: BoundWindow,
        threshold: float = 0.82,
    ) -> MatchResult:
        source = self.grab_window_bgr(bound_window)
        return self.match_in_source(source, template_path, bound_window, threshold)

    def find_fill_teammates(self, source, bound_window, template_path):
        """Find the label from its text strokes, then read the box from its own pixels.

        The ranked-mode toggle uses the same box, so only the text identifies this
        control. Neither step compares against the lobby background around it.
        """
        template = cv2.cvtColor(self.get_template(template_path), cv2.COLOR_BGR2GRAY)
        # The supplied 135x45 control has a 25x25 box at (8, 10) and its label after x=36.
        strokes = cv2.dilate(cv2.inRange(template[:, 36:], 85, 255), np.ones((3, 3), dtype=np.uint8))
        label = cv2.bitwise_and(cv2.Canny(template[:, 36:], 60, 120), strokes)
        rows, columns = np.nonzero(label)
        offset_x, offset_y = 36 + int(columns.min()), int(rows.min())
        label = label[rows.min():rows.max() + 1, columns.min():columns.max() + 1]
        top = source.shape[0] // 2
        gray = cv2.cvtColor(source[top:], cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 120)
        mask = cv2.dilate(label, np.ones((3, 3), dtype=np.uint8))
        scores = cv2.matchTemplate(edges, label, cv2.TM_CCORR_NORMED, mask=mask)
        scores = np.nan_to_num(scores, nan=-1.0, posinf=-1.0, neginf=-1.0)
        _, confidence, _, (x, y) = cv2.minMaxLoc(scores)
        x, y = x - offset_x, y - offset_y
        if confidence < 0.88 or x + 8 < 0 or y + 10 < 0:
            return None
        box = gray[y + 10:y + 35, x + 8:x + 33].astype(float)
        if box.shape != (25, 25):
            return None
        # Each layer is compared with the dark ring inside the box, not with the lobby.
        ring = np.median(np.concatenate((box[2, 5:20], box[22, 5:20], box[5:20, 2], box[5:20, 22])))
        border = np.median(np.concatenate((box[0, 5:20], box[24, 5:20], box[5:20, 0], box[5:20, 24])))
        if border - ring < 25:
            return None
        checked = box[8:17, 8:17].mean() - ring >= 60
        return ElementPosition(bound_window.left + x + 20,
                               bound_window.top + top + y + 22, confidence), bool(checked)

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
