"""What Engineering Tools needs to let MAEC One Core's signed-in people in.

The gate (gate.py) asks Core about the browser's cookie on every request; the
guard (guard.py) maps each route to the permission it needs; routes.py tells
the frontend who it is talking to. Signing in and out happen at Core.
"""
