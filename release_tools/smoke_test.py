from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
from unittest.mock import MagicMock, patch


def run(arguments: list[str]) -> int:
    """Verify startup without UAC, registered shortcuts, or game interaction."""
    if len(arguments) != 1:
        return 2
    report_path = Path(arguments[0]).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["SystemRoot"]) / "Fonts"))
    window = None
    try:
        import cv2
        import numpy as np
        import psutil
        import win32api
        import win32gui
        import win32process
        import win32security
        from PySide6.QtWidgets import QApplication
        from scripts.config import APP_ICON_PATH, AppConfig, PROJECT_ROOT, TEMPLATE_DIR
        from scripts.element_locator import ElementLocator
        from scripts.gui import MainWindow
        from scripts.update_apply import apply_files
        from scripts.version import current_version
        from scripts.privileges import is_elevated

        if report["frozen"]:
            assert PROJECT_ROOT == Path(sys.executable).resolve().parent
        assert APP_ICON_PATH.is_file(), "Missing application icon"
        templates = list(TEMPLATE_DIR.glob("*.png"))
        assert templates, "Missing external templates"
        for template in templates:
            assert cv2.imdecode(np.fromfile(template, dtype=np.uint8), cv2.IMREAD_COLOR) is not None, template.name
        ElementLocator().delete_confirmation_offset(TEMPLATE_DIR / "wegame_confirmdelete.png")
        with tempfile.TemporaryDirectory(prefix="dfammo-smoke-") as tmp:
            config_path = Path(tmp) / "config.json"
            config = AppConfig.load_from_file(config_path)
            assert config_path.is_file()
            assert config.game_install_dir == ""
            assert AppConfig.load_from_file(config_path).game_install_dir == config.game_install_dir

        app = QApplication.instance() or QApplication(["dfAmmo-self-test"])
        with patch("scripts.gui.QSettings", return_value=MagicMock(value=lambda *args: None)), \
             patch.object(AppConfig, "save_to_file"):
            window = MainWindow(config=AppConfig())
            assert not window.windowIcon().isNull(), "Application icon failed to load"
            assert not window.windowIcon().pixmap(32, 32).isNull(), "Application icon failed to render"
            window.hotkey_timer.stop()
            window.show()
            app.processEvents()
            assert window.width() >= 820
            assert window.execution_mode == "continuous"
            assert window.app_version == current_version()
            window.show_about()
            app.processEvents()
            assert window.check_update_button.parentWidget() is window.about_dialog
            assert not window.install_update_button.isEnabled()
            assert window.about_dialog.grab().save(str(report_path.with_name(report_path.stem + "-about.png")))
            window.about_dialog.close()
            window.full_auto_radio.setChecked(True)
            app.processEvents()
            assert all(not button.isEnabled() for button in window.full_auto_placeholder_buttons)
            window.semi_auto_radio.setChecked(True)
            app.processEvents()
            assert window.grab().save(str(report_path.with_suffix(".png")))
            window.close()
            window = None
        report.update(ok=True, icon_loaded=True, update_support=True, version=current_version(),
                      template_count=len(templates), project_root=str(PROJECT_ROOT),
                      python=sys.version, opencv=cv2.__version__, psutil=psutil.__version__)
    except Exception:
        report["error"] = traceback.format_exc()
        if window is not None:
            window.task_runner.shutdown()
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
