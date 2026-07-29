"""mcplock — pin, diff, and lint MCP tool definitions.

Pipeline: connector -> normalize -> hasher -> store/diff, with lint running
in parallel off the same raw tool list. report merges both sides.
"""

__version__ = "1.0.2"
