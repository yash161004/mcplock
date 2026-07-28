"""Compares a live snapshot against the stored baseline.

Emits new / removed / changed tools, with the specific changed fields and an
old-vs-new text diff for descriptions. Severity is a deliberately simple
keyword + schema-widening heuristic in v0.1 — no scoring model.
"""
