MAIN_WINDOW_STYLE = """
QWidget#mainWindow {
    background: #f5f7fb;
    color: #172033;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
}
QWidget {
    color: #172033;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
}
QLabel {
    background: transparent;
}
QLabel#title {
    font-size: 24px;
    font-weight: 700;
}
QLabel#subtitle {
    color: #607089;
}
QLabel#sectionTitle {
    font-size: 17px;
    font-weight: 700;
}
QFrame#bindPanel,
QFrame#featurePanel,
QFrame#logPanel {
    background: #ffffff;
    border: 1px solid #dce3ed;
    border-radius: 8px;
}
QPushButton {
    background: #1f7aec;
    border: 0;
    border-radius: 6px;
    color: white;
    font-weight: 600;
    padding: 10px 16px;
    min-height: 38px;
}
QPushButton:hover {
    background: #176bd3;
}
QPushButton:pressed {
    background: #1258ad;
}
QPushButton:disabled {
    background: #a8bfdc;
    color: #eef3f9;
}
QPushButton#secondaryButton {
    background: #eef2f7;
    border: 1px solid #cfd8e5;
    color: #34445d;
}
QPushButton#secondaryButton:hover {
    background: #e3e9f1;
}
QPlainTextEdit#logOutput {
    background: #141a23;
    border: 1px solid #293344;
    border-radius: 5px;
    color: #dbe5f3;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 8px;
    selection-background-color: #1f7aec;
}
QRadioButton {
    spacing: 8px;
    font-size: 14px;
    color: #243048;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
}
"""
