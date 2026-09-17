"""
CLI facade for the compact diagram builder.

The renderer and YAML validation live in diagram_builder.py; this file gives the
folder the same simple entry-point shape as the other compact tools.
"""

from __future__ import annotations

from diagram_builder import main


if __name__ == "__main__":
    main()
