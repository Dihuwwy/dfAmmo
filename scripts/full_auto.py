from __future__ import annotations


def apply_custom_loadout(workflow, config) -> None:
    """Full-auto step 4: equip the configured custom loadout."""
    workflow.control.check()
    raise NotImplementedError("全自动步骤“自定义配装”尚未实现。")


def wait_for_map_recovery(workflow, config) -> None:
    """Full-auto step 5: wait until the target map finishes downloading/verifying."""
    workflow.control.check()
    raise NotImplementedError("全自动步骤“等待地图恢复”尚未实现。")


def switch_mode_and_reconnect(workflow, config) -> None:
    """Full-auto step 6: switch game mode and reconnect to the active match."""
    workflow.control.check()
    raise NotImplementedError("全自动步骤“切换模式重连”尚未实现。")


def suicide_and_exit_match(workflow, config) -> None:
    """Full-auto step 7: eliminate self in-match and return to lobby."""
    workflow.control.check()
    raise NotImplementedError("全自动步骤“游戏内自杀并退出”尚未实现。")
