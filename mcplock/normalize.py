"""Canonicalizes tool definitions before hashing.

Rules (Phase 1): sort object keys, collapse incidental whitespace, but never
touch semantic content — a single changed word must change the hash.
"""
