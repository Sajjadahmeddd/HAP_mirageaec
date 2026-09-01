"""Project persistence: one JSON file per sizing session, plus a small
recent-projects index. No database — the same shape module 1 uses for its
recent-projects list.

A project holds what cannot be recomputed: which schedule was loaded, what
diffuser type and inputs the engineer chose for each subspace, which result
columns are visible, and the project metadata. Sizing results themselves are
recomputed on load, so a catalogue correction reaches old projects.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .models import SizingInput

MAX_RECENT = 25
_INDEX_NAME = "recent_projects.json"


def default_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MAEC" / "airsizer"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Project:
    name: str = ""
    source_path: str = ""
    created: str = ""
    updated: str = ""
    # keyed by the schedule row number: {"diffuser": key, "values": {...}}
    sizings: dict[str, dict] = field(default_factory=dict)
    visible_columns: list[str] = field(default_factory=list)
    path: Path | None = None

    def sizing_for(self, row: int) -> SizingInput | None:
        entry = self.sizings.get(str(row))
        if not entry:
            return None
        return SizingInput(
            diffuser=str(entry.get("diffuser", "")),
            values={str(k): str(v) for k, v in entry.get("values", {}).items()},
        )

    def set_sizing(self, row: int, sizing_input: SizingInput) -> None:
        self.sizings[str(row)] = {
            "diffuser": sizing_input.diffuser,
            "values": dict(sizing_input.values),
        }

    def clear_sizing(self, row: int) -> None:
        self.sizings.pop(str(row), None)

    @property
    def sized_count(self) -> int:
        return len(self.sizings)


def save(project: Project, path: str | Path) -> Path:
    """Write the project JSON. Recording it in the recent-projects index is
    the caller's call (`RecentProjects.add`), so saving stays side-effect free."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    project.created = project.created or _now()
    project.updated = _now()
    project.name = project.name or path.stem
    payload = asdict(project)
    payload.pop("path", None)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    project.path = path
    return path


def load(path: str | Path) -> Project:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    project = Project(
        name=str(data.get("name", path.stem)),
        source_path=str(data.get("source_path", "")),
        created=str(data.get("created", "")),
        updated=str(data.get("updated", "")),
        sizings={str(k): dict(v) for k, v in data.get("sizings", {}).items()},
        visible_columns=[str(c) for c in data.get("visible_columns", [])],
        path=path,
    )
    return project


@dataclass
class RecentEntry:
    path: str
    name: str = ""
    source_path: str = ""
    sized: int = 0
    updated: str = ""


class RecentProjects:
    """The home screen's Recent Projects list. Best-effort: never fatal."""

    def __init__(self, index_path: Path | None = None):
        self.path = Path(index_path) if index_path else default_dir() / _INDEX_NAME
        self.entries: list[RecentEntry] = self._load()

    def _load(self) -> list[RecentEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [RecentEntry(**e) for e in data if isinstance(e, dict) and "path" in e]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([asdict(e) for e in self.entries], indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def add(self, project: Project) -> None:
        if project.path is None:
            return
        entry = RecentEntry(
            path=str(project.path),
            name=project.name,
            source_path=project.source_path,
            sized=project.sized_count,
            updated=project.updated or _now(),
        )
        self.entries = [e for e in self.entries if e.path != entry.path]
        self.entries.insert(0, entry)
        del self.entries[MAX_RECENT:]
        self._save()

    def remove(self, path: str) -> None:
        self.entries = [e for e in self.entries if e.path != path]
        self._save()

    def top(self, n: int = 5) -> list[RecentEntry]:
        return self.entries[:n]
