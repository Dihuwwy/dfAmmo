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
QLabel#connStatusLabel {
    font-size: 13px;
    font-weight: 700;
    color: #334155;
}
QLabel#connBadge {
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
}
QLabel#connBadge[connected="false"] {
    background: #f1f5f9;
    color: #64748b;
    border: 1px solid #cbd5e1;
}
QLabel#connBadge[connected="true"] {
    background: #ecfdf5;
    color: #059669;
    border: 1px solid #a7f3d0;
}
QLabel#connDetail {
    color: #64748b;
    font-size: 12px;
}
QPushButton#bindButton {
    background: #1f7aec;
    border: 1px solid #1a6cd3;
    border-radius: 6px;
    color: white;
    font-size: 13px;
    font-weight: 600;
    padding: 4px 12px;
    min-height: 30px;
}
QPushButton#bindButton:hover {
    background: #176bd3;
}
QPushButton#bindButton:pressed {
    background: #1258ad;
}
QPushButton {
    background: #1f7aec;
    border: 0;
    border-radius: 6px;
    color: white;
    font-weight: 600;
    padding: 6px 14px;
    min-height: 32px;
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
QPushButton#stopButton {
    background: #e53935;
    border: 0;
    color: white;
    font-weight: 700;
}
QPushButton#stopButton:hover {
    background: #d32f2f;
}
QPushButton#stopButton:pressed {
    background: #b71c1c;
}
QPushButton#stopButton:disabled {
    background: #f2a4a4;
    color: #fbe9e7;
}
QPushButton#pauseButton {
    background: #d97706;
    border: 0;
    color: white;
    font-weight: 600;
}
QPushButton#pauseButton:hover {
    background: #b45309;
}
QPushButton#pauseButton:pressed {
    background: #92400e;
}
QPushButton#pauseButton:disabled {
    background: #e5c596;
    color: #fffbeb;
}
QPushButton#resumeButton {
    background: #10b981;
    border: 0;
    color: white;
    font-weight: 700;
}
QPushButton#resumeButton:hover {
    background: #059669;
}
QPushButton#resumeButton:pressed {
    background: #047857;
}
QPushButton#resumeButton:disabled {
    background: #a7f3d0;
    color: #ecfdf5;
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
QFrame#debugPanel {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 10px;
}
QFrame#debugPanel QLabel {
    color: #e2e8f0;
}
QFrame#debugPanel QLabel#sectionTitle {
    color: #38bdf8;
    font-size: 15px;
    font-weight: 700;
}
QLabel#workflowStatusBadge {
    background: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
}
QLabel#workflowStatusBadge[state="running"] {
    background: #1e3a8a;
    color: #93c5fd;
    border: 1px solid #3b82f6;
}
QLabel#workflowStatusBadge[state="success"] {
    background: #064e3b;
    color: #6ee7b7;
    border: 1px solid #10b981;
}
QLabel#workflowStatusBadge[state="failed"] {
    background: #7f1d1d;
    color: #fca5a5;
    border: 1px solid #ef4444;
}

/* Debug Section Cards */
QFrame.debugSectionCard {
    background: #131d2e;
    border: 1px solid #1e2d42;
    border-radius: 8px;
    padding: 2px;
}
QLabel.debugSectionTitle {
    color: #7dd3fc;
    font-size: 12px;
    font-weight: 700;
}

/* Step Action Buttons */
QPushButton.stepBtn {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    min-height: 28px;
}
QPushButton.stepBtn:hover {
    background: #28384f;
    border-color: #60a5fa;
    color: #ffffff;
}
QPushButton.stepBtn:pressed {
    background: #162030;
}
QPushButton.stepBtn[stepState="idle"] {
    background: #1e293b;
    border: 1px solid #334155;
    color: #cbd5e1;
}
QPushButton.stepBtn[stepState="running"] {
    background: #2563eb;
    border: 2px solid #93c5fd;
    color: #ffffff;
    font-weight: 700;
}
QPushButton.stepBtn[stepState="success"] {
    background: #065f46;
    border: 1px solid #34d399;
    color: #ecfdf5;
    font-weight: 600;
}
QPushButton.stepBtn[stepState="failed"] {
    background: #991b1b;
    border: 1px solid #f87171;
    color: #fef2f2;
    font-weight: 600;
}

QPushButton.stepAuxBtn {
    background: transparent;
    border: 1px dashed #334155;
    border-radius: 6px;
    color: #94a3b8;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
    min-height: 28px;
}
QPushButton.stepAuxBtn:hover {
    border-color: #38bdf8;
    color: #e2e8f0;
    background: #1e293b;
}

QPushButton#debugToggleBtn,
QPushButton#resetStatusBtn {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 5px;
    color: #94a3b8;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    min-height: 26px;
}
QPushButton#debugToggleBtn:hover,
QPushButton#resetStatusBtn:hover {
    background: #273549;
    color: #e2e8f0;
    border-color: #475569;
}

/* Sub-step pills for game navigation (Interactive buttons) */
QPushButton.subStepBtn {
    background: #0b1120;
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 500;
    min-height: 25px;
    max-height: 25px;
}
QPushButton.subStepBtn:hover {
    background: #1e293b;
    border: 1px solid #38bdf8;
    color: #f8fafc;
}
QPushButton.subStepBtn:pressed {
    background: #0f172a;
}
QPushButton.subStepBtn[pillState="active"] {
    background: #1d4ed8;
    color: #ffffff;
    border: 1px solid #60a5fa;
    font-weight: 700;
}
QPushButton.subStepBtn[pillState="active"]:hover {
    background: #2563eb;
    border: 1px solid #93c5fd;
}
QPushButton.subStepBtn[pillState="done"] {
    background: #064e3b;
    color: #6ee7b7;
    border: 1px solid #059669;
}
QPushButton.subStepBtn[pillState="done"]:hover {
    background: #065f46;
    border: 1px solid #34d399;
}
QLabel.subStepPill {
    background: #0b1120;
    color: #64748b;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 500;
}

/* Log Panel action buttons */
QPushButton#clearLogBtn,
QPushButton#copyLogBtn {
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    color: #475569;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    min-height: 22px;
}
QPushButton#clearLogBtn:hover,
QPushButton#copyLogBtn:hover {
    background: #e2e8f0;
    color: #0f172a;
    border-color: #94a3b8;
}

/* Left Scroll Area */
QScrollArea#leftScrollArea {
    background: transparent;
    border: none;
}
QScrollArea#leftScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollArea#leftScrollArea QScrollBar:vertical {
    width: 6px;
    background: transparent;
}
QScrollArea#leftScrollArea QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 3px;
    min-height: 20px;
}
QScrollArea#leftScrollArea QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollArea#leftScrollArea QScrollBar::add-line:vertical,
QScrollArea#leftScrollArea QScrollBar::sub-line:vertical {
    height: 0;
}
"""


