"""Material Design 3 styling for native Qt widgets."""

COLOR_TEXT_DISABLED = "#A9ABB4"
COLOR_SURFACE_SECONDARY = "#F1F0F4"
COLOR_BORDER_SUBTLE = "#E0E2EC"

MAIN_WINDOW_STYLE = """
QWidget {
    background-color: transparent; color: #191C20;
    font-family: "HarmonyOS Sans SC", "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QWidget#mainWindow, QDialog { background-color: #F8F9FF; }
QFrame[md3_card="true"], QWidget[md3_card="true"], QGroupBox {
    background-color: #FFFFFF; border: 1px solid #E0E2EC; border-radius: 16px;
}
QLabel { background-color: transparent; }
QLabel#sectionTitle, QLabel#connStatusLabel, QLabel[class="stepTitle"] { font-size: 14px; font-weight: bold; }
QLabel#connDetail, QLabel[class="stepSubtitle"], QLabel#fieldLabel { color: #64748B; }
QPushButton {
    background-color: #FFFFFF; color: #44474E; border: 1px solid #C4C6D0;
    border-radius: 16px; padding: 6px 16px; font-weight: 500; min-height: 20px;
}
QPushButton:hover { background-color: #F0F4FA; border-color: #0B57D0; color: #0B57D0; }
QPushButton:pressed { background-color: #DCE2F9; }
QPushButton:disabled { background-color: #F1F0F4; border-color: transparent; color: #A9ABB4; }
QPushButton[md3_type="filled"] {
    background-color: #0B57D0; color: #FFFFFF; border: none;
    border-radius: 18px; padding: 8px 24px; font-size: 14px; font-weight: bold;
}
QPushButton[md3_type="filled"]:hover { background-color: #1B66C9; }
QPushButton[md3_type="filled"]:pressed { background-color: #0842A0; }
QPushButton[md3_type="filled"]:disabled { background-color: #DCE2F9; color: #777B85; }
QPushButton[md3_type="danger_outlined"] { background-color: #FFF5F5; color: #DC2626; border: 1px solid #FECACA; border-radius: 16px; }
QPushButton[md3_type="danger_outlined"]:hover { background-color: #FEE2E2; border-color: #DC2626; }
QPushButton[md3_type="danger_outlined"]:disabled { background-color: #F1F0F4; border-color: transparent; color: #A9ABB4; }
QPushButton[md3_type="step_pill"] {
    background-color: #F1F5F9; color: #334155; border: 1px solid transparent;
    border-radius: 14px; padding: 5px 12px; font-weight: 500;
}
QPushButton[md3_type="step_pill"]:hover { background-color: #E0E7FF; border-color: #93C5FD; color: #0B57D0; }
QPushButton[md3_type="step_pill"]:pressed { background-color: #C7D2FE; }
QPushButton[md3_type="step_pill"][step_state="running"] { background-color: #D3E3FD; color: #0B57D0; border-color: #60A5FA; font-weight: bold; }
QPushButton[md3_type="step_pill"][step_state="done"] { background-color: #DCFCE7; color: #15803D; }
QPushButton[md3_type="step_pill"][step_state="failed"] { background-color: #FEE2E2; color: #DC2626; }
QPushButton[md3_type="step_pill"]:disabled { background-color: #F1F0F4; color: #A9ABB4; border-color: transparent; }
QLabel#stepArrow { color: #94A3B8; font-size: 14px; }
QLabel[class="stepDot"] { background: #FFFFFF; border: 2px solid #CBD5E1; border-radius: 6px; }
QLabel[class="stepDot"][state="running"] { background: #0B57D0; border-color: #0B57D0; }
QLabel[class="stepDot"][state="success"] { background: #10B981; border-color: #10B981; }
QLabel[class="stepDot"][state="failed"] { background: #EF4444; border-color: #EF4444; }
QFrame[md3_type="segmented_container"] { background-color: #F0F4F9; border-radius: 14px; border: 1px solid #E2E8F0; }
QRadioButton { background-color: transparent; color: #475569; border: 1px solid transparent; border-radius: 11px; padding: 4px 14px; font-weight: 500; }
QRadioButton::indicator { width: 0px; height: 0px; }
QRadioButton:checked { background-color: #FFFFFF; color: #0B57D0; font-weight: bold; border-color: #CBD5E1; }
QRadioButton:hover { color: #0B57D0; }
QPushButton[md3_type="dashed"] { background-color: #F3F6FC; color: #0B57D0; border: 1px dashed #7CACF8; border-radius: 12px; padding: 8px; font-weight: bold; }
QPushButton[md3_type="dashed"]:hover { background-color: #E1E9F8; border-color: #0B57D0; }
QPushButton#aboutButton { background: transparent; border: none; padding: 0; border-radius: 12px; }
QPushButton#aboutButton:hover { background: #F0F4FA; }
QLabel[md3_type="badge"] { background-color: #E8F0FE; color: #1967D2; border: none; border-radius: 14px; padding: 6px 14px; font-weight: bold; }
QLabel[md3_type="badge"][state="success"] { background: #D1FAE5; color: #059669; }
QLabel[md3_type="badge"][state="failed"] { background: #FEE2E2; color: #DC2626; }
QLabel[status="disconnected"] { background-color: #FEF3C7; color: #D97706; border-radius: 8px; padding: 2px 8px; font-weight: bold; }
QLabel[status="connected"] { background-color: #D1FAE5; color: #059669; border-radius: 8px; padding: 2px 8px; font-weight: bold; }
QLabel#connDot { color: #CBD5E1; }
QLabel#connDot[connected="true"] { color: #10B981; }
QLineEdit, QComboBox { background-color: #F0F4F9; border: 1px solid transparent; border-radius: 10px; padding: 6px 12px; color: #191C20; min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QComboBox:hover { background-color: #FFFFFF; border-color: #0B57D0; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #FFFFFF; selection-background-color: #D3E3FD; selection-color: #0B57D0; }
QFrame[class="divider"], QFrame[frameShape="4"] { border: none; background: #F1F5F9; min-height: 1px; max-height: 1px; }
QTextEdit, QPlainTextEdit {
    background-color: #1E293B; color: #E2E8F0; border: none; border-radius: 12px; padding: 10px;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas", "Microsoft YaHei"; font-size: 12px;
}
QScrollArea#leftScrollArea { background: transparent; border: none; }
QSplitter::handle { background: #E0E2EC; height: 3px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #C4C6D0; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #FFFFFF; color: #44474E; border: 1px solid #C4C6D0; padding: 5px; }
"""
