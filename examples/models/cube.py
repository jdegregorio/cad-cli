"""Simple troubleshooting cube for render and packaging demos."""

from __future__ import annotations

from build123d import Box


def build_model(params: dict, context: object):
    size = float(params.get("size", 20.0))
    return Box(size, size, size)
