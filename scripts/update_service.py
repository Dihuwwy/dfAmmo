from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from urllib import error, parse, request
import zipfile

from scripts.config import PROJECT_ROOT


REPOSITORY = "Dihuwwy/dfAmmo"
REPO_URL = f"https://github.com/{REPOSITORY}"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_UNPACKED = 1536 * 1024 * 1024


class UpdateCancelled(Exception):
    pass


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"不支持的正式版本号：{version}")
    return tuple(map(int, match.groups()))


class GitHubRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = parse.urlparse(newurl)
        if url.scheme != "https" or not (
            url.hostname in ("github.com", "api.github.com")
            or (url.hostname or "").endswith(".githubusercontent.com")
        ):
            raise ValueError("更新下载跳转到了非 GitHub 地址。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class Release:
    tag: str
    version: str
    archive_name: str
    checksum_name: str
    digest: str = ""


def safe_relative(name: str) -> Path:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"更新包包含非法路径：{name}")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    for part in path.parts:
        if ":" in part or part.endswith((".", " ")) or part.split(".")[0].upper() in reserved:
            raise ValueError(f"更新包包含非法文件名：{name}")
    return Path(*path.parts)


def portable_file(name: str) -> bool:
    safe_relative(name)
    return (name in {"dfAmmo.exe", "release_info.json", "README.md", "LICENSE", "NOTICE",
                     "THIRD_PARTY_NOTICES.md", "SOURCE.md", "DEPENDENCIES.json", "assets/app-icon.ico"}
            or name.startswith(("_internal/", "licenses/", "assets/templates/")))


