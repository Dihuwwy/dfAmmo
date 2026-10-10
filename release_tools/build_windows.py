from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parent.parent


def collect_notices(output: Path) -> None:
    license_root = output / "licenses"
    license_root.mkdir(exist_ok=True)
    distributions = []
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name, version = dist.metadata["Name"], dist.version
        distributions.append({"name": name, "version": version,
                              "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                              "project_urls": dist.metadata.get_all("Project-URL") or []})
        for entry in dist.files or ():
            lower = str(entry).lower()
            if (any(word in entry.name.upper() for word in ("LICENSE", "COPYING", "NOTICE"))
                    or "/licenses/" in lower) and ".." not in entry.parts:
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = license_root / f"{name}-{version}" / str(entry)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError(f"Python license missing: {python_license}")
    shutil.copy2(python_license, license_root / "Python-LICENSE.txt")
    (output / "DEPENDENCIES.json").write_text(json.dumps(distributions, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Build requires Windows x64 and an x64 Python interpreter")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if args.version and args.version.removeprefix("v") != version:
        parser.error(f"Tag/version mismatch: {args.version} != {version}")
    dist = ROOT / "dist"
    # Do not let DLLs from unrelated applications on PATH leak into the bundle.
    build_env = os.environ.copy()
    windows = Path(os.environ["SystemRoot"])
    build_env["PATH"] = os.pathsep.join(map(str, (Path(sys.executable).parent,
                                                   Path(sys.base_prefix), windows / "System32", windows)))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(dist), "--workpath", str(ROOT / "build"),
                    str(ROOT / "release_tools" / "dfammo.spec")], cwd=ROOT, env=build_env, check=True)
    output = dist / "dfAmmo"
    shutil.copytree(ROOT / "assets" / "templates", output / "assets" / "templates", dirs_exist_ok=True)
    shutil.copy2(ROOT / "assets" / "app-icon.ico", output / "assets" / "app-icon.ico")
    for name in ("README.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, output / name)
    collect_notices(output)
    source_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   capture_output=True, text=True, check=True).stdout.strip()
    source_url = f"https://github.com/Dihuwwy/dfAmmo/archive/{source_commit}.zip"
    (output / "SOURCE.md").write_text(
        f"# Corresponding Source\n\nApplication version: {version}\n\n"
        f"Commit: {source_commit}\n\n[Download the corresponding source]({source_url})\n\n"
        "The application is licensed under GPL-3.0-only. Source is available separately, "
        "not embedded in the portable ZIP. See LICENSE and THIRD_PARTY_NOTICES.md.\n\n"
        "To rebuild on Windows x64 with Python 3.11, create a fresh virtual environment, "
        "install release_tools/build-requirements.lock using "
        "`python -m pip install --require-hashes -r release_tools/build-requirements.lock`, "
        "then run `python release_tools/build_windows.py` from a Git checkout.\n",
        encoding="utf-8")
    subprocess.run([str(output / "dfAmmo.exe"), "--self-test", str(dist / "smoke-test.json")],
                   cwd=dist, env=build_env, check=True, timeout=90)
    report = json.loads((dist / "smoke-test.json").read_text(encoding="utf-8"))
    if not report.get("ok") or not report.get("frozen"):
        raise RuntimeError(f"Frozen startup check failed: {report}")
    if (output / "config.json").exists():
        raise RuntimeError("Personal config must not be included in the release")
    files = sorted(path for path in output.rglob("*") if path.is_file())
    if (output / "dfAmmo-source.zip").exists() or (output / "scripts").exists():
        raise RuntimeError("Application source must not be embedded in the portable release")
    stem = f"dfAmmo-v{version}-windows-x64"
    archive = dist / f"{stem}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(dist).as_posix())
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    (dist / f"{stem}.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    stats = {"version": version, "source_commit": source_commit, "archive": archive.name, "zip_bytes": archive.stat().st_size,
             "unpacked_bytes": sum(path.stat().st_size for path in files), "sha256": checksum}
    (dist / "build-report.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
