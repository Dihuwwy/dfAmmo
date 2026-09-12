import sys
import tempfile
from pathlib import Path
from dataclasses import replace

sys.path.insert(0, r"c:\Users\48563\Documents\Coding\PycharmProjects\dfAmmo")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from scripts.gui import MainWindow
from scripts.config import AppConfig

app = QApplication(sys.argv)

output_dir = Path(r"C:\Users\48563\.gemini\antigravity-ide\brain\77ecd455-aa88-4ae0-a65a-9a124375ce1b")
temp_dir = tempfile.mkdtemp()
paks_dir = Path(temp_dir) / "DeltaForce" / "PackContent" / "Paks"
paks_dir.mkdir(parents=True, exist_ok=True)

test_files = [
    "pak-0-2-pakchunk90-WindowsClient.pak",
    "pak-0-2-pakchunk90optional-WindowsClient.pak",
]
for name in test_files:
    (paks_dir / name).write_text("test")

cfg = AppConfig.load_from_file()
cfg = replace(cfg, game_install_dir=temp_dir)
window = MainWindow(cfg)
window.resize(1180, 720)
window.show()

def step1_capture_normal():
    pix = window.grab()
    pix.save(str(output_dir / "ui_pak_normal.png"))
    
    # Click toggle -> should rename to disabled
    window._dbg_rename_pak()
    QTimer.singleShot(400, step2_capture_disabled)

def step2_capture_disabled():
    pix = window.grab()
    pix.save(str(output_dir / "ui_pak_disabled.png"))
    
    # Click toggle again -> should restore
    window._dbg_rename_pak()
    QTimer.singleShot(400, step3_capture_restored)

def step3_capture_restored():
    pix = window.grab()
    pix.save(str(output_dir / "ui_pak_restored.png"))
    app.quit()

QTimer.singleShot(500, step1_capture_normal)
sys.exit(app.exec())
