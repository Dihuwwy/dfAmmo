# Third-Party Notices

The Windows distribution contains unmodified third-party runtime components.
Their licenses remain independent of the application's GPL-3.0-only license.
The build includes installed license files in `licenses/` and exact package
versions and upstream project links in `DEPENDENCIES.json`.

| Component | Upstream source / licensing information |
| --- | --- |
| Python | https://www.python.org/downloads/source/ |
| PySide6 / Shiboken6 | https://code.qt.io/cgit/pyside/pyside-setup.git/ (tag v6.11.2) |
| Qt | https://download.qt.io/archive/qt/6.11/6.11.2/single/ |
| NumPy | https://github.com/numpy/numpy/tree/v1.26.4 |
| OpenCV Python wheel | https://github.com/opencv/opencv-python/tree/4.11.0.86 |
| OpenCV | https://github.com/opencv/opencv/tree/4.11.0 |
| Pillow | https://github.com/python-pillow/Pillow |
| psutil | https://github.com/giampaolo/psutil |
| pywin32 | https://github.com/mhammond/pywin32 |
| PyInstaller bootloader | https://github.com/pyinstaller/pyinstaller |

Qt/PySide are dynamically bundled, not statically linked into the application.
Keep their DLLs and license notices when redistributing. `SOURCE.md` provides
a download link to the exact application source and build requirements lock
corresponding to the executable. Qt/PySide source is available separately from the upstream locations
above, including its license texts. Wheel license notices also cover embedded
third-party components such as numerical libraries and image codecs.

The release is unsigned. Build and startup checks do not establish compatibility
with every Windows version, game update, display configuration or security tool.
