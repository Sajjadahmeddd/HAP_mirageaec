"""PDF page → Unit(+Spaces), streaming one page at a time.

Built against the real HAP v5.2 "Zone Sizing Summary" report layout, where
PyMuPDF's get_text() emits each table cell on its own line:

- One air-system unit per page; pages without the page_signature anchor
  (covers, TOC) are skipped.
- Label-anchored fields ("Air System Name", "Floor Area"): the value is on
  the same line as the label or `offset` lines below it — both occur in the
  same report.
- Sizing values (coil loads, DB/WB, water flow) are a positional row after
  the "Zone N" line inside "Terminal Unit Sizing Data - Cooling"; the table's
  header labels are fragmented across lines and unusable as anchors.
- Space rows in "Space Loads and Airflows" are detected by indentation: the
  space-name cell is the only indented line after the zone row (names may
  start with #, @, or nothing, contain spaces/parentheses, and are
  width-truncated by HAP — the truncated text is carried as-is).
- Time-of-peak cells normally arrive as one line ("Jul 1500"); if a layout
  splits them ("Jul" / "1500") they are re-merged before offsets apply.

All anchors, regexes and offsets come from mapping.json — tune there.
"""

from __future__ import annotations

import re
from typing import Callable, Iterator

import pymupdf

from .config import Config
from .models import Space, Unit

_MONTH_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", re.IGNORECASE
)
_TIME_RE = re.compile(r"^\d{3,4}$")

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]


def _merge_time_of_peak(cells: list[str]) -> list[str]:
    """Merge a split two-line time-of-peak cell ("Jul" / "1500") into one."""
    merged: list[str] = []
    i = 0
    while i < len(cells):
        if (
            i + 1 < len(cells)
            and _MONTH_RE.match(cells[i])
            and _TIME_RE.match(cells[i + 1])
        ):
            merged.append(f"{cells[i]} {cells[i + 1]}")
            i += 2
        else:
            merged.append(cells[i])
            i += 1
    return merged


