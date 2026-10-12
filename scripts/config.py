from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


PROJECT_ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parent.parent)
TEMPLATE_DIR = PROJECT_ROOT / "assets" / "templates"
APP_ICON_PATH = PROJECT_ROOT / "assets" / "app-icon.ico"
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
    check_updates_on_startup: bool = True
    auto_update: bool = False
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
    reconnect_notice_template: str = "df_reconnect_unavailable.png"
    game_confirm_template: str = "df_confirm.png"
    reconnect_notice_threshold: float = 0.90
    reconnect_notice_timeout_seconds: int = 120
    redownload_map_choice_template: str = "df_changgong_choose_2.png"
    redownload_map_panel_template: str = "df_redownload_panel.png"
    redownload_map_button_template: str = "df_redownload_button.png"
    warehouse_notice_template: str = "df_warehouse_notice.png"
    warehouse_notice_threshold: float = 0.90

    def save_to_file(self, path: Path | None = None, *, overwrite: bool = True) -> None:
        path = path or CONFIG_FILE
        data = asdict(self)
        with path.open("w" if overwrite else "x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, path: Path | None = None) -> AppConfig:
        path = path or CONFIG_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except FileNotFoundError:
            config = cls()
            try:
                config.save_to_file(path, overwrite=False)
            except FileExistsError:
                # Another instance may have created user settings while we were loading.
                return cls.load_from_file(path)
            except OSError as exc:
                logging.getLogger(__name__).warning("无法创建默认配置 %s，使用内存默认配置：%s", path, exc)
            return config
        except (json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
            return cls()
