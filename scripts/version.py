from __future__ import annotations

import json
import sys
import tomllib

from scripts.config import PROJECT_ROOT


def current_version() -> str:
    if getattr(sys, "frozen", False):
        return json.loads((PROJECT_ROOT / "release_info.json").read_text(encoding="utf-8"))["version"]
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
