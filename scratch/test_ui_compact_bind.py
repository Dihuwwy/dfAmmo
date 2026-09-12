import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, r"c:\Users\48563\Documents\Coding\PycharmProjects\dfAmmo")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from scripts.gui import MainWindow
from scripts.config import AppConfig
from scripts.window_binding import BoundWindow

app = QApplication(sys.argv)
config = AppConfig.load_from_file()
window = MainWindow(config)
window.show()

output_dir = Path(r"C:\Users\48563\.gemini\antigravity-ide\brain\77ecd455-aa88-4ae0-a65a-9a124375ce1b")
output_dir.mkdir(parents=True, exist_ok=True)

# Step 1: Capture initial startup state (unbound)
def capture_unbound():
    pix = window.grab()
    unbound_path = output_dir / "ui_startup_unbound.png"
    pix.save(str(unbound_path))
    print(f"Captured unbound UI: {unbound_path}")
    
    # Step 2: Simulate window binding
    mock_window = BoundWindow(
        handle=123456,
        title="WeGame - 游戏客户端",
        left=100,
        top=100,
        right=1380,
        bottom=820,
        process_id=9876,
        process_name="wegame.exe"
    )
    window.bound_window = mock_window
    info_text = (
        f"{mock_window.title} | "
        f"{mock_window.process_name} | "
        f"pid={mock_window.process_id} | "
        f"handle={mock_window.handle}"
    )
    window.conn_badge.setText("🟢 已连接")
    window.conn_badge.setProperty("connected", "true")
    window.conn_badge.style().unpolish(window.conn_badge)
    window.conn_badge.style().polish(window.conn_badge)
    window.conn_badge.update()
    window.conn_detail_label.setText(info_text)
    window.bind_button.default_text = "🎯 重新拖拽绑定"
    window.bind_button.setText("🎯 重新拖拽绑定")
    window.subtitle.setText("WeGame 窗口已绑定，可以开始执行自动化流程或单步调试。")
    window.write_log(f"窗口绑定成功：{info_text}")

    QTimer.singleShot(400, capture_bound)

def capture_bound():
    pix = window.grab()
    bound_path = output_dir / "ui_bound_connected.png"
    pix.save(str(bound_path))
    print(f"Captured bound UI: {bound_path}")
    app.quit()

QTimer.singleShot(600, capture_unbound)
sys.exit(app.exec())
