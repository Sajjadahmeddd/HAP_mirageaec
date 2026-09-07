"""Prove the drawing came through the edit unchanged.

Removing text means rewriting the page's content stream, and a rewrite is the
one place a rebadge could disturb the drawing it is supposed to leave alone.
So the drawing is not assumed intact — it is checked, by comparing where every
piece of text sits before and after, and reporting anything that moved outside
the cells we deliberately edited.

Text position is the right probe: it is exact, cheap, and it catches the class
of damage a stream rewrite actually causes (operators dropped or re-encoded),
which a coarse pixel sample of one region can miss entirely.
"""

from __future__ import annotations

import pymupdf

from .locator import words

# Below this a difference is float noise in the rewritten coordinates, not a
# glyph that landed somewhere else. Well under a printed hair's breadth.
_TOLERANCE = 0.05


def span_index(page: pymupdf.Page) -> dict[str, list[tuple[float, float]]]:
    """Every word's displayed origin, keyed by its text.

    Words rather than spans: this only needs to know what sits where, and the
    cheap extraction answers that in a hundredth of the time.
    """
    index: dict[str, list[tuple[float, float]]] = {}
    for rect, text in words(page):
        index.setdefault(text, []).append((rect.x0, rect.y0))
    for positions in index.values():
        positions.sort()
    return index


def displaced(before: dict, after: dict, edited: list[pymupdf.Rect]) -> list[str]:
    """Text that moved, ignoring the cells we meant to change.

    Only spans present in both versions are compared: a value we removed is
    absent from `after` by design, and the replacement we wrote is new.
    """
    # Words that moved together belong to the same piece of text, so they are
    # grouped by how far they went and reported once — a shifted sentence is
    # one problem, not one per word.
    moved: dict[tuple[float, float], list[tuple[float, str]]] = {}
    for text, origins in before.items():
        landing = after.get(text)
        if not landing:
            continue
        for (bx, by), (ax, ay) in zip(origins, landing):
            dx, dy = ax - bx, ay - by
            if abs(dx) <= _TOLERANCE and abs(dy) <= _TOLERANCE:
                continue
            if any(rect.contains(pymupdf.Point(bx, by)) for rect in edited):
                continue                      # inside a cell we edited
            moved.setdefault((round(dx, 2), round(dy, 2)), []).append((bx, text))

    problems: list[str] = []
    for (dx, dy), items in sorted(moved.items()):
        items.sort()
        phrase = " ".join(text for _, text in items)[:60]
        problems.append(
            f"{phrase!r} shifted by ({dx:+.2f}, {dy:+.2f}) pt when the "
            f"content stream was rewritten"
        )
    return problems
