"""FastAPI wrapper around the MAEC engines.

The routers are thin: they take an upload, write it to a temp file, call the
exact same engine function the desktop app calls, and stream the result back.
No engine logic lives here.
"""
