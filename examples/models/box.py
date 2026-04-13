"""Example parametric solid box model for cad-cli."""

from __future__ import annotations

from build123d import Axis, Box


def build_model(params: dict, context: object):
    width = float(params.get("width", 10.0))
    depth = float(params.get("depth", 20.0))
    height = float(params.get("height", 30.0))
    translation = params.get("translation", [0.0, 0.0, 0.0])
    rotation_deg = params.get("rotation_deg", {})

    shape = Box(width, depth, height)
    if any(float(value) != 0.0 for value in translation):
        shape = shape.translate(tuple(float(value) for value in translation))

    for axis_name, axis in {"x": Axis.X, "y": Axis.Y, "z": Axis.Z}.items():
        angle = float(rotation_deg.get(axis_name, 0.0))
        if angle:
            shape = shape.rotate(axis, angle)
    return shape
