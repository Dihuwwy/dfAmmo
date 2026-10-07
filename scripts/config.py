from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "assets" / "templates"
CONFIG_FILE = PROJECT_ROOT / "config.json"
DEFAULT_PAK_NAMES = (
    "pak-0-2-pakchunk90-WindowsClient.pak",
    "pak-0-2-pakchunk90optional-WindowsClient.pak",
)


@dataclass(frozen=True)
class AppConfig:
    """Shared runtime configuration."""

    app_name: str = "dfAmmo"
    window_title: str = "dfAmmo Assistant"
    start_button_templates: tuple[str, ...] = (
        "wegame_start_button.png",
        "wegame_start_deltaforce.png",
        "start_button.png",
    )
    template_match_threshold: float = 0.78
    game_process_names: tuple[str, ...] = (
        "DeltaForceClient-Win64-Shipping.exe",
        "DeltaForceClient.exe",
    )
    game_process_poll_interval_ms: int = 1000
    game_process_timeout_seconds: int = 120
    navigation_poll_interval_ms: int = 700
    navigation_step_timeout_seconds: int = 60
    game_window_timeout_seconds: int = 90
    game_install_dir: str = ""
    pak_file_names: tuple[str, ...] = DEFAULT_PAK_NAMES
    operation_mode: str = "semi_auto"
    wegame_more_template: str = "wegame_more.png"
    wegame_assets_manage_template: str = "wegame_assets_manage.png"
    wegame_delete_map_template: str = "wegame_delete_map.png"
    wegame_bin_template: str = "wegame_bin.png"
    wegame_manager_header_template: str = "wegame_assests_manage.png"
    wegame_confirm_delete_template: str = "wegame_confirmdelete.png"
    confirm_delete_timeout_seconds: int = 10
    wegame_ready_timeout_seconds: int = 60
    delete_map_timeout_seconds: int = 30

    def save_to_file(self, path: Path | None = None) -> None:
        path = path or CONFIG_FILE
        data = asdict(self)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path | None = None) -> AppConfig:
        path = path or CONFIG_FILE
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
            return cls()