class _PageParser:
    def __init__(self, config: Config):
        self.config = config
        self._zone_row_re = re.compile(config.space_table.zone_row_regex)
        self._row_res = {
            fname: re.compile(spec.row_regex)
            for fname, spec in config.unit_fields.items()
            if spec.row_regex
        }
        # Lines that are labels/section headers can never be values; guards
        # against reading the next heading when a value is absent.
        self._guard_prefixes = [
            spec.anchor.lower() for spec in config.unit_fields.values() if spec.anchor
        ]
        self._guard_prefixes += [
            spec.section.lower() for spec in config.unit_fields.values() if spec.section
        ]
        self._guard_prefixes += [
            config.space_table.section_anchor.lower(),
            config.space_table.footer_anchor.lower(),
            "terminal unit sizing data",
        ]

    def _is_guard_line(self, line: str) -> bool:
        low = line.strip().lower()
        return any(low.startswith(p) for p in self._guard_prefixes)

    @staticmethod
    def _find(stripped: list[str], prefix: str, start: int = 0) -> int:
        low = prefix.lower()
        for i in range(start, len(stripped)):
            if stripped[i].lower().startswith(low):
                return i
        return -1

    def _value_at(self, stripped: list[str], idx: int) -> str:
        if 0 <= idx < len(stripped) and not self._is_guard_line(stripped[idx]):
            return stripped[idx]
        return ""

    def _anchor_value(self, stripped: list[str], field: str, end: int) -> str:
        spec = self.config.unit_fields[field]
        idx = self._find(stripped[:end], spec.anchor)
        if idx < 0:
            return ""
        if spec.allow_same_line:
            remainder = stripped[idx][len(spec.anchor):].strip(" .:…\t")
            if remainder:
                return remainder
        return self._value_at(stripped, idx + spec.offset)

    def _section_row_value(self, stripped: list[str], field: str) -> str:
        spec = self.config.unit_fields[field]
        sec = self._find(stripped, spec.section)
        if sec < 0:
            return ""
        row_re = self._row_res[field]
        row = next(
            (i for i in range(sec + 1, len(stripped)) if row_re.match(stripped[i])), -1
        )
        if row < 0:
            return ""
        return self._value_at(stripped, row + spec.offset)

    def _unit_value(self, stripped: list[str], field: str, section_end: int) -> str:
        spec = self.config.unit_fields[field]
        if spec.section:
            return self._section_row_value(stripped, field)
        return self._anchor_value(stripped, field, section_end)

    def _parse_spaces(
        self, raw: list[str], stripped: list[str], page_number: int
    ) -> list[Space]:
        table = self.config.space_table
        sec = self._find(stripped, table.section_anchor)
        if sec < 0:
            return []
        footer = self._find(stripped, table.footer_anchor, sec)
        if footer < 0:
            footer = len(stripped)
        zone = next(
            (
                i
                for i in range(sec + 1, footer)
                if self._zone_row_re.match(stripped[i])
            ),
            -1,
        )
        if zone < 0:
            return []

        offsets = table.field_offsets
        spaces: list[Space] = []
        i = zone + 1
        while i < footer:
            if not stripped[i] or raw[i] == raw[i].lstrip():
                i += 1  # blank filler or a non-indented (zone/foreign) line
                continue
            # Indented line == space-name cell. Collect its value cells: the
            # following non-indented lines up to the next name/zone/footer.
            name = stripped[i]
            cells: list[str] = []
            j = i + 1
            while j < footer:
                if not stripped[j]:
                    j += 1
                    continue
                if raw[j] != raw[j].lstrip() or self._zone_row_re.match(stripped[j]):
                    break
                cells.append(stripped[j])
                j += 1
            if table.merge_time_of_peak:
                cells = _merge_time_of_peak(cells)
            values = {
                fname: (cells[off - 1] if off - 1 < len(cells) else "")
                for fname, off in offsets.items()
            }
            spaces.append(
                Space(
                    name=name,
                    floor_area=values.get("floor_area", ""),
                    air_flow=values.get("air_flow", ""),
                    page=page_number,
                )
            )
            i = j
        return spaces

    def parse_page(self, text: str, page_number: int) -> Unit | None:
        raw = [ln.rstrip("\r\n") for ln in text.splitlines()]
        stripped = [ln.strip() for ln in raw]
        if self._find(stripped, self.config.page_signature) < 0:
            return None  # cover page, TOC, or other non-unit page

        section_end = self._find(stripped, self.config.space_table.section_anchor)
        if section_end < 0:
            section_end = len(stripped)

        unit = Unit(page=page_number)
        for field in (
            "name",
            "floor_area",
            "total_coil",
            "sens_coil",
            "coil_entering",
            "coil_leaving",
            "water_flow",
        ):
            setattr(unit, field, self._unit_value(stripped, field, section_end))
        unit.spaces = self._parse_spaces(raw, stripped, page_number)
        return unit


def preflight(pdf_path: str) -> str | None:
    """Detect PDFs that can never convert, before parsing starts.

    Returns "protected" (password/permission locked), "scanned" (image-only,
    no extractable text on any sampled page), or None if the file looks
    parseable.
    """
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            return "protected"
        pages = min(doc.page_count, 10)
        if pages and all(
            not doc.load_page(i).get_text().strip() for i in range(pages)
        ):
            return "scanned"
    return None


def parse(
    pdf_path: str,
    config: Config,
    progress_cb: ProgressCb | None = None,
    cancel_cb: CancelCb | None = None,
) -> Iterator[Unit]:
    """Yield one Unit per unit page, page by page (flat memory on 1000 pages).

    When `cancel_cb` returns True the iteration stops immediately; the
    caller is responsible for treating the resulting unit list as partial.
    """
    page_parser = _PageParser(config)
    with pymupdf.open(pdf_path) as doc:
        total = doc.page_count
        for pno in range(total):
            if cancel_cb and cancel_cb():
                return
            text = doc.load_page(pno).get_text()
            if progress_cb:
                progress_cb(pno + 1, total, f"Parsing page {pno + 1} of {total}")
            unit = page_parser.parse_page(text, pno + 1)
            if unit is not None:
                yield unit
