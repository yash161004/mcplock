"""Local snapshot store — flat JSON, one file per server.

``~/.mcplock/snapshots/<server-id>.json``. No SQLite in v0.1; there are no
concurrent-access needs.
"""
