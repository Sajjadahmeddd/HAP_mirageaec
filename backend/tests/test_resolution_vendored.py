"""The vendored copy of Core's permission engine, and proof it has not drifted.

`backend/maec_auth/resolution.py` is a byte-for-byte copy of
`backend/identity/resolution.py` in maec-one-core. Both services run that one
engine — Core over database rows, this product over the claims of a token Core
signed — so a single line of difference would have the two reach different
decisions about the same token, with nothing failing loudly. These tests are
what fails instead.

  * the hash test   — this copy was edited or corrupted here
  * the import test — it grew a dependency a product cannot satisfy
  * the smoke test  — it does not merely match, it runs and decides

What none of them catch, deliberately: Core changing the engine while nobody
re-vendors it here. This repository cannot see Core's current hash. See
`backend/maec_auth/README.md`, and OPEN-DECISIONS #18 for the trigger to
promote this to a cross-repo check once the two share a CI.
"""

from __future__ import annotations

import ast
import hashlib
import re
import sys
from dataclasses import replace
from pathlib import Path

from backend.maec_auth import resolution
from backend.maec_auth.resolution import Grant, ResolutionInput, resolve

ENGINE = Path(resolution.__file__)
PUBLISHED = ENGINE.with_name("resolution.sha256")


def digest(path: Path = ENGINE) -> str:
    """SHA-256 of the file, CRLF normalised to LF.

    The same rule as Core's `resolution_hash.digest`, so both repositories get
    the same number for the same file whatever a checkout did to its line
    endings. Repeated here rather than vendoring Core's module, whose commands
    name Core's paths and which can rewrite the hash file — which this
    repository must never do: the hash is Core's to publish.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _non_stdlib_imports(source: str) -> list[str]:
    """Every import in this source that is not the standard library.

    Parsed, not grepped: resolution.py's own docstring carries a line starting
    "from the claims of a token", which a scan of import lines reads as an
    import of a module called `the`. Relative imports are refused outright —
    a vendored file that reaches for its neighbours is not portable.
    """
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                offenders.append(f"line {node.lineno}: from {'.' * node.level}{node.module or ''}")
                continue
            names = [node.module or ""]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        for name in names:
            if name.split(".")[0] not in sys.stdlib_module_names:
                offenders.append(f"line {node.lineno}: {name}")
    return offenders


# --------------------------------------------------------------- the copy
def test_the_vendored_engine_matches_its_published_hash():
    """If this fails, resolution.py was changed in THIS repository. It is not
    maintained here — replace it with Core's copy and Core's hash. See
    backend/maec_auth/README.md."""
    published = PUBLISHED.read_text(encoding="ascii").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", published), published
    assert digest() == published, (
        f"the vendored resolution.py hashes to {digest()}, but the hash beside "
        f"it says {published} — this copy has drifted from Core's")


def test_the_vendored_engine_imports_only_the_standard_library():
    """A product imports this with no database driver in sight."""
    offenders = _non_stdlib_imports(ENGINE.read_text(encoding="utf-8"))
    assert not offenders, "; ".join(offenders)


def test_the_import_check_catches_what_it_exists_for():
    source = "\n".join([
        '"""from the claims of a token — prose, not an import"""',
        "import json",
        "from collections.abc import Mapping",
        "from sqlalchemy import select",
        "import fastapi.responses",
        "from backend.identity import config",
        "from .db import get_db",
    ])
    assert len(_non_stdlib_imports(source)) == 4


def test_the_contract_version_is_declared():
    """Which behaviour this copy claims, for a divergence report to quote."""
    assert isinstance(resolution.RESOLUTION_CONTRACT, str)
    assert resolution.RESOLUTION_CONTRACT.strip()


# ------------------------------------------------------ it actually decides
CONVERT = "engineering:hapext:convert"
EMPLOYEE = Grant(role_id="role-employee", role_key="employee",
                 scope_type="application", scope_id="engineering")
ALLOWED = ResolutionInput(
    app_key="engineering",
    org_id="org-mirage",
    entitled=True,
    grants=(EMPLOYEE,),
    role_permissions={(EMPLOYEE.role_id, CONVERT): "allow"},
)


def test_the_vendored_engine_allows_what_the_role_allows():
    """Matching bytes is not the same as running. An engineer holding
    `employee` at application scope, entitled to the product, may convert."""
    assert resolve(ALLOWED, CONVERT) is True


def test_the_vendored_engine_refuses_what_the_role_denies():
    """The same person, the same scope, the grant flipped to a deny."""
    denied = replace(ALLOWED, role_permissions={(EMPLOYEE.role_id, CONVERT): "deny"})
    assert resolve(denied, CONVERT) is False
