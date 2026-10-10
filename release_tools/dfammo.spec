from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["airtest", "paddleocr", "paddle", "poco", "scipy", "matplotlib",
              "IPython", "tkinter", "pytest", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="dfAmmo",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    # The application requests UAC itself; the non-interactive self-test needs no elevation.
    uac_admin=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="dfAmmo")
