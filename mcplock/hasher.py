"""Stable SHA-256 hashing of normalized tool definitions.

Produces a full hash plus a hash per field (name / description / schema) so
diffs can name the field that drifted.
"""