def is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def git_command(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Git 更新失败。")
    return result.stdout.strip()


class UpdateService:
    def __init__(self, version: str, root: Path = PROJECT_ROOT, frozen: bool | None = None,
                 report=None, cancelled: threading.Event | None = None):
        self.version = version
        self.root = root.resolve()
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self.report = report or (lambda message: None)
        self.cancelled = cancelled or threading.Event()
        self.opener = request.build_opener(GitHubRedirect())

    def check_cancelled(self):
        if self.cancelled.is_set():
            raise UpdateCancelled("已取消更新。")

    def open_url(self, url: str):
        self.check_cancelled()
        req = request.Request(url, headers={"User-Agent": f"dfAmmo/{self.version}",
                              "Accept": "application/vnd.github+json" if url == LATEST_URL else "*/*"})
        return self.opener.open(req, timeout=15)

    def check_latest(self) -> Release | None:
        cache = self.root / ".updates"
        if cache.is_dir() and not is_link(cache):
            for job in cache.glob("job-*"):
                marker = job / "done"
                if (job.is_dir() and not is_link(job) and job.resolve().parent == cache.resolve()
                        and marker.is_file() and time.time() - marker.stat().st_mtime > 60):
                    try:
                        shutil.rmtree(job)
                    except OSError:
                        if job.is_dir():
                            marker.touch(exist_ok=True)
        try:
            with self.open_url(LATEST_URL) as response:
                payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise ValueError("GitHub 版本信息过大。")
            data = json.loads(payload)
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code in (403, 429):
                self.report("GitHub API 请求受限，正在通过官方 Release 页面检查版本。")
                return self.check_latest_redirect()
            raise
        except error.URLError:
            self.report("版本接口连接失败，正在通过官方 Release 页面检查版本。")
            return self.check_latest_redirect()
        self.check_cancelled()
        tag = data["tag_name"]
        if data.get("draft") or data.get("prerelease"):
            return None
        if version_tuple(tag) <= version_tuple(self.version):
            return None
        version = tag.removeprefix("v")
        stem = f"dfAmmo-v{version}-windows-x64"
        assets = {asset["name"]: asset for asset in data.get("assets", []) if asset.get("state") == "uploaded"}
        archive = assets.get(stem + ".zip")
        if self.frozen and (not archive or stem + ".sha256" not in assets):
            raise RuntimeError("新版 Windows 安装包尚未上传完整，请稍后再试。")
        digest = (archive or {}).get("digest") or ""
        return Release(tag, version, stem + ".zip", stem + ".sha256", digest)

    def check_latest_redirect(self) -> Release | None:
        try:
            with self.open_url(REPO_URL + "/releases/latest") as response:
                url = parse.urlparse(response.geturl())
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        prefix = f"/{REPOSITORY}/releases/tag/"
        if url.hostname != "github.com" or not url.path.startswith(prefix):
            raise ValueError("GitHub 最新版本跳转地址不正确。")
        tag = url.path[len(prefix):]
        if version_tuple(tag) <= version_tuple(self.version):
            return None
        version = tag.removeprefix("v")
        stem = f"dfAmmo-v{version}-windows-x64"
        if self.frozen:
            try:
                with self.open_url(f"{REPO_URL}/releases/download/{tag}/{stem}.sha256") as response:
                    checksum = response.read(4097).decode("ascii").strip().split()
                if len(checksum) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum[0]) or checksum[1].lstrip("*") != stem + ".zip":
                    raise ValueError("新版 SHA-256 校验文件格式不正确。")
            except error.HTTPError as exc:
                if exc.code == 404:
                    raise RuntimeError("新版 Windows 安装包尚未上传完整，请稍后再试。") from exc
                raise
        return Release(tag, version, stem + ".zip", stem + ".sha256")

    def download(self, release: Release, job: Path) -> Path:
        base = f"{REPO_URL}/releases/download/{release.tag}/"
        with self.open_url(base + release.checksum_name) as response:
            checksum_text = response.read(4097).decode("ascii")
        parts = checksum_text.strip().split()
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) or parts[1].lstrip("*") != release.archive_name:
            raise ValueError("新版 SHA-256 校验文件格式不正确。")
        expected = parts[0].lower()
        if release.digest and release.digest != "sha256:" + expected:
            raise ValueError("GitHub 资产摘要与校验文件不一致。")
        archive = job / release.archive_name
        digest = hashlib.sha256()
        received = 0
        last_report = -1
        with self.open_url(base + release.archive_name) as response, archive.open("wb") as stream:
            total = int(response.headers.get("Content-Length", 0))
            if total > MAX_DOWNLOAD:
                raise ValueError("更新包超出下载大小限制。")
            while True:
                self.check_cancelled()
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_DOWNLOAD:
                    raise ValueError("更新包超出下载大小限制。")
                stream.write(chunk)
                digest.update(chunk)
                progress = (received * 100 // total // 10 * 10) if total else received // (10 * 1024 * 1024)
                if progress != last_report:
                    last_report = progress
                    self.report(f"更新下载：{min(progress, 100)}%" if total else f"更新已下载 {received // 1024**2} MB")
        self.check_cancelled()
        if digest.hexdigest() != expected:
            raise ValueError("更新包 SHA-256 校验失败，请重新下载。")
        self.report("更新包校验通过，正在解压。")
        return archive

    def unpack(self, archive: Path, job: Path, release: Release) -> Path:
        target = job / "payload"
        target.mkdir()
        names = set()
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if sum(entry.file_size for entry in entries) > MAX_UNPACKED or len(entries) > 10000:
                raise ValueError("更新包解压大小异常。")
            for entry in entries:
                self.check_cancelled()
                relative = safe_relative(entry.filename)
                if not relative.parts or relative.parts[0] != "dfAmmo":
                    raise ValueError("更新包目录结构不正确。")
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError("更新包不能包含符号链接。")
                if entry.is_dir():
                    continue
                name = PurePosixPath(*relative.parts[1:]).as_posix()
                if not portable_file(name) or name.casefold() in names:
                    raise ValueError(f"更新包包含重复或非程序文件：{name}")
                names.add(name.casefold())
                output = target / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, output.open("wb") as dest:
                    shutil.copyfileobj(source, dest, 256 * 1024)
        payload = target / "dfAmmo"
        info = json.loads((payload / "release_info.json").read_text(encoding="utf-8"))
        if info.get("version") != release.version or not (payload / "dfAmmo.exe").is_file():
            raise ValueError("更新包版本或程序文件不正确。")
        return payload

    def prepare(self, release: Release) -> Path:
        self.check_cancelled()
        cache = self.root / ".updates"
        if is_link(cache):
            raise ValueError("更新目录不能是符号链接。")
        cache.mkdir(exist_ok=True)
        job = Path(tempfile.mkdtemp(prefix="job-", dir=cache))
        try:
            if self.frozen:
                payload = self.unpack(self.download(release, job), job, release)
                mode = "portable"
                commit = ""
            else:
                if not shutil.which("git"):
                    raise RuntimeError("源码更新需要安装 Git。")
                mode = "git" if (self.root / ".git").exists() else "clone"
                if mode == "git":
                    self.check_source_clean()
                payload = job / "source"
                self.report(f"正在克隆 {release.tag} 源码。")
                subprocess.run(["git", "clone", "--depth=1", "--single-branch", "--branch", release.tag,
                                REPO_URL + ".git", str(payload)], check=True, capture_output=True,
                               timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.check_cancelled()
                version = tomllib.loads((payload / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
                if version != release.version or not (payload / "scripts" / "update_apply.py").is_file():
                    raise ValueError("新版源码的版本或更新模块不正确。")
                commit = git_command(payload, "rev-parse", "HEAD")
                if mode == "git":
                    git_command(self.root, "fetch", "--no-tags", REPO_URL + ".git",
                                f"refs/tags/{release.tag}:refs/dfammo-updates/{release.tag}")
                    if git_command(self.root, "rev-parse", f"refs/dfammo-updates/{release.tag}^{{commit}}") != commit:
                        raise ValueError("源码标签在下载期间发生变化，请重新检查更新。")
                    try:
                        git_command(self.root, "merge-base", "--is-ancestor", "HEAD", commit)
                    except RuntimeError as exc:
                        raise RuntimeError("本地提交无法快进到新版，已保留本地源码，请手动合并后再更新。") from exc
            self.check_cancelled()
            plan = {"format": 1, "mode": mode, "root": str(self.root), "payload": str(payload),
                    "version": release.version, "commit": commit, "parent_pid": os.getpid(),
                    "python": sys.executable, "uv": shutil.which("uv") or "", "restart_args": sys.argv[1:]}
            path = job / "plan.json"
            path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            return path
        except Exception:
            shutil.rmtree(job)
            raise

    def check_source_clean(self):
        if Path(git_command(self.root, "rev-parse", "--show-toplevel")).resolve() != self.root:
            raise RuntimeError("当前目录不是源码仓库根目录。")
        if git_command(self.root, "status", "--porcelain", "--untracked-files=no"):
            raise RuntimeError("源码有本地修改，已保留这些修改。请提交或处理后再更新。")

    def launch_helper(self, plan_path: Path):
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        payload = Path(plan["payload"])
        command = ([str(payload / "dfAmmo.exe")] if plan["mode"] == "portable"
                   else [plan["python"], str(payload / "main.py")])
        process = subprocess.Popen([*command, "--apply-update", str(plan_path)], cwd=payload,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 20
        while not (plan_path.parent / "ready").is_file():
            self.check_cancelled()
            if process.poll() is not None:
                raise RuntimeError("更新助手启动失败，程序继续运行。")
            if time.monotonic() >= deadline:
                (plan_path.parent / "cancel").touch()
                raise RuntimeError("更新助手启动超时，程序继续运行。")
            time.sleep(0.1)
