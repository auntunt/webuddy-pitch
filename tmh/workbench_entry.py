"""Absolute-path entry for desktop MCP clients, independent of their current cwd."""
from pathlib import Path
import sys

if __package__ in (None, ""):
    # Replace the script directory, not merely prepend the repo: leaving tmh/
    # on sys.path makes its legacy mcp.py shadow the official top-level SDK.
    sys.path[0] = str(Path(__file__).resolve().parent.parent)

from tmh.workbench import main

if __name__ == "__main__":
    sys.exit(main())
