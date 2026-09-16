# maec_auth

Engineering Tools' half of MAEC One Core's sign-in.

## resolution.py is vendored. Do not edit it here.

`resolution.py` is a **byte-for-byte copy** of `backend/identity/resolution.py`
in the [maec-one-core](https://github.com/Sajjadahmeddd/maec-one-core)
repository. It is the permission engine both services run: Core builds its
input from database rows, this product builds one from the claims of a token
Core signed (`from_claims`), and then both call the same `resolve()`.

That is the whole point, and it only holds while the two copies are the same
file. If they differ by one line — a tie-break, a level definition, a scope
rule — Core and this product will reach different decisions about the same
token, and nothing will break loudly. It surfaces months later as a
permissions bug nobody can reproduce.

So this copy is not maintained here. It is replaced.

## Updating it

When Core's engine changes:

1. Copy `backend/identity/resolution.py` from Core over this file.
2. Copy `backend/identity/resolution.sha256` alongside it.
3. Run the suite. `backend/tests/test_resolution_vendored.py` must pass.

Never edit `resolution.py` in this repository — not to reformat it, not to fix
an import, not to adapt it. A change that belongs in the engine belongs in
Core, and comes back here through the steps above.

## What the drift test enforces, and what it cannot

`test_resolution_vendored.py` fails if:

* this copy no longer matches the hash beside it (edited or corrupted here);
* it imports anything outside the standard library (a product has to import it
  with no database driver present);
* it no longer decides correctly (an allow and a deny, run through `resolve`).

It **cannot** catch Core changing the engine while nobody re-vendors it here:
this repository has no way to see Core's current hash. Until the two share a
CI that can fetch it, the update ritual above is the only guard. That trigger
is recorded as OPEN-DECISIONS #18.

The hash is taken over the file with CRLF normalised to LF, which is exactly
what Core's `resolution_hash.digest()` does — the same number on either
platform. `.gitattributes` also pins both files to LF so the bytes on disk stay
the bytes that were hashed. The eight-line algorithm is repeated in the test
rather than vendoring Core's `resolution_hash.py`, whose commands and paths
would be wrong here and which can *write* the hash file — something this
repository must never do.
