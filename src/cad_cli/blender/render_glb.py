"""Headless Blender renderer for deterministic orthographic previews."""
# mypy: ignore-errors

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Matrix, Vector


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("io_scene_gltf2", default_set=True)


def configure_world() -> None:
    world = bpy.data.worlds.new("cad_cli_world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.9, 0.91, 0.92, 1.0)
    background.inputs[1].default_value = 0.68
    bpy.context.scene.world = world


def import_glb(glb_path: Path) -> list[bpy.types.Object]:
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError(f"No mesh objects imported from {glb_path}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in mesh_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    joined.location = (0.0, 0.0, 0.0)
    return [joined]


def frame_scale(obj: bpy.types.Object) -> float:
    dimensions = obj.dimensions
    return max(dimensions.x, dimensions.y, dimensions.z, 1.0)


def apply_object_material(
    obj: bpy.types.Object, base_color: tuple | None = None
) -> None:
    material = bpy.data.materials.new(name="cad_cli_clay")
    material.use_nodes = True
    principled = material.node_tree.nodes["Principled BSDF"]
    # CAD-F-021: matte, lightly tinted verification material keeps surfaces legible
    # without pushing the part into blinding white highlights or a strong color cast.
    has_custom_color = base_color is not None
    color = base_color if has_custom_color else (0.66, 0.73, 0.79, 1.0)
    principled.inputs["Base Color"].default_value = color
    # When a custom colour is provided (e.g. compare-diff renders), use lower
    # roughness and higher specular so the tint is clearly visible.
    principled.inputs["Roughness"].default_value = 0.55 if has_custom_color else 0.86
    principled.inputs["Specular IOR Level"].default_value = 0.38 if has_custom_color else 0.14
    principled.inputs["Coat Roughness"].default_value = 0.55
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def camera_direction(view_name: str, location: tuple[float, float, float]) -> Vector:
    if view_name == "front":
        return Vector((0.0, 1.0, 0.0))
    if view_name == "back":
        return Vector((0.0, -1.0, 0.0))
    if view_name == "left":
        return Vector((1.0, 0.0, 0.0))
    if view_name == "right":
        return Vector((-1.0, 0.0, 0.0))
    if view_name == "top":
        return Vector((0.0, 0.0, -1.0))
    if view_name == "bottom":
        return Vector((0.0, 0.0, 1.0))
    if view_name == "iso":
        return -Vector(location).normalized()
    raise RuntimeError(f"Unknown render view: {view_name}")


def camera_up_hint(view_name: str) -> Vector:
    if view_name in {"front", "back", "left", "right", "iso"}:
        return Vector((0.0, 0.0, 1.0))
    if view_name in {"top", "bottom"}:
        return Vector((0.0, 1.0, 0.0))
    raise RuntimeError(f"Unknown render view: {view_name}")


def orient_camera(
    camera: bpy.types.Object, *, direction: Vector, up_hint: Vector
) -> None:
    """Build an explicit camera basis so datum views don't roll ambiguously."""
    forward = direction.normalized()
    right = forward.cross(up_hint).normalized()
    up = right.cross(forward).normalized()
    matrix = Matrix.Identity(4)
    matrix.col[0].xyz = right
    matrix.col[1].xyz = up
    matrix.col[2].xyz = -forward
    matrix.col[3].xyz = camera.location
    camera.matrix_world = matrix


def fit_ortho_camera_to_object(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    obj: bpy.types.Object,
    *,
    margin: float,
) -> None:
    """Fit the orthographic camera to the object's actual projected bounds."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = obj.evaluated_get(depsgraph)
    world_corners = [
        evaluated_obj.matrix_world @ Vector(corner) for corner in evaluated_obj.bound_box
    ]
    camera_inverse = camera.matrix_world.inverted()
    camera_corners = [camera_inverse @ corner for corner in world_corners]
    width = max(corner.x for corner in camera_corners) - min(
        corner.x for corner in camera_corners
    )
    height = max(corner.y for corner in camera_corners) - min(
        corner.y for corner in camera_corners
    )
    aspect = (
        scene.render.resolution_x * scene.render.pixel_aspect_x
    ) / (
        scene.render.resolution_y * scene.render.pixel_aspect_y
    )
    camera.data.ortho_scale = max(width, height * aspect, 1e-6) * margin


def add_lights(scale: float) -> None:
    sun_data = bpy.data.lights.new(name="Sun", type="SUN")
    sun_data.energy = 1.0
    sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
    sun.rotation_euler = (math.radians(38), 0.0, math.radians(22))
    bpy.context.scene.collection.objects.link(sun)

    area_data = bpy.data.lights.new(name="Area", type="AREA")
    area_data.energy = 1200.0
    area_data.shape = "RECTANGLE"
    area_data.size = scale * 2.2
    area_data.size_y = scale * 2.2
    area = bpy.data.objects.new(name="Area", object_data=area_data)
    area.location = (scale * 1.4, -scale * 1.25, scale * 1.7)
    area.rotation_euler = (math.radians(54), 0.0, math.radians(34))
    bpy.context.scene.collection.objects.link(area)

    rim_data = bpy.data.lights.new(name="Rim", type="AREA")
    rim_data.energy = 420.0
    rim_data.shape = "RECTANGLE"
    rim_data.size = scale * 1.9
    rim_data.size_y = scale * 1.9
    rim = bpy.data.objects.new(name="Rim", object_data=rim_data)
    rim.location = (-scale * 1.5, scale * 1.2, scale * 1.1)
    rim.rotation_euler = (math.radians(63), 0.0, math.radians(-122))
    bpy.context.scene.collection.objects.link(rim)

    fill_data = bpy.data.lights.new(name="BottomFill", type="AREA")
    fill_data.energy = 420.0
    fill_data.shape = "RECTANGLE"
    fill_data.size = scale * 1.8
    fill_data.size_y = scale * 1.8
    fill = bpy.data.objects.new(name="BottomFill", object_data=fill_data)
    fill.location = (0.0, 0.0, -scale * 1.8)
    fill.rotation_euler = (math.radians(180), 0.0, 0.0)
    bpy.context.scene.collection.objects.link(fill)


def add_camera(
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    view_name: str,
    name: str,
    location: tuple[float, float, float],
    *,
    ortho: bool,
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name=name)
    if ortho:
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = 1.0
    else:
        camera_data.type = "PERSP"
        camera_data.lens = 52
    camera = bpy.data.objects.new(name, camera_data)
    camera.location = location
    bpy.context.scene.collection.objects.link(camera)
    orient_camera(
        camera,
        direction=camera_direction(view_name, location),
        up_hint=camera_up_hint(view_name),
    )
    if ortho:
        # CAD-F-019 / CAD-F-020: fit each view to the true projected bounds.
        fit_ortho_camera_to_object(scene, camera, obj, margin=1.28)
    return camera


def render_camera(scene: bpy.types.Scene, camera: bpy.types.Object, output_path: Path) -> None:
    scene.camera = camera
    scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)


def configure_render(scene: bpy.types.Scene, spec: dict[str, object]) -> None:
    scene.render.engine = str(spec.get("engine", "BLENDER_EEVEE"))
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_x = int(spec.get("width", 768))
    scene.render.resolution_y = int(spec.get("height", 768))
    scene.render.film_transparent = False
    scene.render.use_freestyle = True
    if scene.render.engine == "BLENDER_EEVEE":
        scene.eevee.taa_render_samples = int(spec.get("samples", 32))
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True
        if hasattr(scene.eevee, "gtao_factor"):
            scene.eevee.gtao_factor = 1.8
        if hasattr(scene.eevee, "use_bloom"):
            scene.eevee.use_bloom = False
    else:
        scene.cycles.samples = int(spec.get("samples", 32))


def configure_freestyle(scene: bpy.types.Scene) -> None:
    """Use Blender-native line rendering for readable verification edges."""
    view_layer = bpy.context.view_layer
    freestyle = view_layer.freestyle_settings
    line_set = freestyle.linesets[0]
    line_set.select_by_edge_types = True
    line_set.select_by_visibility = True
    line_set.visibility = "VISIBLE"
    line_set.select_silhouette = True
    line_set.select_contour = True
    line_set.select_external_contour = True
    line_set.select_crease = True
    line_set.select_border = False
    line_set.select_edge_mark = False
    line_set.select_ridge_valley = False
    line_set.select_suggestive_contour = False
    line_set.select_material_boundary = False

    line_style = line_set.linestyle
    if line_style is None:
        line_style = bpy.data.linestyles.new(name="cad_cli_freestyle")
        line_set.linestyle = line_style
    line_style.use_chaining = True
    line_style.caps = "ROUND"
    line_style.color = (0.18, 0.22, 0.28)
    line_style.alpha = 1.0
    line_style.thickness = 1.7
    line_style.thickness_position = "CENTER"


def main(argv: list[str]) -> None:
    glb_path = Path(argv[0])
    output_dir = Path(argv[1])
    spec = json.loads(argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    reset_scene()
    configure_world()
    scene = bpy.context.scene
    configure_render(scene, spec)
    configure_freestyle(scene)
    objects = import_glb(glb_path)
    obj = objects[0]
    scale = frame_scale(obj)
    raw_color = spec.get("base_color")
    color_tuple = tuple(raw_color) if raw_color else None
    apply_object_material(obj, base_color=color_tuple)
    add_lights(scale)

    cameras = {
        "front": add_camera(
            scene,
            obj,
            "front",
            "Front",
            (0.0, -scale * 2.6, 0.0),
            ortho=True,
        ),
        "back": add_camera(
            scene,
            obj,
            "back",
            "Back",
            (0.0, scale * 2.6, 0.0),
            ortho=True,
        ),
        "left": add_camera(
            scene,
            obj,
            "left",
            "Left",
            (-scale * 2.6, 0.0, 0.0),
            ortho=True,
        ),
        "right": add_camera(
            scene,
            obj,
            "right",
            "Right",
            (scale * 2.6, 0.0, 0.0),
            ortho=True,
        ),
        "top": add_camera(
            scene,
            obj,
            "top",
            "Top",
            (0.0, 0.0, scale * 2.6),
            ortho=True,
        ),
        "bottom": add_camera(
            scene,
            obj,
            "bottom",
            "Bottom",
            (0.0, 0.0, -scale * 2.6),
            ortho=True,
        ),
        "iso": add_camera(
            scene,
            obj,
            "iso",
            "Iso",
            (scale * 1.75, -scale * 1.75, scale * 1.45),
            ortho=True,
        ),
    }

    requested_views = spec.get("views")
    for name, camera in cameras.items():
        if requested_views is not None and name not in requested_views:
            continue
        render_camera(scene, camera, output_dir / f"{name}.png")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :]
    try:
        main(args)
    except Exception as exc:  # pragma: no cover - exercised via Blender subprocess
        print(f"cad_cli Blender render failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
