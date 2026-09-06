from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class GameProcess:
    """A detected Delta Force game process."""

    process_id: int
    name: str
    executable: str = ""
    create_time: float = 0.0


class GameProcessFinder:
    """Find the running Delta Force client process."""

    def __init__(self, process_names: tuple[str, ...]) -> None:
        self.process_names = {name.casefold() for name in process_names}

    def find(self) -> GameProcess | None:
        matches: list[GameProcess] = []
        for process in psutil.process_iter(("pid", "name", "exe", "create_time")):
            try:
                name = process.info.get("name") or ""
                if name.casefold() not in self.process_names:
                    continue

                matches.append(
                    GameProcess(
                        process_id=process.info["pid"],
                        name=name,
                        executable=process.info.get("exe") or "",
                        create_time=process.info.get("create_time") or 0.0,
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue

        if not matches:
            return None
        return max(matches, key=lambda item: item.create_time)
