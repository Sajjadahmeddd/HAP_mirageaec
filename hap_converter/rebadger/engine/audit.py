"""A one-page record of what a rebadging run did.

Ships alongside the drawings so a submission set carries its own evidence:
what was applied, to which sheets, what changed on each, and what was
skipped and why.
"""

from __future__ import annotations

import io
from datetime import datetime

import pymupdf

from .models import INPUT_FIELDS, BatchResult, RebadgeInputs

_MARGIN = 48
_TITLE = 18
_BODY = 9
_LINE = 13.5
_NAVY = (0.078, 0.106, 0.302)
_GREY = (0.42, 0.45, 0.50)
_RED = (0.72, 0.16, 0.16)
_AMBER = (0.55, 0.38, 0.05)


def audit_name(when: datetime | None = None) -> str:
    return f"Rebadging_Audit_{(when or datetime.now()).strftime('%Y-%m-%d')}.pdf"


class _Writer:
    """A cursor that wraps, paginates, and keeps the margins honest."""

    def __init__(self, doc: pymupdf.Document):
        self.doc = doc
        self.page = doc.new_page(width=595, height=842)     # A4 portrait
        self.y = _MARGIN

    def _room(self, needed: float) -> None:
        if self.y + needed > self.page.rect.height - _MARGIN:
            self.page = self.doc.new_page(width=595, height=842)
            self.y = _MARGIN

    def text(self, value: str, *, size=_BODY, bold=False, color=(0, 0, 0),
             indent=0.0, gap=_LINE) -> None:
        self._room(gap)
        self.page.insert_text(
            pymupdf.Point(_MARGIN + indent, self.y + size),
            value, fontname="hebo" if bold else "helv", fontsize=size, color=color)
        self.y += gap

    def rule(self, gap=10.0) -> None:
        self._room(gap)
        self.page.draw_line(pymupdf.Point(_MARGIN, self.y),
                            pymupdf.Point(self.page.rect.width - _MARGIN, self.y),
                            color=_GREY, width=0.5)
        self.y += gap

    def space(self, amount=8.0) -> None:
        self.y += amount


def build_audit(inputs: RebadgeInputs, batch: BatchResult,
                when: datetime | None = None) -> bytes:
    """The audit PDF, as bytes."""
    stamp = when or datetime.now()
    doc = pymupdf.open()
    out = _Writer(doc)

    out.text("PDF Rebadging — Audit Record", size=_TITLE, bold=True, color=_NAVY, gap=26)
    out.text(f"Generated {stamp.strftime('%d %b %Y, %H:%M')}", color=_GREY, gap=18)
    out.rule()
    out.space()

    out.text("Values applied to every sheet", bold=True, gap=16)
    for key, label in INPUT_FIELDS:
        out.text(f"{label}:", indent=8, gap=0)
        out.text(str(getattr(inputs, key)), bold=True, indent=140)
    out.space()
    out.rule()
    out.space()

    out.text(
        f"Sheets: {len(batch.sheets)} submitted · {batch.ok_count} rebadged · "
        f"{batch.error_count} skipped · {batch.warning_count} note(s)",
        bold=True, gap=18)

    for sheet in batch.sheets:
        out.space(4)
        state = "REBADGED" if sheet.ok else "SKIPPED"
        colour = (0, 0, 0) if sheet.ok else _RED
        out.text(f"{state}   {sheet.filename}", bold=True, color=colour)
        if sheet.ok:
            arrow = f"{sheet.previous_rev or '—'}  ->  {sheet.new_rev}"
            out.text(f"Revision {arrow}", indent=16, color=_GREY)
        for note in sheet.warnings:
            out.text(f"note: {note}", indent=16, color=_AMBER, size=8)
        for problem in sheet.errors:
            out.text(f"reason: {problem}", indent=16, color=_RED, size=8)

    out.space()
    out.rule()
    out.text("Original drawings were not modified. Rebadged sheets are new files.",
             color=_GREY, size=8)

    buffer = io.BytesIO()
    doc.save(buffer, garbage=3, deflate=True)
    doc.close()
    return buffer.getvalue()
