"""What a rebadging run takes in and reports back.

Plain dataclasses, no PDF library types: the routers serialise these straight
to JSON and the UI renders them, so nothing here may depend on PyMuPDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The six values an engineer supplies, applied to every sheet in the batch —
# that is what rebadging a submission set means.
INPUT_FIELDS = (
    ("project_stage", "Project Stage"),
    ("sheet_status", "Sheet Status"),
    ("rev", "Rev"),
    ("description", "Description"),
    ("date", "Date"),
    ("approved_by", "Approved By"),
)

# The four columns of the revision-history table, in sheet order.
HISTORY_COLUMNS = ("rev", "description", "date", "approved_by")


@dataclass(frozen=True)
class RebadgeInputs:
    project_stage: str
    sheet_status: str
    rev: str
    description: str
    date: str
    approved_by: str

    def missing(self) -> list[str]:
        """Labels of any blank field. All six are required."""
        return [label for key, label in INPUT_FIELDS
                if not str(getattr(self, key, "")).strip()]

    @classmethod
    def from_dict(cls, data: dict) -> "RebadgeInputs":
        return cls(**{key: str(data.get(key, "") or "").strip()
                      for key, _ in INPUT_FIELDS})


@dataclass
class HistoryRow:
    """One row of the revision table as it stands on the sheet."""
    rev: str = ""
    description: str = ""
    date: str = ""
    approved_by: str = ""

    def filled(self) -> bool:
        return any(v.strip() for v in
                   (self.rev, self.description, self.date, self.approved_by))


@dataclass
class SheetCheck:
    """What validation found, before anything is edited."""
    filename: str
    ok: bool
    rotation: int = 0
    labels_found: dict[str, bool] = field(default_factory=dict)
    current: dict = field(default_factory=dict)   # stage/status/rev/history_rows
    blank_row_available: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def missing_labels(self) -> list[str]:
        return [name for name, found in self.labels_found.items() if not found]


@dataclass
class SheetResult:
    """What happened to one sheet during apply."""
    filename: str
    ok: bool
    previous_rev: str = ""
    new_rev: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    sheets: list[SheetResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for s in self.sheets if s.ok)

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.sheets if not s.ok)

    @property
    def warning_count(self) -> int:
        return sum(len(s.warnings) for s in self.sheets)
