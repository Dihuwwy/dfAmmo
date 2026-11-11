from __future__ import annotations

import json
import logging
import os
import shutil
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
# Deleting a map also removes its cutscenes, and the game then downloads them
# again. Unlike Paks these are optional: any that exist are disabled alongside.
CHANGGONG_EXTRA_FILES = tuple(
    f"DeltaForce/Content/Movies_HD/SeamlessEntry/{name}.bin"
    for name in (
        "Forrest_Intro",
        "Forrest_Outro",
        "SOL_Common_Wildfire_5k",
        "SOL_Forest_Intro_Wildfire_5k",
        "SOL_Forest_Outro_Wildfire_5k",
    )
)
TEMPLATE_RENAMES = {
    "wegame_assets_manage.png": "wegame_resource_manager_menu.png",
    "wegame_assests_manage.png": "wegame_resource_manager_header.png",
    "wegame_confirmdelete.png": "wegame_resource_delete_confirm.png",
    "wegame_delete_map.png": "wegame_changgong_map_card.png",
    "wegame_az3_map.png": "wegame_az3_map_card.png",
    "df_changgong_choose.png": "df_changgong_map_option.png",
    "df_az3_choose.png": "df_az3_map_option.png",
    "df_map_choose_selected.png": "df_changgong_map_selected.png",
    "df_az3_selected.png": "df_az3_map_selected.png",
    "df_changgong_choose_2.png": "df_changgong_download_option.png",
    "df_az3_choose_2.png": "df_az3_map_option.png",
    "df_redownload_panel.png": "df_changgong_download_panel.png",
    "df_az3_redownload_panel.png": "df_az3_download_panel.png",
}


@dataclass(frozen=True)
class AppConfig:
    """Shared runtime configuration."""

    app_name: str = "dfAmmo"
    window_title: str = "dfAmmo Assistant"
    check_updates_on_startup: bool = True
    auto_update: bool = False
    update_channel: str = "stable"
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
    map_id: str = "changgong"
    check_fill_teammates: bool = True
    wegame_more_template: str = "wegame_more.png"
    wegame_assets_manage_template: str = "wegame_resource_manager_menu.png"
    wegame_delete_map_template: str = "wegame_changgong_map_card.png"
    wegame_bin_template: str = "wegame_bin.png"
    wegame_manager_header_template: str = "wegame_resource_manager_header.png"
    wegame_confirm_delete_template: str = "wegame_resource_delete_confirm.png"
    confirm_delete_timeout_seconds: int = 10
    wegame_ready_timeout_seconds: int = 60
    delete_map_timeout_seconds: int = 30
    reconnect_notice_template: str = "df_reconnect_unavailable.png"
    game_confirm_template: str = "df_confirm.png"
    reconnect_notice_threshold: float = 0.90
    reconnect_notice_timeout_seconds: int = 120
    redownload_map_choice_template: str = "df_changgong_download_option.png"
    redownload_map_panel_template: str = "df_changgong_download_panel.png"
    warehouse_notice_template: str = "df_warehouse_notice.png"
    warehouse_notice_threshold: float = 0.90

    @property
    def map_name(self) -> str:
        return "AZ3" if self.map_id == "az3" else "长弓溪谷"

    @property
    def active_pak_names(self) -> tuple[str, ...]:
        if self.map_id == "az3":
            return ("pak-0-2-pakchunk219-WindowsClient.pak",
                    "pak-0-2-pakchunk219optional-WindowsClient.pak")
        return tuple(self.pak_file_names)

    @property
    def active_extra_files(self) -> tuple[str, ...]:
        return () if self.map_id == "az3" else CHANGGONG_EXTRA_FILES

    def map_template(self, name: str) -> str:
        if self.map_id != "az3":
            return name
        return {
            "df_changgong_map_option.png": "df_az3_map_option.png",
            "df_changgong_map_selected.png": "df_az3_map_selected.png",
            self.wegame_delete_map_template: "wegame_az3_map_card.png",
            self.redownload_map_choice_template: "df_az3_map_option.png",
            self.redownload_map_panel_template: "df_az3_download_panel.png",
        }.get(name, name)

    def save_to_file(self, path: Path | None = None, *, overwrite: bool = True) -> None:
        path = path or CONFIG_FILE
        text = json.dumps(asdict(self), ensure_ascii=False, indent=2)
        if not overwrite:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(text)
            return
        # Write beside the target, then swap: a crash mid-save cannot truncate the settings.
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)

    @classmethod
    def load_from_file(cls, path: Path | None = None) -> AppConfig:
        path = path or CONFIG_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()
            for key, value in data.items():
                if key.endswith("_template") and isinstance(value, str):
                    data[key] = TEMPLATE_RENAMES.get(value, value)
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
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
            # Keep the unreadable file: the next save would overwrite it with defaults.
            try:
                shutil.copy2(path, path.with_name(path.stem + ".corrupt.json"))
            except OSError:
                pass
            logging.getLogger(__name__).warning("配置文件无法解析，已使用默认配置并备份原文件：%s", exc)
            return cls()
        except OSError:
            return cls()
