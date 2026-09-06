import ctypes

from scripts.dpi import enable_dpi_awareness
from scripts.privileges import hide_console_window, is_elevated, relaunch_as_admin


def main() -> int:
    enable_dpi_awareness()

    if not is_elevated():
        if relaunch_as_admin():
            return 0

        ctypes.windll.user32.MessageBoxW(
            None,
            "需要管理员权限才能向 WeGame 发送鼠标输入。",
            "dfAmmo Assistant",
            0x10,
        )
        return 1

    hide_console_window()

    from scripts.app import App

    app = App()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
