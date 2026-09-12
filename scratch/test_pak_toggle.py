import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, r"c:\Users\48563\Documents\Coding\PycharmProjects\dfAmmo")

from PySide6.QtWidgets import QApplication
from scripts.workflow import Workflow
from scripts.config import AppConfig
from scripts.gui import MainWindow

app = QApplication(sys.argv)

with tempfile.TemporaryDirectory() as temp_dir:
    paks_dir = Path(temp_dir) / "DeltaForce" / "PackContent" / "Paks"
    paks_dir.mkdir(parents=True, exist_ok=True)

    test_files = [
        "pak-0-2-pakchunk90-WindowsClient.pak",
        "pak-0-2-pakchunk90optional-WindowsClient.pak",
    ]

    # Create normal pak files
    for name in test_files:
        (paks_dir / name).write_text("dummy pak content")

    workflow = Workflow()

    # Step 1: Initial check
    status1 = workflow.get_pak_status(temp_dir, test_files)
    print(f"Status 1 (init): {status1}")
    assert status1 == "normal", f"Expected normal, got {status1}"

    # Step 2: Toggle (first click -> rename to disabled)
    action1, results1 = workflow.toggle_pak_files(temp_dir, test_files)
    print(f"Action 1: {action1}, Results: {results1}")
    assert action1 == "disabled"
    for name in test_files:
        assert not (paks_dir / name).exists(), f"{name} should not exist"
        assert (paks_dir / f"{name}.disabled").exists(), f"{name}.disabled should exist"

    status2 = workflow.get_pak_status(temp_dir, test_files)
    print(f"Status 2 (after disabled): {status2}")
    assert status2 == "disabled"

    # Step 3: Toggle again (second click -> restore to normal)
    action2, results2 = workflow.toggle_pak_files(temp_dir, test_files)
    print(f"Action 2: {action2}, Results: {results2}")
    assert action2 == "restored"
    for name in test_files:
        assert (paks_dir / name).exists(), f"{name} should exist"
        assert not (paks_dir / f"{name}.disabled").exists(), f"{name}.disabled should not exist"

    status3 = workflow.get_pak_status(temp_dir, test_files)
    print(f"Status 3 (after restore): {status3}")
    assert status3 == "normal"

    # Step 4: Test GUI button text updates
    from dataclasses import replace
    cfg = AppConfig.load_from_file()
    cfg = replace(cfg, game_install_dir=temp_dir)
    win = MainWindow(cfg)
    
    # In normal state:
    win._sync_pak_button_state()
    assert "屏蔽 Pak" in win.dbg_rename_pak_btn.text()

    # Trigger click 1 via GUI method:
    win._dbg_rename_pak()
    assert "恢复 Pak" in win.dbg_rename_pak_btn.text()
    assert (paks_dir / f"{test_files[0]}.disabled").exists()

    # Trigger click 2 via GUI method:
    win._dbg_rename_pak()
    assert "屏蔽 Pak" in win.dbg_rename_pak_btn.text()
    assert (paks_dir / test_files[0]).exists()

    print("ALL TESTS PASSED SUCCESSFULLY!")
