"""Recent-projects persistence: a small JSON list in %APPDATA%/MAEC.

Pure Python (no Qt) so it is unit-testable without a window.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

MAX_ENTRIES = 25


@dataclass
class RecentEntry:
    pdf_path: str
    output_path: str = ""
    status: str = ""       # "completed" | "failed"
    units: int = 0
    spaces: int = 0
    timestamp: str = ""    # ISO 8601


def default_store_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MAEC" / "recent_projects.json"


class RecentStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_store_path()
        self.entries: list[RecentEntry] = self._load()

    def _load(self) -> list[RecentEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [RecentEntry(**e) for e in data if isinstance(e, dict) and "pdf_path" in e]
        except (OSError, ValueError, TypeError):
            return []  # missing or corrupt store -> start fresh

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([asdict(e) for e in self.entries], indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # persistence is best-effort; never break the app over it

    def add(self, entry: RecentEntry) -> None:
        if not entry.timestamp:
            entry.timestamp = datetime.now().isoformat(timespec="seconds")
        # one entry per PDF path: newest wins, moves to the top
        self.entries = [e for e in self.entries if e.pdf_path != entry.pdf_path]
        self.entries.insert(0, entry)
        del self.entries[MAX_ENTRIES:]
        self._save()

    def remove(self, pdf_path: str) -> None:
        self.entries = [e for e in self.entries if e.pdf_path != pdf_path]
        self._save()

    def top(self, n: int = 5) -> list[RecentEntry]:
        return self.entries[:n]
