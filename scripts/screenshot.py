from __future__ import annotations

import re
from pathlib import Path

from PIL import ImageGrab

from scripts.config import PROJECT_ROOT, TEMPLATE_DIR
from scripts.dpi import physical_coordinates


class ScreenshotService:
    """Responsible for screenshots."""

    def capture_delete_target(self, left: int, top: int, right: int, bottom: int) -> Path:
        output_dir = PROJECT_ROOT / "tmp"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "wegame_delete_target.png"
        with physical_coordinates():
            image = ImageGrab.grab(bbox=(left, top, right, bottom))
        image.save(output_path)
        return output_path


    def capture_region_to_template(
        self,
        name: str,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> Path:
        safe_name = self._safe_template_name(name)
        if right <= left or bottom <= top:
            raise ValueError("截图区域无效，请重新框选。")

        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        with physical_coordinates():
            image = ImageGrab.grab(bbox=(left, top, right, bottom))
        output_path = TEMPLATE_DIR / f"{safe_name}.png"
        image.save(output_path)
        return output_path

    def _safe_template_name(self, name: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-z_-]+", "_", name.strip())
        normalized = normalized.strip("_")
        if not normalized:
            raise ValueError("模板名称不能为空。")
        return normalized
