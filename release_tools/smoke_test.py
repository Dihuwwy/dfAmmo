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
    # The offscreen platform has no GPU surface for the scene graph.
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["SystemRoot"]) / "Fonts"))
    controller = None
    try:
        import cv2
        import numpy as np
        import psutil
        from PySide6.QtCore import QMetaObject, QObject
        from PySide6.QtWidgets import QApplication
        from scripts.config import APP_ICON_PATH, AppConfig, PROJECT_ROOT, TEMPLATE_DIR
        from scripts.element_locator import ElementLocator
        from scripts.gui import QML_DIR, MainController
        from scripts.version import current_version

        if report["frozen"]:
            assert PROJECT_ROOT == Path(sys.executable).resolve().parent
        assert APP_ICON_PATH.is_file(), "Missing application icon"
        templates = list(TEMPLATE_DIR.glob("*.png"))
        assert templates, "Missing external templates"
        assert (QML_DIR / "Main.qml").is_file(), "Missing QML interface"
        for template in templates:
            assert cv2.imdecode(np.fromfile(template, dtype=np.uint8), cv2.IMREAD_COLOR) is not None, template.name
        ElementLocator().delete_confirmation_offset(TEMPLATE_DIR / "wegame_resource_delete_confirm.png")
        with tempfile.TemporaryDirectory(prefix="dfammo-smoke-") as tmp:
            config_path = Path(tmp) / "config.json"
            config = AppConfig.load_from_file(config_path)
            assert config_path.is_file()
            assert config.game_install_dir == ""
            assert AppConfig.load_from_file(config_path).game_install_dir == config.game_install_dir

        app = QApplication.instance() or QApplication(["dfAmmo-self-test"])
        with patch("scripts.gui.QSettings", return_value=MagicMock(value=lambda *args: None)), \
             patch.object(AppConfig, "save_to_file"):
            controller = MainController(config=AppConfig())
            window = controller.window
            assert not window.icon().isNull(), "Application icon failed to load"
            controller.hotkey_timer.stop()
            controller.show()
            app.processEvents()
            assert window.width() >= 820
            assert controller.execution_mode == "continuous"
            assert controller.app_version == current_version()
            about = window.findChild(QObject, "aboutDialog")
            assert about is not None, "About dialog missing"
            assert not controller._ui_state["canInstallUpdate"]
            QMetaObject.invokeMethod(about, "open")
            app.processEvents()
            assert window.grabWindow().save(str(report_path.with_name(report_path.stem + "-about.png")))
            QMetaObject.invokeMethod(about, "close")
            controller.set_operation_mode("full_auto")
            app.processEvents()
            assert controller._ui_state["operationMode"] == "full_auto"
            controller.set_operation_mode("semi_auto")
            app.processEvents()
            assert window.grabWindow().save(str(report_path.with_suffix(".png")))
            controller.shutdown()
            controller = None
        report.update(ok=True, icon_loaded=True, update_support=True, version=current_version(),
                      template_count=len(templates), project_root=str(PROJECT_ROOT),
                      python=sys.version, opencv=cv2.__version__, psutil=psutil.__version__)
    except Exception:
        report["error"] = traceback.format_exc()
        if controller is not None:
            controller.shutdown()
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
