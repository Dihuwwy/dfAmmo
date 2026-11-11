from pathlib import Path
import re

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    # The Qt Quick interface is loaded from files next to scripts/gui.py.
    datas=[(str(root / "scripts" / "qml"), "scripts/qml")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["airtest", "paddleocr", "paddle", "poco", "scipy", "matplotlib",
              "IPython", "tkinter", "pytest", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
# PyInstaller collects every Qt Quick module. The interface uses the Basic
# controls on Direct3D only, so drop the other styles, unused QML modules,
# the QML debugger and the software OpenGL renderer.
unused = re.compile(
    r"PySide6/(?:"
    r"opengl32sw\.dll"
    r"|Qt6QuickControls2(?:Imagine|Material|Universal|Fusion|FluentWinUI3|Windows)\w*\.dll"
    r"|Qt6(?:QuickDialogs2\w*|QuickParticles|QuickTimeline\w*|QuickVectorImage\w*|QuickTest|Test|Sql"
    r"|QmlLocalStorage|QmlXmlListModel|QuickShapesDesignHelpers|Labs\w+)\.dll"
    r"|qml/QtQuick/Controls/(?:FluentWinUI3|Windows|Material|Fusion|Universal|Imagine|designer)/"
    r"|qml/QtQuick/(?:VirtualKeyboard|NativeStyle|Dialogs|Particles|Timeline|VectorImage|LocalStorage|tooling)/"
    r"|qml/(?:Qt/labs|QtTest)/"
    r"|plugins/qmltooling/"
    # Interface text is written in Chinese already; only ICO and the built-in PNG are loaded.
    r"|translations/"
    r"|plugins/imageformats/q(?!ico)\w+\.dll"
    r")"
    # OpenCV loads FFmpeg only for video; Pillow is used for screen grabs and PNG alone.
    r"|cv2/opencv_videoio_ffmpeg\w*\.dll"
    r"|PIL/_(?:avif|webp|imagingcms|imagingtk)\.",
    re.IGNORECASE,
)
a.binaries = [entry for entry in a.binaries if not unused.search(entry[0].replace("\\", "/"))]
a.datas = [entry for entry in a.datas if not unused.search(entry[0].replace("\\", "/"))]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="dfAmmo",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "app-icon.ico"),
    # The application requests UAC itself; the non-interactive self-test needs no elevation.
    uac_admin=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="dfAmmo")
