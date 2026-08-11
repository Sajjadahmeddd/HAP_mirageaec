"""PyInstaller entry point (top-level so the hap_converter package resolves)."""

import sys

from hap_converter.main import main

if __name__ == "__main__":
    sys.exit(main())
