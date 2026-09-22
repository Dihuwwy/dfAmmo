"""Design tokens and unified Windows desktop utility stylesheet for dfAmmo Assistant.

Adheres strictly to Windows desktop utility conventions:
- Information architecture prioritized over decoration
- Solid colors only (zero gradients)
- Compact, high-density desktop layout (4px-6px radii)
- 1px subtle borders and separators
- Monospace quiet dark log panel
"""

# ── Design Tokens ─────────────────────────────────────────────────────────────

# Color Palette (Solid Colors)
COLOR_APP_BG = "#F6F7F9"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_SECONDARY = "#F8FAFC"
COLOR_SURFACE_HOVER = "#F1F5F9"
COLOR_SURFACE_PRESSED = "#E2E8F0"

COLOR_BORDER = "#DDE1E7"
COLOR_BORDER_SUBTLE = "#E6E9ED"
COLOR_BORDER_FOCUS = "#2563EB"

COLOR_TEXT_MAIN = "#1F2328"
COLOR_TEXT_SECONDARY = "#475569"
COLOR_TEXT_MUTED = "#64748B"
COLOR_TEXT_DISABLED = "#94A3B8"

# Semantic Accents (Low Saturation)
COLOR_PRIMARY = "#2563EB"
COLOR_PRIMARY_HOVER = "#1D4ED8"
COLOR_PRIMARY_PRESSED = "#1E40AF"
COLOR_PRIMARY_DISABLED = "#93C5FD"

COLOR_SUCCESS = "#16A34A"
COLOR_SUCCESS_BG = "#F0FDF4"
COLOR_SUCCESS_BORDER = "#86EFAC"

COLOR_WARNING = "#D97706"
COLOR_WARNING_BG = "#FFFBEB"
COLOR_WARNING_BORDER = "#FDE68A"

COLOR_DANGER = "#DC2626"
COLOR_DANGER_BG = "#FEF2F2"
COLOR_DANGER_BORDER = "#FECACA"

# Log Console (The only dark surface)
COLOR_LOG_BG = "#15191F"
COLOR_LOG_BORDER = "#232B38"
COLOR_LOG_TEXT = "#D8DEE9"

# Geometry & Metrics
RADIUS_CONTROL = "4px"
RADIUS_PANEL = "6px"

