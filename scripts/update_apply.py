from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from scripts.update_service import UpdateService, git_command, is_link, portable_file, safe_relative


def wait_for_exit(pid: int, cancel_path: Path) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        for _ in range(60):
            if cancel_path.exists():
                raise RuntimeError("已取消更新。")
            status = kernel.WaitForSingleObject(handle, 1000)
            if status == 0:
                return
            if status != 258:
                raise ctypes.WinError(ctypes.get_last_error())
        raise RuntimeError("程序未能在 60 秒内退出，已取消文件替换。")
    finally:
        kernel.CloseHandle(handle)


def replace_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if is_link(target) or any(is_link(parent) for parent in target.parents):
        raise ValueError(f"更新目标不能是符号链接：{target}")
    descriptor, temp_name = tempfile.mkstemp(prefix=".dfammo-", dir=target.parent)
    os.close(descriptor)
    try:
        shutil.copy2(source, temp_name)
        os.replace(temp_name, target)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def apply_files(root: Path, payload: Path, backup: Path, portable: bool = True) -> None:
    old_info = json.loads((root / "release_info.json").read_text(encoding="utf-8")) if (root / "release_info.json").is_file() else {}
    incoming = {path.relative_to(payload).as_posix(): path for path in payload.rglob("*") if path.is_file()}
    if any(is_link(path) for path in incoming.values()):
        raise ValueError("更新源不能包含符号链接。")
    if portable:
        if not all(portable_file(name) for name in incoming):
            raise ValueError("更新文件不属于便携程序。")
        previous = set(old_info.get("files", []))
        if not all(portable_file(name) for name in previous):
            raise ValueError("旧版文件清单包含非法路径。")
    else:
        previous = set()
        for name in incoming:
            safe_relative(name)
            if name == "config.json" or name.startswith((".updates/", ".venv/")):
                raise ValueError("源码更新包含个人配置或运行环境。")
    template_hashes = old_info.get("template_hashes", {})
    protected = set()
    import hashlib
    for path in (root / "assets" / "templates").glob("*.png"):
        name = path.relative_to(root).as_posix()
        if name not in template_hashes or hashlib.sha256(path.read_bytes()).hexdigest() != template_hashes[name]:
            protected.add(name.casefold())
    incoming_names = {name.casefold() for name in incoming}
    obsolete = {name for name in previous if name.casefold() not in incoming_names}
    changes = {name for name in set(incoming) | obsolete if name.casefold() not in protected}
    originals = {}
    backup.mkdir()
    # Back up every changed file before replacing any of them.
    for name in sorted(changes):
        target = root / safe_relative(name)
        if is_link(target) or any(is_link(parent) for parent in target.parents):
            raise ValueError("更新目标包含符号链接。")
        originals[name] = target.is_file()
        if target.exists() and not target.is_file():
            raise ValueError(f"更新目标不是普通文件：{name}")
        if originals[name]:
            saved = backup / safe_relative(name)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
    touched = []
    try:
        for name in sorted(changes):
            target = root / safe_relative(name)
            if name in incoming:
                replace_file(incoming[name], target)
            else:
                target.unlink(missing_ok=True)
            touched.append(name)
    except Exception:
        for name in reversed(touched):
            target = root / safe_relative(name)
            if originals[name]:
                replace_file(backup / safe_relative(name), target)
            else:
                target.unlink(missing_ok=True)
        raise


def pause_auto_updates(root: Path, job: Path) -> bool:
    """Older clients must not retry a failed installation on every restart."""
    config_path = root / "config.json"
    try:
        settings = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    if not isinstance(settings, dict) or not settings.get("auto_update"):
        return True
    settings["auto_update"] = False
    try:
        saved = job / "paused-update-config.json"
        saved.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        replace_file(saved, config_path)
        return True
    except OSError:
        return False


def run(plan_path: str) -> int:
    path = Path(plan_path).resolve()
    plan = json.loads(path.read_text(encoding="utf-8"))
    root = Path(plan["root"]).resolve()
    payload = Path(plan["payload"]).resolve()
    if plan.get("format") != 1 or path.parent.parent != root / ".updates" or not payload.is_relative_to(path.parent):
        raise ValueError("更新计划路径不正确。")
    result_path = root / ".updates" / "result.json"
    result = {"ok": False, "version": plan["version"]}
    restart = False
    lock = (root / ".updates" / "install.lock").open("a+b")
    import msvcrt
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        raise RuntimeError("另一个实例正在安装更新，请等待完成。")
    try:
        (path.parent / "ready").touch()
        wait_for_exit(int(plan["parent_pid"]), path.parent / "cancel")
        if (path.parent / "cancel").exists():
            raise RuntimeError("已取消更新。")
        restart = True
        if plan["mode"] == "portable":
            info = json.loads((payload / "release_info.json").read_text(encoding="utf-8"))
            if info["version"] != plan["version"]:
                raise ValueError("待安装版本不一致。")
            apply_files(root, payload, path.parent / "backup")
        elif plan["mode"] == "git":
            service = UpdateService(plan["version"], root=root, frozen=False)
            service.check_source_clean()
            git_command(root, "merge", "--ff-only", plan["commit"])
        elif plan["mode"] == "clone":
            if (root / ".git").exists():
                raise RuntimeError("安装目录出现了 Git 仓库，已取消覆盖。")
            apply_files(root, payload, path.parent / "backup", portable=False)
        else:
            raise ValueError("未知更新类型。")
        if plan["mode"] != "portable" and plan["uv"]:
            subprocess.run([plan["uv"], "sync", "--frozen"], cwd=root, capture_output=True,
                           check=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result["ok"] = True
        (path.parent / "done").touch()
    except Exception as exc:
        result["message"] = str(exc)
        if restart:
            restart = pause_auto_updates(root, path.parent)
            result["message"] += "；自动更新已暂停，请在“关于”中手动重试。" if restart else "；请手动启动程序并检查更新日志。"
    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    lock.close()
    if restart:
        command = ([str(root / "dfAmmo.exe")] if plan["mode"] == "portable"
                   else [plan["python"], str(root / "main.py")])
        subprocess.Popen([*command, *plan.get("restart_args", [])], cwd=root,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0 if result["ok"] else 1
