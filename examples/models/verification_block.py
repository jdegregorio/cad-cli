"""Verification-oriented block with through and counterbored blind holes."""

from __future__ import annotations

from build123d import Axis, Box, Cylinder, Pos


def build_model(params: dict, context: object):
    x = float(params.get("x", 20.0))
    width = x
    depth = x
    height = 3.0 * x

    through_diameter = 0.25 * x
    blind_diameter = 0.25 * x
    counterbore_diameter = 0.5 * x
    blind_depth = 0.5 * x
    counterbore_depth = 0.25 * x

    block = Box(width, depth, height)

    through_hole = Cylinder(through_diameter / 2.0, width * 1.5).rotate(Axis.Y, 90)
    block = block - through_hole

    top_face_z = height / 2.0
    blind_hole = Pos(0.0, 0.0, top_face_z - blind_depth / 2.0) * Cylinder(
        blind_diameter / 2.0,
        blind_depth,
    )
    counterbore = Pos(0.0, 0.0, top_face_z - counterbore_depth / 2.0) * Cylinder(
        counterbore_diameter / 2.0,
        counterbore_depth,
    )
    block = block - blind_hole - counterbore
    return block