MAIN_WINDOW_STYLE = f"""
/* ── Global App Canvas ────────────────────────────────────────────────────── */
QWidget#mainWindow {{
    background-color: {COLOR_APP_BG};
    color: {COLOR_TEXT_MAIN};
    font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei", -apple-system, sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {COLOR_TEXT_MAIN};
    font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei", -apple-system, sans-serif;
    font-size: 13px;
}}

QLabel {{
    background: transparent;
    color: {COLOR_TEXT_MAIN};
}}

/* Typography */
QLabel#windowTitle {{
    font-size: 16px;
    font-weight: 600;
    color: {COLOR_TEXT_MAIN};
}}

QLabel#sectionTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {COLOR_TEXT_MAIN};
}}

QLabel#fieldLabel {{
    font-size: 12px;
    font-weight: 500;
    color: {COLOR_TEXT_SECONDARY};
}}

QLabel#secondaryText {{
    font-size: 12px;
    color: {COLOR_TEXT_MUTED};
}}

/* ── Panel / Surface Containers ───────────────────────────────────────────── */
QFrame#connectionBar,
QFrame#settingsCard,
QFrame#stepperCard,
QFrame#logPanel {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_PANEL};
}}

/* Horizontal 1px Divider */
QFrame.divider {{
    background-color: {COLOR_BORDER_SUBTLE};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* ── Connection Bar Components ────────────────────────────────────────────── */
QLabel#connStatusLabel {{
    font-size: 13px;
    font-weight: 600;
    color: {COLOR_TEXT_MAIN};
}}

QLabel#connDetail {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
}}

QLabel#connDot {{
    font-size: 11px;
}}
QLabel#connDot[connected="false"] {{
    color: {COLOR_TEXT_DISABLED};
}}
QLabel#connDot[connected="true"] {{
    color: {COLOR_SUCCESS};
}}

QLabel#connBadge {{
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 500;
}}
QLabel#connBadge[connected="false"] {{
    background-color: {COLOR_SURFACE_HOVER};
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_BORDER};
}}
QLabel#connBadge[connected="true"] {{
    background-color: {COLOR_SUCCESS_BG};
    color: {COLOR_SUCCESS};
    border: 1px solid {COLOR_SUCCESS_BORDER};
}}

/* ── Form Controls (Inputs, Radios) ───────────────────────────────────────── */
QLineEdit {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    padding: 0 8px;
    min-height: 28px;
    max-height: 30px;
    selection-background-color: {COLOR_PRIMARY};
}}

QLineEdit:hover {{
    border-color: #CBD5E1;
}}

QLineEdit:focus {{
    border-color: {COLOR_BORDER_FOCUS};
    background-color: #FFFFFF;
}}

QLineEdit:disabled {{
    background-color: {COLOR_SURFACE_HOVER};
    color: {COLOR_TEXT_DISABLED};
    border-color: {COLOR_BORDER_SUBTLE};
}}

QRadioButton {{
    spacing: 6px;
    font-size: 12px;
    color: {COLOR_TEXT_MAIN};
}}

QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid {COLOR_BORDER};
    background-color: #FFFFFF;
}}

QRadioButton::indicator:hover {{
    border-color: {COLOR_PRIMARY};
}}

QRadioButton::indicator:checked {{
    border: 1px solid {COLOR_PRIMARY};
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {COLOR_PRIMARY}, stop:0.52 {COLOR_PRIMARY}, stop:0.58 #FFFFFF, stop:1 #FFFFFF);
}}

/* ── Buttons (Strict Hierarchy) ───────────────────────────────────────────── */
/* Base QPushButton: Secondary / Desktop Neutral */
QPushButton {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 500;
    padding: 4px 12px;
    min-height: 28px;
}}

QPushButton:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    border-color: #CBD5E1;
}}

QPushButton:pressed {{
    background-color: {COLOR_SURFACE_PRESSED};
}}

QPushButton:disabled {{
    background-color: {COLOR_SURFACE_SECONDARY};
    border-color: {COLOR_BORDER_SUBTLE};
    color: {COLOR_TEXT_DISABLED};
}}

/* Primary Action Button (The single focal action) */
QPushButton#primaryButton,
QPushButton#startCardMailBtn {{
    background-color: {COLOR_PRIMARY};
    border: 1px solid {COLOR_PRIMARY_HOVER};
    border-radius: {RADIUS_CONTROL};
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 16px;
    min-height: 30px;
}}

QPushButton#primaryButton:hover,
QPushButton#startCardMailBtn:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}

QPushButton#primaryButton:pressed,
QPushButton#startCardMailBtn:pressed {{
    background-color: {COLOR_PRIMARY_PRESSED};
}}

QPushButton#primaryButton:disabled,
QPushButton#startCardMailBtn:disabled {{
    background-color: {COLOR_PRIMARY_DISABLED};
    border-color: {COLOR_PRIMARY_DISABLED};
    color: #F8FAFC;
}}

/* Secondary / Ghost Toolbar Buttons */
QPushButton#secondaryButton,
QPushButton#bindButton {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 500;
    padding: 4px 12px;
    min-height: 28px;
}}

QPushButton#secondaryButton:hover,
QPushButton#bindButton:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    border-color: #CBD5E1;
}}

QPushButton#secondaryButton:pressed,
QPushButton#bindButton:pressed {{
    background-color: {COLOR_SURFACE_PRESSED};
}}

/* State-specific execution buttons */
QPushButton#pauseButton {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_WARNING};
    color: {COLOR_WARNING};
    font-weight: 600;
    min-height: 28px;
}}

QPushButton#pauseButton:hover {{
    background-color: {COLOR_WARNING_BG};
}}

QPushButton#resumeButton {{
    background-color: {COLOR_SUCCESS};
    border: 1px solid #15803D;
    color: #FFFFFF;
    font-weight: 600;
    min-height: 28px;
}}

QPushButton#resumeButton:hover {{
    background-color: #15803D;
}}

QPushButton#stopButton {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_DANGER};
    color: {COLOR_DANGER};
    font-weight: 500;
    min-height: 28px;
}}

QPushButton#stopButton:hover {{
    background-color: {COLOR_DANGER_BG};
}}

QPushButton#stopButton:disabled {{
    background-color: {COLOR_SURFACE_SECONDARY};
    border-color: {COLOR_BORDER_SUBTLE};
    color: {COLOR_TEXT_DISABLED};
}}

/* Compact Utility Buttons (Reset, Toggle, Copy, Clear) */
QPushButton#resetStatusBtn,
QPushButton#debugToggleBtn,
QPushButton#copyLogBtn,
QPushButton#clearLogBtn {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 500;
    padding: 2px 8px;
    min-height: 24px;
}}

QPushButton#resetStatusBtn:hover,
QPushButton#debugToggleBtn:hover,
QPushButton#copyLogBtn:hover,
QPushButton#clearLogBtn:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    color: {COLOR_TEXT_MAIN};
    border-color: #CBD5E1;
}}

/* ── Stepper & Workflow Components ────────────────────────────────────────── */
/* Global status indicator */
QLabel#workflowStatusBadge {{
    background-color: {COLOR_SURFACE_HOVER};
    color: {COLOR_TEXT_SECONDARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 500;
    max-width: 200px;
    qproperty-alignment: AlignCenter;
}}

QLabel#workflowStatusBadge[state="running"] {{
    background-color: #EFF6FF;
    color: {COLOR_PRIMARY};
    border-color: #BFDBFE;
}}

QLabel#workflowStatusBadge[state="success"] {{
    background-color: {COLOR_SUCCESS_BG};
    color: {COLOR_SUCCESS};
    border-color: {COLOR_SUCCESS_BORDER};
}}

QLabel#workflowStatusBadge[state="failed"] {{
    background-color: {COLOR_DANGER_BG};
    color: {COLOR_DANGER};
    border-color: {COLOR_DANGER_BORDER};
}}

/* Step Title / Subtitle */
QLabel.stepTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {COLOR_TEXT_MAIN};
}}

QLabel.stepSubtitle {{
    font-size: 11px;
    color: {COLOR_TEXT_MUTED};
}}

/* Stepper Node Indicator Dot */
QLabel.stepDot {{
    font-size: 12px;
    color: {COLOR_TEXT_DISABLED};
}}
QLabel.stepDot[state="idle"] {{
    color: {COLOR_TEXT_DISABLED};
}}
QLabel.stepDot[state="running"] {{
    color: {COLOR_PRIMARY};
    font-weight: bold;
}}
QLabel.stepDot[state="success"] {{
    color: {COLOR_SUCCESS};
    font-weight: bold;
}}
QLabel.stepDot[state="failed"] {{
    color: {COLOR_DANGER};
    font-weight: bold;
}}

/* Step Action Buttons (Compact Step Triggers) */
QPushButton.stepBtn {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 500;
    padding: 3px 10px;
    min-height: 26px;
}}

QPushButton.stepBtn:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    border-color: #94A3B8;
}}

QPushButton.stepBtn[stepState="idle"] {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_MAIN};
}}

QPushButton.stepBtn[stepState="running"] {{
    background-color: #EFF6FF;
    border: 1px solid {COLOR_PRIMARY};
    color: {COLOR_PRIMARY};
    font-weight: 600;
}}

QPushButton.stepBtn[stepState="success"] {{
    background-color: {COLOR_SUCCESS_BG};
    border: 1px solid {COLOR_SUCCESS_BORDER};
    color: #15803D;
    font-weight: 500;
}}

QPushButton.stepBtn[stepState="failed"] {{
    background-color: {COLOR_DANGER_BG};
    border: 1px solid {COLOR_DANGER_BORDER};
    color: {COLOR_DANGER};
    font-weight: 500;
}}

QPushButton.stepAuxBtn {{
    background-color: transparent;
    border: 1px dashed {COLOR_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    padding: 3px 8px;
    min-height: 26px;
}}

QPushButton.stepAuxBtn:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    border-color: #94A3B8;
    color: {COLOR_TEXT_MAIN};
}}

/* Navigation Sub-step Pills */
QPushButton.subStepBtn {{
    background-color: {COLOR_SURFACE_SECONDARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_TEXT_SECONDARY};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
    min-height: 24px;
    max-height: 24px;
}}

QPushButton.subStepBtn:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    border-color: #94A3B8;
    color: {COLOR_TEXT_MAIN};
}}

QPushButton.subStepBtn[pillState="active"] {{
    background-color: {COLOR_PRIMARY};
    border: 1px solid {COLOR_PRIMARY_HOVER};
    color: #FFFFFF;
    font-weight: 600;
}}

QPushButton.subStepBtn[pillState="done"] {{
    background-color: {COLOR_SUCCESS_BG};
    border: 1px solid {COLOR_SUCCESS_BORDER};
    color: #15803D;
    font-weight: 500;
}}

/* ── Log Console Area ─────────────────────────────────────────────────────── */
QPlainTextEdit#logOutput {{
    background-color: {COLOR_LOG_BG};
    border: 1px solid {COLOR_LOG_BORDER};
    border-radius: {RADIUS_CONTROL};
    color: {COLOR_LOG_TEXT};
    font-family: "Consolas", "Cascadia Mono", "Courier New", monospace;
    font-size: 12px;
    line-height: 1.4;
    padding: 6px;
    selection-background-color: {COLOR_PRIMARY};
}}

/* ── Splitter ─────────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {COLOR_BORDER_SUBTLE};
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QSplitter::handle:horizontal:hover {{
    background-color: #CBD5E1;
}}

/* ── Scrollbars (Slim Desktop Style) ──────────────────────────────────────── */
QScrollBar:vertical {{
    width: 8px;
    background-color: transparent;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: #D1D5DB;
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #9CA3AF;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* Left Scroll Area */
QScrollArea#leftScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea#leftScrollArea > QWidget > QWidget {{
    background: transparent;
}}
"""



