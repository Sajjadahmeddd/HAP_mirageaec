"""The audit log is append-only.

Two guarantees, tested two ways: no code in the repository updates or
deletes an audit row (a scan of the source), and the migration installs a
database trigger that refuses to (checked by the Postgres migration test,
which runs only where a Postgres is available)."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select

from backend.identity.models import AuditLog
from backend.identity.permissions import audit

REPO = Path(__file__).resolve().parents[1]
SOURCE = [*(REPO / "backend").rglob("*.py")]

# The ways SQLAlchemy code deletes or updates rows of a model.
FORBIDDEN = [
    re.compile(r"delete\(\s*AuditLog"),          # sqlalchemy.delete(AuditLog)
    re.compile(r"update\(\s*AuditLog"),          # sqlalchemy.update(AuditLog)
    re.compile(r"query\(\s*AuditLog\s*\)[^\n]*\.(delete|update)\("),
    re.compile(r"db\.delete\(\s*(row|entry|log|audit)\b"),
]


def test_nothing_in_the_backend_updates_or_deletes_an_audit_row():
    offenders = []
    for path in SOURCE:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO)}: {pattern.pattern}")
    assert not offenders, "\n".join(offenders)


def test_the_migration_installs_the_append_only_trigger():
    versions = REPO / "backend" / "identity" / "migrations" / "versions"
    text = "\n".join(p.read_text(encoding="utf-8") for p in versions.glob("*.py"))
    assert "audit_logs_append_only" in text
    assert "BEFORE UPDATE OR DELETE ON audit_logs" in text


def test_the_writer_records_who_did_what_and_from_where(db):
    from sqlalchemy import select as sel
    from backend.identity.models import User
    admin = db.scalar(sel(User).where(User.email == "admin@mirageaec.com"))

    class FakeRequest:
        client = type("C", (), {"host": "203.0.113.9"})()
        headers = {"user-agent": "pytest/1.0", "x-forwarded-for": "198.51.100.4, 10.0.0.1"}

    audit(db, actor=admin, action="test.action", target_type="thing", target_id="42",
          source="api", result="success", request=FakeRequest(),
          before={"a": 1}, after={"a": 2})
    row = db.scalar(select(AuditLog).where(AuditLog.action == "test.action"))
    assert row.actor_id == admin.id
    assert row.actor_email == admin.email
    assert row.org_id == admin.org_id
    assert row.ip == "198.51.100.4"                 # the client, not the proxy
    assert row.user_agent == "pytest/1.0"
    assert row.before == {"a": 1} and row.after == {"a": 2}
    assert row.created_at is not None
