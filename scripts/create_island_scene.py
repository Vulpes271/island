"""
Procedural low-poly island scene for Blender.

Run with:
    blender --background --python scripts/create_island_scene.py

The script generates a complete stylized island map with two villages, roads,
trees, rocks, a dock, boats, lighting, camera, and exported project files.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


SEED = 73
random.seed(SEED)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
ASSETS_DIR = PROJECT_ROOT / "assets"
BLEND_PATH = OUTPUT_DIR / "island_two_villages.blend"
GLB_PATH = OUTPUT_DIR / "island_two_villages.glb"

ISLAND_X_RADIUS = 9.4
ISLAND_Y_RADIUS = 6.8
BEACH_START = 0.78
COLLECTIONS = {}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 0.0
    t = clamp((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def angle_delta(a: float, b: float) -> float:
    return math.atan2(math.sin(a - b), math.cos(a - b))


def create_material(name: str, color, roughness: float = 0.85, metallic: float = 0.0):
    """Create or update a simple material with a visible viewport color."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    if hasattr(mat, "roughness"):
        mat.roughness = roughness
    if hasattr(mat, "metallic"):
        mat.metallic = metallic

    if color[3] < 1.0:
        mat.blend_method = "BLEND"
        if hasattr(mat, "use_screen_refraction"):
            mat.use_screen_refraction = True

    return mat


def ensure_collection(name: str, parent_name: str | None = None):
    """Create a logical collection once and return it."""
    if name in COLLECTIONS:
        return COLLECTIONS[name]

    collection = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = bpy.context.scene.collection if parent_name is None else ensure_collection(parent_name)
    if collection.name not in [child.name for child in parent.children]:
        parent.children.link(collection)
    COLLECTIONS[name] = collection
    return collection


def link_to_collection(obj, collection_name: str | None):
    if not collection_name:
        return obj
    collection = ensure_collection(collection_name)
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    return obj


def create_scene_collections():
    for name in ("Island", "Village_1", "Village_2", "Boats", "Roads", "Trees", "Props", "Interiors"):
        ensure_collection(name)


def boundary_factor(theta: float) -> float:
    """Organic outline multiplier used by both terrain and object placement."""
    southeast_cove = -0.18 * math.exp(-((angle_delta(theta, -0.62) / 0.24) ** 2))
    return (
        1.0
        + 0.14 * math.sin(theta * 3.0 + 0.4)
        + 0.09 * math.sin(theta * 5.0 - 1.1)
        + 0.06 * math.sin(theta * 8.0 + 2.0)
        + 0.035 * math.cos(theta * 11.0 - 0.7)
        + southeast_cove
    )


def organic_point(theta: float, radius_fraction: float = 1.0):
    factor = boundary_factor(theta)
    return (
        math.cos(theta) * ISLAND_X_RADIUS * factor * radius_fraction,
        math.sin(theta) * ISLAND_Y_RADIUS * factor * radius_fraction,
    )


def normalized_radius(x: float, y: float):
    theta = math.atan2(y / ISLAND_Y_RADIUS, x / ISLAND_X_RADIUS)
    ellipse_radius = math.sqrt((x / ISLAND_X_RADIUS) ** 2 + (y / ISLAND_Y_RADIUS) ** 2)
    return ellipse_radius / boundary_factor(theta), theta


def island_height(x: float, y: float) -> float:
    """Height field shared by terrain, roads, houses, trees, and rocks."""
    radius, theta = normalized_radius(x, y)
    if radius >= 1.0:
        return -0.05

    if radius > BEACH_START:
        beach_t = (1.0 - radius) / (1.0 - BEACH_START)
        return 0.02 + 0.08 * smoothstep(0.0, 1.0, beach_t)

    coast_falloff = smoothstep(BEACH_START, 0.16, radius)
    hill_a = 1.05 * math.exp(-(((x + 1.2) / 4.6) ** 2 + ((y + 0.7) / 3.2) ** 2))
    hill_b = 0.72 * math.exp(-(((x - 3.4) / 3.0) ** 2 + ((y - 2.2) / 2.3) ** 2))
    hill_c = 0.52 * math.exp(-(((x + 4.8) / 2.4) ** 2 + ((y - 2.0) / 1.9) ** 2))
    ridge = 0.18 * math.sin(x * 0.85 + 0.6) * math.cos(y * 0.72 - 0.4)

    return max(0.08, 0.12 + coast_falloff * (hill_a + hill_b + hill_c + ridge))


def local_to_world(origin, rotation_z: float, point):
    cos_r = math.cos(rotation_z)
    sin_r = math.sin(rotation_z)
    return (
        origin[0] + point[0] * cos_r - point[1] * sin_r,
        origin[1] + point[0] * sin_r + point[1] * cos_r,
        origin[2] + point[2],
    )


def add_box(name: str, location, dimensions, material, rotation_z: float = 0.0, collection: str | None = None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0.0, 0.0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    if material:
        obj.data.materials.append(material)
    link_to_collection(obj, collection)
    return obj


def add_local_box(name: str, origin, rotation_z: float, local_center, dimensions, material, collection: str | None = None):
    return add_box(name, local_to_world(origin, rotation_z, local_center), dimensions, material, rotation_z, collection)


def create_roof(name: str, origin, rotation_z: float, width: float, depth: float, wall_height: float, roof_height: float, material, style: str = "gable", collection: str | None = None):
    eave = 0.12
    w = width + eave * 2.0
    d = depth + eave * 2.0

    if style == "hip":
        local_vertices = [
            (-w / 2.0, -d / 2.0, wall_height),
            (w / 2.0, -d / 2.0, wall_height),
            (w / 2.0, d / 2.0, wall_height),
            (-w / 2.0, d / 2.0, wall_height),
            (-w * 0.22, 0.0, wall_height + roof_height),
            (w * 0.22, 0.0, wall_height + roof_height),
        ]
        faces = [
            (0, 1, 5, 4),
            (1, 2, 5),
            (2, 3, 4, 5),
            (3, 0, 4),
        ]
    elif style == "shed":
        local_vertices = [
            (-w / 2.0, -d / 2.0, wall_height),
            (w / 2.0, -d / 2.0, wall_height),
            (w / 2.0, d / 2.0, wall_height),
            (-w / 2.0, d / 2.0, wall_height),
            (-w / 2.0, -d / 2.0, wall_height + roof_height * 0.35),
            (w / 2.0, -d / 2.0, wall_height + roof_height * 0.35),
            (w / 2.0, d / 2.0, wall_height + roof_height),
            (-w / 2.0, d / 2.0, wall_height + roof_height),
        ]
        faces = [
            (4, 5, 6, 7),
            (0, 4, 7, 3),
            (1, 2, 6, 5),
            (0, 1, 5, 4),
            (3, 7, 6, 2),
        ]
    else:
        local_vertices = [
            (-w / 2.0, -d / 2.0, wall_height),
            (w / 2.0, -d / 2.0, wall_height),
            (0.0, -d / 2.0, wall_height + roof_height),
            (-w / 2.0, d / 2.0, wall_height),
            (w / 2.0, d / 2.0, wall_height),
            (0.0, d / 2.0, wall_height + roof_height),
        ]
        faces = [
            (0, 1, 2),
            (3, 5, 4),
            (0, 3, 4, 1),
            (1, 4, 5, 2),
            (0, 2, 5, 3),
        ]

    vertices = [local_to_world(origin, rotation_z, vertex) for vertex in local_vertices]

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    link_to_collection(obj, collection)
    return obj


def create_house(
    name: str,
    location,
    rotation_z: float,
    wall_material,
    roof_material,
    door_material,
    window_material,
    scale: float = 1.0,
    width: float | None = None,
    depth: float | None = None,
    wall_height: float | None = None,
    roof_height: float | None = None,
    roof_style: str = "gable",
    door_offset: float = 0.0,
    window_count: int = 2,
    side_windows: bool = True,
):
    """Create a low-poly house with configurable proportions and roof shape."""
    width = (width if width is not None else random.uniform(0.78, 1.08)) * scale
    depth = (depth if depth is not None else random.uniform(0.82, 1.16)) * scale
    wall_height = (wall_height if wall_height is not None else random.uniform(0.55, 0.72)) * scale
    roof_height = (roof_height if roof_height is not None else random.uniform(0.34, 0.48)) * scale

    wall_center = local_to_world(location, rotation_z, (0.0, 0.0, wall_height / 2.0))
    add_box(f"{name} Walls", wall_center, (width, depth, wall_height), wall_material, rotation_z)
    create_roof(f"{name} {roof_style.title()} Roof", location, rotation_z, width, depth, wall_height, roof_height, roof_material, roof_style)

    door_width = width * 0.22
    door_height = wall_height * 0.62
    door_x = clamp(door_offset, -0.35, 0.35) * width
    door_center = local_to_world(location, rotation_z, (door_x, -depth / 2.0 - 0.026, door_height / 2.0))
    add_box(f"{name} Door", door_center, (door_width, 0.05, door_height), door_material, rotation_z)

    window_size = min(width, wall_height) * 0.18
    possible_front_windows = [-0.34, 0.0, 0.34] if window_count >= 3 else [-0.28, 0.28]
    used = 0
    for window_x_factor in possible_front_windows:
        window_x = window_x_factor * width
        if abs(window_x - door_x) < door_width * 1.15:
            continue
        window_center = local_to_world(location, rotation_z, (window_x, -depth / 2.0 - 0.028, wall_height * 0.58))
        add_box(f"{name} Front Window", window_center, (window_size, 0.045, window_size), window_material, rotation_z)
        used += 1
        if used >= window_count:
            break

    if side_windows:
        for side in (-1.0, 1.0):
            side_window_center = local_to_world(location, rotation_z, (side * (width / 2.0 + 0.026), 0.08, wall_height * 0.58))
            add_box(f"{name} Side Window", side_window_center, (0.045, window_size, window_size), window_material, rotation_z)

    return {
        "name": name,
        "location": location,
        "width": width,
        "depth": depth,
        "height": wall_height + roof_height,
    }


def create_house_variant(name: str, location, rotation_z: float, wall_material, roof_material, door_material, window_material, variant: str, rng: random.Random):
    """Create a deterministic house variation for village layouts."""
    profiles = {
        "cottage": {"width": 0.86, "depth": 0.9, "wall_height": 0.58, "roof_height": 0.42, "roof_style": "gable", "window_count": 1},
        "family": {"width": 1.18, "depth": 1.02, "wall_height": 0.68, "roof_height": 0.46, "roof_style": "gable", "window_count": 2},
        "tall": {"width": 0.92, "depth": 1.02, "wall_height": 0.9, "roof_height": 0.5, "roof_style": "hip", "window_count": 2},
        "wide": {"width": 1.5, "depth": 1.04, "wall_height": 0.66, "roof_height": 0.42, "roof_style": "hip", "window_count": 3},
        "hut": {"width": 0.82, "depth": 0.82, "wall_height": 0.54, "roof_height": 0.32, "roof_style": "shed", "window_count": 1},
        "workshop": {"width": 1.72, "depth": 1.12, "wall_height": 0.72, "roof_height": 0.38, "roof_style": "shed", "window_count": 2},
    }
    profile = profiles[variant].copy()
    scale = rng.uniform(0.9, 1.12)
    profile["door_offset"] = rng.choice([-0.22, -0.1, 0.0, 0.16, 0.24])
    profile["side_windows"] = variant not in {"hut"} or rng.random() > 0.35

    return create_house(
        name,
        location,
        rotation_z,
        wall_material,
        roof_material,
        door_material,
        window_material,
        scale=scale,
        **profile,
    )


def create_tree(name: str, location, trunk_material, leaves_material, scale: float = 1.0):
    """Create a stylized low-poly tree from a trunk and two leaf cones."""
    trunk_height = 0.45 * scale
    trunk_radius = 0.07 * scale
    leaf_height = 0.68 * scale
    leaf_radius = 0.38 * scale

    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=trunk_radius, depth=trunk_height, location=(location[0], location[1], location[2] + trunk_height / 2.0))
    trunk = bpy.context.object
    trunk.name = f"{name} Trunk"
    trunk.data.materials.append(trunk_material)
    link_to_collection(trunk, "Trees")

    for index, z_offset in enumerate((trunk_height + leaf_height * 0.35, trunk_height + leaf_height * 0.78)):
        bpy.ops.mesh.primitive_cone_add(
            vertices=7,
            radius1=leaf_radius * (1.0 - index * 0.22),
            radius2=0.0,
            depth=leaf_height * (0.92 - index * 0.15),
            location=(location[0], location[1], location[2] + z_offset),
            rotation=(0.0, 0.0, random.uniform(0.0, math.tau)),
        )
        leaves = bpy.context.object
        leaves.name = f"{name} Leaves {index + 1}"
        leaves.data.materials.append(leaves_material)
        link_to_collection(leaves, "Trees")


def create_road_or_path(name: str, points, width: float, material, z_offset: float = 0.055):
    """Create a raised mesh strip along a polyline so roads remain visible."""
    if len(points) < 2:
        return None

    vertices = []
    for index, point in enumerate(points):
        x, y = point[0], point[1]
        if index == 0:
            tx = points[1][0] - x
            ty = points[1][1] - y
        elif index == len(points) - 1:
            tx = x - points[index - 1][0]
            ty = y - points[index - 1][1]
        else:
            tx = points[index + 1][0] - points[index - 1][0]
            ty = points[index + 1][1] - points[index - 1][1]

        length = math.hypot(tx, ty) or 1.0
        nx = -ty / length
        ny = tx / length
        z = island_height(x, y) + z_offset
        vertices.append((x + nx * width / 2.0, y + ny * width / 2.0, z))
        vertices.append((x - nx * width / 2.0, y - ny * width / 2.0, z))

    faces = [(i * 2, i * 2 + 2, i * 2 + 3, i * 2 + 1) for i in range(len(points) - 1)]
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    link_to_collection(obj, "Roads")
    return obj


def create_flat_patch(name: str, center, width: float, depth: float, material, rotation_z: float = 0.0, z_offset: float = 0.07, corners: int = 4, collection: str = "Roads"):
    """Create a terrain-hugging patch for plazas, yards, and sand transitions."""
    if corners == 8:
        local_points = []
        for index in range(8):
            angle = math.tau * index / 8.0 + math.pi / 8.0
            local_points.append((math.cos(angle) * width / 2.0, math.sin(angle) * depth / 2.0))
    else:
        local_points = [
            (-width / 2.0, -depth / 2.0),
            (width / 2.0, -depth / 2.0),
            (width / 2.0, depth / 2.0),
            (-width / 2.0, depth / 2.0),
        ]

    vertices = []
    for x_local, y_local in local_points:
        x, y, _z = local_to_world((center[0], center[1], 0.0), rotation_z, (x_local, y_local, 0.0))
        vertices.append((x, y, island_height(x, y) + z_offset))

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], [tuple(range(len(vertices)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    link_to_collection(obj, collection)
    return obj


def create_prop_crate(name: str, location, wood_material, dark_material, scale: float = 1.0, rotation_z: float = 0.0, collection: str = "Props"):
    size = 0.28 * scale
    add_box(f"{name} Box", (location[0], location[1], location[2] + size / 2.0), (size, size, size), wood_material, rotation_z, collection)
    add_box(f"{name} Cross Slat A", (location[0], location[1], location[2] + size * 0.55), (size * 1.08, 0.035 * scale, 0.035 * scale), dark_material, rotation_z + math.radians(32), collection)
    add_box(f"{name} Cross Slat B", (location[0], location[1], location[2] + size * 0.55), (size * 1.08, 0.035 * scale, 0.035 * scale), dark_material, rotation_z - math.radians(32), collection)


def create_prop_barrel(name: str, location, wood_material, band_material, scale: float = 1.0, collection: str = "Props"):
    radius = 0.13 * scale
    height = 0.34 * scale
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=radius, depth=height, location=(location[0], location[1], location[2] + height / 2.0))
    barrel = bpy.context.object
    barrel.name = f"{name} Barrel"
    barrel.data.materials.append(wood_material)
    link_to_collection(barrel, collection)

    for z_factor in (0.28, 0.72):
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=radius * 1.04, depth=0.035 * scale, location=(location[0], location[1], location[2] + height * z_factor))
        band = bpy.context.object
        band.name = f"{name} Barrel Band"
        band.data.materials.append(band_material)
        link_to_collection(band, collection)


def create_prop_woodpile(name: str, location, wood_material, scale: float = 1.0, rotation_z: float = 0.0):
    for row in range(2):
        for index in range(3):
            x_offset = (index - 1) * 0.12 * scale
            z_offset = (row + 0.5) * 0.08 * scale
            x, y, z = local_to_world(location, rotation_z, (x_offset, 0.0, z_offset))
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=6,
                radius=0.035 * scale,
                depth=0.36 * scale,
                location=(x, y, z),
                rotation=(0.0, math.radians(90), rotation_z),
            )
            log = bpy.context.object
            log.name = f"{name} Log"
            log.data.materials.append(wood_material)


def create_fence(name: str, points, wood_material, post_height: float = 0.42):
    if len(points) < 2:
        return

    for index, point in enumerate(points):
        z = island_height(point[0], point[1]) + 0.08
        add_box(f"{name} Post {index + 1}", (point[0], point[1], z + post_height / 2.0), (0.075, 0.075, post_height), wood_material, 0.0)

    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.atan2(y2 - y1, x2 - x1)
        z = (island_height(x1, y1) + island_height(x2, y2)) / 2.0 + 0.08
        for rail_height in (0.2, 0.34):
            add_box(
                f"{name} Rail {index + 1}",
                ((x1 + x2) / 2.0, (y1 + y2) / 2.0, z + rail_height),
                (length, 0.045, 0.045),
                wood_material,
                angle,
            )


def create_garden_patch(name: str, center, material, row_material, rotation_z: float = 0.0, scale: float = 1.0):
    create_flat_patch(f"{name} Garden Soil", center, 0.72 * scale, 0.46 * scale, material, rotation_z, 0.08, 4)
    for offset in (-0.18, 0.0, 0.18):
        x, y, z = local_to_world((center[0], center[1], island_height(center[0], center[1]) + 0.11), rotation_z, (offset * scale, 0.0, 0.0))
        add_box(f"{name} Garden Row", (x, y, z), (0.055 * scale, 0.42 * scale, 0.045 * scale), row_material, rotation_z)


def create_fishing_net(name: str, center, rope_material, rotation_z: float = 0.0, scale: float = 1.0):
    z = island_height(center[0], center[1]) + 0.13
    for offset in (-0.24, -0.08, 0.08, 0.24):
        x, y, _z = local_to_world((center[0], center[1], z), rotation_z, (offset * scale, 0.0, 0.0))
        add_box(f"{name} Net Strand A", (x, y, z), (0.025 * scale, 0.72 * scale, 0.025 * scale), rope_material, rotation_z)
        x, y, _z = local_to_world((center[0], center[1], z), rotation_z, (0.0, offset * scale, 0.0))
        add_box(f"{name} Net Strand B", (x, y, z + 0.012), (0.72 * scale, 0.025 * scale, 0.025 * scale), rope_material, rotation_z)


def create_fish_drying_rack(name: str, center, wood_material, fish_material, rotation_z: float = 0.0, scale: float = 1.0):
    width = 0.92 * scale
    post_height = 0.78 * scale
    for side in (-1.0, 1.0):
        x, y, z = local_to_world((center[0], center[1], island_height(center[0], center[1]) + 0.08), rotation_z, (side * width / 2.0, 0.0, post_height / 2.0))
        add_box(f"{name} Post", (x, y, z), (0.07 * scale, 0.07 * scale, post_height), wood_material, rotation_z)

    cross_center = local_to_world((center[0], center[1], island_height(center[0], center[1]) + 0.08), rotation_z, (0.0, 0.0, post_height))
    add_box(f"{name} Cross Beam", cross_center, (width + 0.2 * scale, 0.065 * scale, 0.065 * scale), wood_material, rotation_z)

    for index, offset in enumerate((-0.28, 0.0, 0.28)):
        x, y, z = local_to_world((center[0], center[1], island_height(center[0], center[1]) + 0.08), rotation_z, (offset * scale, -0.025 * scale, post_height - 0.2 * scale))
        add_box(f"{name} Dried Fish {index + 1}", (x, y, z), (0.09 * scale, 0.025 * scale, 0.24 * scale), fish_material, rotation_z)


def create_well(name: str, center, stone_material, wood_material, roof_material, bucket_material):
    """Create a recognizable village well with stone base, posts, roof, and bucket."""
    ground_z = island_height(center[0], center[1]) + 0.09
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.32, depth=0.28, location=(center[0], center[1], ground_z + 0.14))
    base = bpy.context.object
    base.name = f"{name} Stone Ring"
    base.data.materials.append(stone_material)

    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.2, depth=0.035, location=(center[0], center[1], ground_z + 0.295))
    hole = bpy.context.object
    hole.name = f"{name} Dark Opening"
    hole.data.materials.append(bucket_material)

    for side in (-1.0, 1.0):
        add_box(
            f"{name} Upright Beam",
            (center[0] + side * 0.32, center[1], ground_z + 0.68),
            (0.08, 0.08, 0.82),
            wood_material,
            0.0,
        )

    add_box(f"{name} Cross Beam", (center[0], center[1], ground_z + 1.04), (0.78, 0.08, 0.08), wood_material, 0.0)
    create_roof(f"{name} Little Roof", (center[0], center[1], ground_z + 1.02), 0.0, 0.9, 0.7, 0.0, 0.28, roof_material, "gable")

    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.08, depth=0.12, location=(center[0], center[1] - 0.08, ground_z + 0.52))
    bucket = bpy.context.object
    bucket.name = f"{name} Hanging Bucket"
    bucket.data.materials.append(bucket_material)


def create_window_detail(name: str, origin, rotation_z: float, local_center, width: float, height: float, materials, wall_side: str, collection: str):
    """Add a pane, frame, shutters, and sill to a window opening."""
    pane_mat = materials["window"]
    wood_mat = materials["dark_wood"]
    flower_mat = materials.get("flower", materials["garden_green"])

    if wall_side in {"front", "back"}:
        pane_dims = (width, 0.028, height)
        frame_h_dims = (width + 0.11, 0.04, 0.045)
        frame_v_dims = (0.045, 0.04, height + 0.1)
        sill_dims = (width + 0.16, 0.08, 0.045)
        add_local_box(f"{name} Glass Pane", origin, rotation_z, local_center, pane_dims, pane_mat, collection)
        for zoff in (-height / 2.0 - 0.035, height / 2.0 + 0.035):
            add_local_box(f"{name} Window Frame Horizontal", origin, rotation_z, (local_center[0], local_center[1], local_center[2] + zoff), frame_h_dims, wood_mat, collection)
        for xoff in (-width / 2.0 - 0.035, width / 2.0 + 0.035):
            add_local_box(f"{name} Window Frame Vertical", origin, rotation_z, (local_center[0] + xoff, local_center[1], local_center[2]), frame_v_dims, wood_mat, collection)
            add_local_box(f"{name} Shutter", origin, rotation_z, (local_center[0] + xoff * 1.35, local_center[1], local_center[2]), (0.07, 0.035, height * 0.9), wood_mat, collection)
        add_local_box(f"{name} Flower Box", origin, rotation_z, (local_center[0], local_center[1] - 0.02, local_center[2] - height / 2.0 - 0.12), sill_dims, wood_mat, collection)
        add_local_box(f"{name} Flowers", origin, rotation_z, (local_center[0], local_center[1] - 0.03, local_center[2] - height / 2.0 - 0.075), (width * 0.8, 0.045, 0.055), flower_mat, collection)
    else:
        pane_dims = (0.028, width, height)
        frame_h_dims = (0.04, width + 0.11, 0.045)
        frame_v_dims = (0.04, 0.045, height + 0.1)
        add_local_box(f"{name} Glass Pane", origin, rotation_z, local_center, pane_dims, pane_mat, collection)
        for zoff in (-height / 2.0 - 0.035, height / 2.0 + 0.035):
            add_local_box(f"{name} Window Frame Horizontal", origin, rotation_z, (local_center[0], local_center[1], local_center[2] + zoff), frame_h_dims, wood_mat, collection)
        for yoff in (-width / 2.0 - 0.035, width / 2.0 + 0.035):
            add_local_box(f"{name} Window Frame Vertical", origin, rotation_z, (local_center[0], local_center[1] + yoff, local_center[2]), frame_v_dims, wood_mat, collection)


def create_front_wall_with_openings(name: str, origin, rotation_z: float, width: float, depth: float, wall_height: float, wall_material, openings, collection: str):
    """Build a front wall from pieces so door/window placements are real gaps."""
    thickness = 0.08
    y = -depth / 2.0
    edges = [-width / 2.0]
    for opening in openings:
        edges.extend([opening["x"] - opening["w"] / 2.0, opening["x"] + opening["w"] / 2.0])
    edges.append(width / 2.0)
    edges = sorted(clamp(edge, -width / 2.0, width / 2.0) for edge in edges)

    for index in range(len(edges) - 1):
        span = edges[index + 1] - edges[index]
        midpoint = (edges[index] + edges[index + 1]) / 2.0
        inside_opening = any((opening["x"] - opening["w"] / 2.0) < midpoint < (opening["x"] + opening["w"] / 2.0) for opening in openings)
        if span > 0.035 and not inside_opening:
            x = (edges[index] + edges[index + 1]) / 2.0
            add_local_box(f"{name} Front Wall Span {index}", origin, rotation_z, (x, y, wall_height / 2.0), (span, thickness, wall_height), wall_material, collection)

    for index, opening in enumerate(openings):
        x = opening["x"]
        w = opening["w"]
        bottom = opening["bottom"]
        top = opening["bottom"] + opening["h"]
        if bottom > 0.05:
            add_local_box(f"{name} Front Wall Below Opening {index}", origin, rotation_z, (x, y, bottom / 2.0), (w, thickness, bottom), wall_material, collection)
        if top < wall_height - 0.04:
            add_local_box(f"{name} Front Wall Above Opening {index}", origin, rotation_z, (x, y, (top + wall_height) / 2.0), (w, thickness, wall_height - top), wall_material, collection)


def create_table(name: str, origin, rotation_z: float, local_pos, materials, collection: str, size=(0.58, 0.38, 0.08)):
    wood = materials["wood"]
    add_local_box(f"{name} Table Top", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.32), size, wood, collection)
    for xoff in (-size[0] * 0.38, size[0] * 0.38):
        for yoff in (-size[1] * 0.34, size[1] * 0.34):
            add_local_box(f"{name} Table Leg", origin, rotation_z, (local_pos[0] + xoff, local_pos[1] + yoff, local_pos[2] + 0.17), (0.045, 0.045, 0.3), wood, collection)


def create_chair(name: str, origin, rotation_z: float, local_pos, materials, collection: str, angle: float = 0.0):
    wood = materials["wood"]
    rot = rotation_z + angle
    world = local_to_world(origin, rotation_z, local_pos)
    add_box(f"{name} Seat", (world[0], world[1], world[2] + 0.22), (0.22, 0.22, 0.05), wood, rot, collection)
    back = local_to_world(origin, rotation_z, (local_pos[0], local_pos[1] + 0.1, local_pos[2] + 0.38))
    add_box(f"{name} Back", back, (0.22, 0.045, 0.32), wood, rot, collection)


def create_bed(name: str, origin, rotation_z: float, local_pos, materials, collection: str, angle: float = 0.0, double: bool = False):
    rot = rotation_z + angle
    length = 0.72 if not double else 0.86
    width = 0.42 if not double else 0.62
    world = local_to_world(origin, rotation_z, local_pos)
    add_box(f"{name} Bed Frame", (world[0], world[1], world[2] + 0.16), (width, length, 0.14), materials["wood"], rot, collection)
    add_box(f"{name} Mattress", (world[0], world[1], world[2] + 0.26), (width * 0.9, length * 0.82, 0.08), materials["fabric"], rot, collection)
    pillow = local_to_world(origin, rotation_z, (local_pos[0], local_pos[1] + length * 0.28, local_pos[2] + 0.34))
    add_box(f"{name} Pillow", pillow, (width * 0.58, 0.16, 0.055), materials["pillow"], rot, collection)


def create_chest(name: str, origin, rotation_z: float, local_pos, materials, collection: str, scale: float = 1.0):
    add_local_box(f"{name} Storage Chest", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.14 * scale), (0.34 * scale, 0.22 * scale, 0.24 * scale), materials["dark_wood"], collection)
    add_local_box(f"{name} Chest Lid", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.27 * scale), (0.38 * scale, 0.24 * scale, 0.045 * scale), materials["wood"], collection)


def create_shelf(name: str, origin, rotation_z: float, local_pos, materials, collection: str, width: float = 0.62):
    add_local_box(f"{name} Shelf Back", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.48), (width, 0.045, 0.52), materials["dark_wood"], collection)
    for zoff in (0.3, 0.5, 0.7):
        add_local_box(f"{name} Shelf Board", origin, rotation_z, (local_pos[0], local_pos[1] - 0.025, local_pos[2] + zoff), (width, 0.16, 0.035), materials["wood"], collection)
    for index, xoff in enumerate((-0.22, 0.0, 0.2), start=1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.04, depth=0.08, location=local_to_world(origin, rotation_z, (local_pos[0] + xoff, local_pos[1] - 0.08, local_pos[2] + 0.76)))
        pot = bpy.context.object
        pot.name = f"{name} Pot {index}"
        pot.data.materials.append(materials["clay"])
        link_to_collection(pot, collection)


def create_fireplace(name: str, origin, rotation_z: float, local_pos, materials, collection: str, stove: bool = False):
    if stove:
        add_local_box(f"{name} Iron Stove", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.22), (0.3, 0.25, 0.28), materials["black"], collection)
        add_local_box(f"{name} Stove Pipe", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.58), (0.1, 0.1, 0.48), materials["black"], collection)
    else:
        add_local_box(f"{name} Stone Hearth", origin, rotation_z, (local_pos[0], local_pos[1], local_pos[2] + 0.16), (0.48, 0.18, 0.32), materials["rock"], collection)
        add_local_box(f"{name} Chimney Breast", origin, rotation_z, (local_pos[0], local_pos[1] + 0.02, local_pos[2] + 0.5), (0.36, 0.14, 0.58), materials["rock"], collection)
        add_local_box(f"{name} Fire Glow", origin, rotation_z, (local_pos[0], local_pos[1] - 0.08, local_pos[2] + 0.14), (0.22, 0.04, 0.14), materials["fire"], collection)


def create_house_base(
    name: str,
    center,
    rotation_z: float,
    width: float,
    depth: float,
    wall_height: float,
    roof_height: float,
    wall_material,
    roof_material,
    materials,
    collection: str,
    roof_style: str = "gable",
    door_offset: float = 0.0,
    door_width: float = 0.34,
    door_height: float = 0.68,
    front_windows: int = 2,
    side_extension: bool = False,
    chimney: bool = False,
    porch: bool = True,
):
    """Build a furnished-house-ready shell with segmented walls and separated roof."""
    origin = (center[0], center[1], island_height(center[0], center[1]) + 0.09)
    foundation_h = 0.16
    wall_z = foundation_h
    wall_origin = (origin[0], origin[1], origin[2] + wall_z)

    add_local_box(f"{name} Interior Floor", origin, rotation_z, (0.0, 0.0, 0.02), (width, depth, 0.04), materials["floor"], collection)
    add_local_box(f"{name} Stone Foundation", origin, rotation_z, (0.0, 0.0, foundation_h / 2.0), (width + 0.16, depth + 0.16, foundation_h), materials["rock"], collection)

    openings = [{"x": door_offset * width, "w": door_width, "bottom": 0.0, "h": door_height}]
    window_xs = [-width * 0.28, width * 0.28] if front_windows == 2 else [-width * 0.33, 0.0, width * 0.33]
    for x in window_xs[:front_windows]:
        if abs(x - door_offset * width) > door_width * 0.78:
            openings.append({"x": x, "w": 0.28, "bottom": 0.38, "h": 0.28})

    create_front_wall_with_openings(f"{name}", wall_origin, rotation_z, width, depth, wall_height, wall_material, openings, collection)
    add_local_box(f"{name} Back Wall", wall_origin, rotation_z, (0.0, depth / 2.0, wall_height / 2.0), (width, 0.08, wall_height), wall_material, collection)
    add_local_box(f"{name} Left Wall", wall_origin, rotation_z, (-width / 2.0, 0.0, wall_height / 2.0), (0.08, depth, wall_height), wall_material, collection)
    add_local_box(f"{name} Right Wall", wall_origin, rotation_z, (width / 2.0, 0.0, wall_height / 2.0), (0.08, depth, wall_height), wall_material, collection)

    door_center = (door_offset * width, -depth / 2.0 - 0.045, door_height / 2.0)
    add_local_box(f"{name} Wooden Front Door", wall_origin, rotation_z, door_center, (door_width * 0.88, 0.045, door_height * 0.92), materials["door"], collection)
    add_local_box(f"{name} Door Handle", wall_origin, rotation_z, (door_center[0] + door_width * 0.28, door_center[1] - 0.025, door_center[2]), (0.035, 0.03, 0.035), materials["metal"], collection)

    for index, opening in enumerate(openings[1:], start=1):
        create_window_detail(
            f"{name} Front Window {index}",
            wall_origin,
            rotation_z,
            (opening["x"], -depth / 2.0 - 0.055, opening["bottom"] + opening["h"] / 2.0),
            opening["w"] * 0.84,
            opening["h"] * 0.86,
            materials,
            "front",
            collection,
        )
    create_window_detail(f"{name} Side Window Left", wall_origin, rotation_z, (-width / 2.0 - 0.05, -depth * 0.15, 0.66), 0.26, 0.26, materials, "side", collection)
    create_window_detail(f"{name} Side Window Right", wall_origin, rotation_z, (width / 2.0 + 0.05, depth * 0.12, 0.66), 0.26, 0.26, materials, "side", collection)

    roof = create_roof(f"{name} Separated Inspectable Roof", origin, rotation_z, width + 0.16, depth + 0.16, wall_z + wall_height, roof_height, roof_material, roof_style, collection)
    roof["is_removable_roof"] = True

    if porch:
        add_local_box(f"{name} Porch Step", origin, rotation_z, (door_offset * width, -depth / 2.0 - 0.36, 0.09), (0.66, 0.36, 0.12), materials["wood"], collection)
    if chimney:
        add_local_box(f"{name} Chimney", origin, rotation_z, (width * 0.28, depth * 0.15, wall_z + wall_height + roof_height * 0.72), (0.18, 0.18, 0.62), materials["rock"], collection)
    if side_extension:
        add_local_box(f"{name} Side Extension", origin, rotation_z, (width / 2.0 + 0.38, -depth * 0.1, 0.32), (0.68, depth * 0.55, 0.48), wall_material, collection)
        ext_origin = local_to_world(origin, rotation_z, (width / 2.0 + 0.38, -depth * 0.1, 0.0))
        create_roof(f"{name} Side Extension Roof", ext_origin, rotation_z, 0.78, depth * 0.65, 0.56, 0.2, roof_material, "shed", collection)

    return {"origin": origin, "wall_origin": wall_origin, "width": width, "depth": depth, "wall_height": wall_height, "rotation": rotation_z}


def furnish_house_interior(name: str, house, materials, profile: str, collection: str = "Interiors"):
    """Give every house readable domestic interior furniture and owner-specific clutter."""
    origin = house["origin"]
    rot = house["rotation"]
    width = house["width"]
    depth = house["depth"]

    create_table(f"{name} Main Room", origin, rot, (-width * 0.08, -depth * 0.08, 0.05), materials, collection)
    chair_count = 4 if profile in {"family", "farmhouse", "formal"} else 2
    chair_positions = [(-0.42, -0.08, math.radians(90)), (0.28, -0.08, -math.radians(90)), (-0.08, -0.42, 0.0), (-0.08, 0.26, math.pi)]
    for index, (xoff, yoff, angle) in enumerate(chair_positions[:chair_count], start=1):
        create_chair(f"{name} Chair {index}", origin, rot, (xoff, yoff, 0.05), materials, collection, angle)

    create_bed(f"{name} Bed", origin, rot, (width * 0.22, depth * 0.28, 0.05), materials, collection, math.radians(90), double=profile in {"family", "formal", "farmhouse"})
    create_chest(f"{name}", origin, rot, (-width * 0.34, depth * 0.26, 0.05), materials, collection)
    create_shelf(f"{name} Pottery", origin, rot, (-width * 0.32, depth / 2.0 - 0.08, 0.05), materials, collection, 0.58)
    create_fireplace(f"{name} Hearth", origin, rot, (width * 0.32, -depth / 2.0 + 0.12, 0.05), materials, collection, stove=profile in {"cottage", "coastal_hut", "rustic"})

    if profile in {"family", "farmhouse", "formal"}:
        create_table(f"{name} Kitchen Prep", origin, rot, (-width * 0.32, -depth * 0.32, 0.05), materials, collection, (0.48, 0.24, 0.07))
        for i, xoff in enumerate((-0.18, 0.0, 0.18), start=1):
            add_local_box(f"{name} Storage Jar {i}", origin, rot, (-width * 0.32 + xoff, -depth * 0.32, 0.48), (0.08, 0.08, 0.12), materials["clay"], collection)
    if profile in {"work", "rustic", "coastal_work"}:
        add_local_box(f"{name} Tool Rack", origin, rot, (-width / 2.0 + 0.08, -0.08, 0.74), (0.055, 0.58, 0.08), materials["dark_wood"], collection)
        for i, yoff in enumerate((-0.2, 0.0, 0.2), start=1):
            add_local_box(f"{name} Hanging Tool {i}", origin, rot, (-width / 2.0 + 0.04, yoff, 0.54), (0.04, 0.04, 0.28), materials["metal"], collection)
    if profile in {"cottage", "stone_cottage"}:
        add_local_box(f"{name} Woven Rug", origin, rot, (0.08, 0.05, 0.075), (0.58, 0.42, 0.025), materials["rug"], collection)


def create_detailed_house(name: str, center, rotation_z: float, variant: dict, materials, collection: str):
    """Create one non-repeating house and furnish its interior."""
    house = create_house_base(
        name,
        center,
        rotation_z,
        variant["width"],
        variant["depth"],
        variant["wall_height"],
        variant["roof_height"],
        materials[variant["wall_mat"]],
        materials[variant["roof_mat"]],
        materials,
        collection,
        variant.get("roof_style", "gable"),
        variant.get("door_offset", 0.0),
        variant.get("door_width", 0.34),
        variant.get("door_height", 0.68),
        variant.get("front_windows", 2),
        variant.get("side_extension", False),
        variant.get("chimney", False),
        variant.get("porch", True),
    )
    furnish_house_interior(name, house, materials, variant.get("interior", "family"))
    return house


def create_anvil(name: str, location, materials, collection: str, rotation_z: float = 0.0):
    add_box(f"{name} Anvil Base", (location[0], location[1], location[2] + 0.14), (0.16, 0.16, 0.28), materials["metal"], rotation_z, collection)
    add_box(f"{name} Anvil Body", (location[0], location[1], location[2] + 0.33), (0.42, 0.18, 0.12), materials["metal"], rotation_z, collection)
    add_box(f"{name} Anvil Horn", (location[0] + math.cos(rotation_z) * 0.27, location[1] + math.sin(rotation_z) * 0.27, location[2] + 0.34), (0.2, 0.1, 0.08), materials["metal"], rotation_z, collection)


def create_sack(name: str, location, materials, collection: str, scale: float = 1.0):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=0.15 * scale, location=(location[0], location[1], location[2] + 0.16 * scale))
    sack = bpy.context.object
    sack.name = f"{name} Sack"
    sack.scale.z *= 1.25
    sack.data.materials.append(materials["sack"])
    link_to_collection(sack, collection)


def create_cart(name: str, center, rotation_z: float, materials, collection: str = "Props"):
    z = island_height(center[0], center[1]) + 0.13
    add_box(f"{name} Cart Bed", (center[0], center[1], z + 0.18), (0.82, 0.42, 0.16), materials["wood"], rotation_z, collection)
    for side in (-1.0, 1.0):
        wheel_pos = local_to_world((center[0], center[1], z), rotation_z, (-0.24, side * 0.27, 0.14))
        bpy.ops.mesh.primitive_torus_add(major_radius=0.13, minor_radius=0.025, major_segments=12, minor_segments=4, location=wheel_pos, rotation=(math.radians(90), 0.0, rotation_z))
        wheel = bpy.context.object
        wheel.name = f"{name} Wooden Wheel"
        wheel.data.materials.append(materials["dark_wood"])
        link_to_collection(wheel, collection)
    add_box(f"{name} Cart Handle", local_to_world((center[0], center[1], z), rotation_z, (0.48, 0.0, 0.22)), (0.55, 0.055, 0.055), materials["wood"], rotation_z, collection)


def create_blacksmith(name: str, center, rotation_z: float, materials):
    house = create_house_base(
        name,
        center,
        rotation_z,
        1.95,
        1.35,
        0.88,
        0.36,
        materials["wall_timber"],
        materials["roof_gray"],
        materials,
        "Village_1",
        "shed",
        0.0,
        0.72,
        0.78,
        1,
        False,
        True,
        False,
    )
    origin = house["origin"]
    create_fireplace(f"{name} Forge", origin, rotation_z, (-0.55, -0.46, 0.05), materials, "Interiors", False)
    create_table(f"{name} Heavy Workbench", origin, rotation_z, (0.45, 0.26, 0.05), materials, "Interiors", (0.72, 0.34, 0.08))
    create_anvil(f"{name} Interior", local_to_world(origin, rotation_z, (0.08, -0.18, 0.05)), materials, "Interiors", rotation_z)
    add_local_box(f"{name} Hammer Rack", origin, rotation_z, (0.86, -0.52, 0.64), (0.52, 0.06, 0.08), materials["dark_wood"], "Interiors")
    for i, xoff in enumerate((-0.16, 0.0, 0.16), start=1):
        add_local_box(f"{name} Hanging Hammer {i}", origin, rotation_z, (0.86 + xoff, -0.55, 0.46), (0.045, 0.045, 0.26), materials["metal"], "Interiors")

    yard = local_to_world(origin, rotation_z, (0.0, -1.04, 0.0))
    create_anvil(f"{name} Yard", (yard[0] - 0.28, yard[1], yard[2]), materials, "Props", rotation_z)
    add_box(f"{name} Water Trough", (yard[0] + 0.34, yard[1] - 0.08, yard[2] + 0.12), (0.56, 0.22, 0.18), materials["dark_wood"], rotation_z, "Props")
    for i in range(5):
        bar = local_to_world(origin, rotation_z, (-0.82 + i * 0.08, -1.08, 0.1 + i * 0.02))
        add_box(f"{name} Stacked Metal Bar {i + 1}", bar, (0.52, 0.035, 0.035), materials["metal"], rotation_z + 0.1, "Props")
    bpy.ops.mesh.primitive_torus_add(major_radius=0.18, minor_radius=0.035, location=local_to_world(origin, rotation_z, (0.82, -1.02, 0.23)), rotation=(math.radians(90), 0.0, rotation_z))
    wheel = bpy.context.object
    wheel.name = f"{name} Wagon Wheel"
    wheel.data.materials.append(materials["dark_wood"])
    link_to_collection(wheel, "Props")
    return house


def create_stable(name: str, center, rotation_z: float, materials):
    house = create_house_base(name, center, rotation_z, 2.15, 1.45, 0.82, 0.34, materials["stable_wall"], materials["roof_brown"], materials, "Village_1", "gable", 0.0, 0.9, 0.78, 1, False, False, False)
    origin = house["origin"]
    for offset in (-0.42, 0.28):
        add_local_box(f"{name} Stall Divider", origin, rotation_z, (offset, 0.08, 0.38), (0.06, 1.12, 0.62), materials["wood"], "Interiors")
    for index, xoff in enumerate((-0.72, 0.0, 0.72), start=1):
        add_local_box(f"{name} Hay Bale {index}", origin, rotation_z, (xoff, 0.46, 0.16), (0.38, 0.28, 0.22), materials["hay"], "Interiors")
        add_local_box(f"{name} Stall Trough {index}", origin, rotation_z, (xoff, -0.48, 0.18), (0.42, 0.16, 0.16), materials["dark_wood"], "Interiors")
    fence_points = []
    for local in [(-1.25, -1.02), (-0.2, -1.25), (1.08, -1.05), (1.25, -0.25)]:
        p = local_to_world(origin, rotation_z, (local[0], local[1], 0.0))
        fence_points.append((p[0], p[1]))
    create_fence(f"{name} Paddock Fence", fence_points, materials["wood"], 0.44)
    trough = local_to_world(origin, rotation_z, (1.45, -0.52, 0.0))
    add_box(f"{name} Outdoor Trough", (trough[0], trough[1], trough[2] + 0.12), (0.64, 0.22, 0.16), materials["dark_wood"], rotation_z, "Props")
    return house


def create_granary(name: str, center, rotation_z: float, materials):
    house = create_house_base(name, center, rotation_z, 1.45, 1.1, 0.76, 0.32, materials["wall_warm"], materials["roof_brown"], materials, "Village_1", "gable", -0.12, 0.42, 0.64, 1, False, False, True)
    origin = house["origin"]
    for xoff in (-0.52, 0.52):
        for yoff in (-0.38, 0.38):
            add_local_box(f"{name} Raised Stone Pier", origin, rotation_z, (xoff, yoff, -0.05), (0.18, 0.18, 0.32), materials["rock"], "Village_1")
    for i, pos in enumerate([(-0.38, -0.24), (-0.1, -0.18), (0.22, -0.22), (0.42, 0.14)], start=1):
        create_sack(f"{name} Grain {i}", local_to_world(origin, rotation_z, (pos[0], pos[1], 0.05)), materials, "Interiors", 0.9)
    for i, pos in enumerate([(-0.44, 0.36), (0.0, 0.36), (0.44, 0.36)], start=1):
        create_prop_crate(f"{name} Storage Crate {i}", local_to_world(origin, rotation_z, (pos[0], pos[1], 0.05)), materials["crate"], materials["dark_wood"], 0.78, rotation_z)
    add_local_box(f"{name} Farm Tool Rack", origin, rotation_z, (0.64, -0.12, 0.58), (0.06, 0.52, 0.08), materials["dark_wood"], "Interiors")
    return house


def create_bakehouse(name: str, center, rotation_z: float, materials):
    house = create_house_base(name, center, rotation_z, 1.78, 1.2, 0.86, 0.34, materials["wall_warm"], materials["roof_red"], materials, "Village_1", "hip", 0.0, 0.46, 0.7, 2, False, True, True)
    origin = house["origin"]
    add_local_box(f"{name} Brick Oven Base", origin, rotation_z, (-0.58, 0.25, 0.22), (0.52, 0.46, 0.34), materials["clay"], "Interiors")
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.31, location=local_to_world(origin, rotation_z, (-0.58, 0.25, 0.55)))
    oven = bpy.context.object
    oven.name = f"{name} Domed Oven"
    oven.scale.z *= 0.6
    oven.data.materials.append(materials["clay"])
    link_to_collection(oven, "Interiors")
    create_table(f"{name} Flour Prep Table", origin, rotation_z, (0.25, -0.22, 0.05), materials, "Interiors", (0.82, 0.34, 0.08))
    for i, pos in enumerate([(0.52, 0.32), (0.24, 0.32), (0.5, 0.05)], start=1):
        create_sack(f"{name} Flour Sack {i}", local_to_world(origin, rotation_z, (pos[0], pos[1], 0.05)), materials, "Interiors", 0.78)
    create_shelf(f"{name} Bread Shelf", origin, rotation_z, (0.0, 0.52, 0.05), materials, "Interiors", 0.9)
    return house


def create_fish_market(name: str, center, rotation_z: float, materials):
    origin = (center[0], center[1], island_height(center[0], center[1]) + 0.1)
    add_local_box(f"{name} Packed Sand Floor", origin, rotation_z, (0.0, 0.0, 0.02), (1.95, 1.22, 0.04), materials["path"], "Village_2")
    for xoff in (-0.82, 0.82):
        for yoff in (-0.5, 0.5):
            add_local_box(f"{name} Timber Post", origin, rotation_z, (xoff, yoff, 0.46), (0.08, 0.08, 0.86), materials["wood"], "Village_2")
    create_roof(f"{name} Open Shelter Roof", origin, rotation_z, 2.14, 1.42, 0.86, 0.32, materials["roof_blue"], "gable", "Village_2")
    for i, xoff in enumerate((-0.44, 0.44), start=1):
        create_table(f"{name} Fish Display Table {i}", origin, rotation_z, (xoff, -0.05, 0.05), materials, "Interiors", (0.62, 0.36, 0.08))
        for fish_idx in range(3):
            add_local_box(f"{name} Display Fish {i}-{fish_idx}", origin, rotation_z, (xoff - 0.18 + fish_idx * 0.18, -0.05, 0.43), (0.13, 0.035, 0.035), materials["fish"], "Interiors")
    for i, local in enumerate([(-0.76, -0.62), (0.72, -0.6), (0.85, 0.48)], start=1):
        create_prop_crate(f"{name} Market Crate {i}", local_to_world(origin, rotation_z, (local[0], local[1], 0.05)), materials["crate"], materials["dark_wood"], 0.9, rotation_z)
    return {"origin": origin}


def create_prop_rope(name: str, location, materials, collection: str = "Props", scale: float = 1.0):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.14 * scale, minor_radius=0.025 * scale, major_segments=18, minor_segments=6, location=location)
    rope = bpy.context.object
    rope.name = f"{name} Rope Coil"
    rope.data.materials.append(materials["rope"])
    link_to_collection(rope, collection)
    return rope


def create_prop_net(name: str, center, rope_material, rotation_z: float = 0.0, scale: float = 1.0):
    return create_fishing_net(name, center, rope_material, rotation_z, scale)


def create_net_shed(name: str, center, rotation_z: float, materials):
    house = create_house_base(name, center, rotation_z, 1.32, 1.0, 0.68, 0.28, materials["wall_fishing"], materials["roof_gray"], materials, "Village_2", "shed", 0.0, 0.5, 0.58, 1, False, False, False)
    origin = house["origin"]
    create_fishing_net(f"{name} Floor Net", (center[0], center[1]), materials["rope"], rotation_z, 0.7)
    for i, yoff in enumerate((-0.24, 0.0, 0.24), start=1):
        add_local_box(f"{name} Hanging Net {i}", origin, rotation_z, (-0.52, yoff, 0.52), (0.035, 0.32, 0.42), materials["rope"], "Interiors")
    for i, yoff in enumerate((-0.32, 0.0, 0.32), start=1):
        add_local_box(f"{name} Fishing Pole {i}", origin, rotation_z, (0.52, yoff, 0.44), (0.035, 0.035, 0.76), materials["wood"], "Interiors")
    create_prop_rope(f"{name} Interior", local_to_world(origin, rotation_z, (0.05, -0.22, 0.1)), materials, "Interiors", 0.78)
    return house


def create_smokehouse(name: str, center, rotation_z: float, materials):
    house = create_house_base(name, center, rotation_z, 1.05, 0.92, 0.76, 0.26, materials["dark_wood"], materials["roof_gray"], materials, "Village_2", "gable", 0.0, 0.34, 0.58, 0, False, True, False)
    origin = house["origin"]
    add_local_box(f"{name} Smoke Pit", origin, rotation_z, (0.0, -0.24, 0.12), (0.34, 0.28, 0.12), materials["black"], "Interiors")
    add_local_box(f"{name} Ember Glow", origin, rotation_z, (0.0, -0.24, 0.2), (0.22, 0.16, 0.04), materials["fire"], "Interiors")
    for zoff in (0.46, 0.64):
        add_local_box(f"{name} Drying Rack", origin, rotation_z, (0.0, 0.08, zoff), (0.72, 0.05, 0.04), materials["wood"], "Interiors")
    for i, xoff in enumerate((-0.26, -0.08, 0.1, 0.28), start=1):
        add_local_box(f"{name} Hanging Fish {i}", origin, rotation_z, (xoff, 0.08, 0.54), (0.055, 0.025, 0.22), materials["fish"], "Interiors")
    return house


def create_boat_workshop(name: str, center, rotation_z: float, materials):
    origin = (center[0], center[1], island_height(center[0], center[1]) + 0.1)
    add_local_box(f"{name} Work Yard Floor", origin, rotation_z, (0.0, 0.0, 0.02), (2.0, 1.24, 0.04), materials["path"], "Village_2")
    for xoff in (-0.82, 0.82):
        for yoff in (-0.5, 0.5):
            add_local_box(f"{name} Open Shed Post", origin, rotation_z, (xoff, yoff, 0.46), (0.08, 0.08, 0.86), materials["wood"], "Village_2")
    create_roof(f"{name} Open Shed Roof", origin, rotation_z, 2.18, 1.38, 0.82, 0.28, materials["roof_gray"], "shed", "Village_2")
    create_table(f"{name} Tool Workbench", origin, rotation_z, (-0.52, 0.18, 0.05), materials, "Interiors", (0.74, 0.32, 0.08))
    for i, yoff in enumerate((-0.34, -0.18, 0.0, 0.18), start=1):
        add_local_box(f"{name} Spare Plank {i}", origin, rotation_z, (0.42, yoff, 0.13 + i * 0.025), (0.92, 0.055, 0.035), materials["wood"], "Interiors")
    for i, xoff in enumerate((-0.28, 0.18), start=1):
        add_local_box(f"{name} Sawhorse {i}", origin, rotation_z, (xoff, -0.38, 0.24), (0.38, 0.08, 0.2), materials["dark_wood"], "Interiors")
    partial = local_to_world(origin, rotation_z, (0.22, -0.38, 0.42))
    create_boat(f"{name} Partial Hull Frame", partial, rotation_z, materials["dark_wood"], materials["sail"], materials["wood"], 0.55, "rowboat")
    return {"origin": origin}


def create_village(name: str, center, roof_material, wall_material, door_material, window_material, path_material, materials, seed: int):
    """Create Village 1: an inland settlement with a well, square, houses, and civic buildings."""
    rng = random.Random(seed)
    square_center = center
    create_flat_patch(f"{name} Irregular Stone-Dirt Village Square", square_center, 2.55, 2.25, path_material, math.radians(7), 0.085, 8)
    create_flat_patch(f"{name} Worn Stone Paving Around Well", square_center, 1.05, 0.9, materials["paving"], math.radians(12), 0.105, 8)
    create_well(f"{name} Central Well", square_center, materials["rock"], materials["wood"], materials["roof_thatch"], materials["bucket"])

    for index, local in enumerate([(-0.72, -0.46), (0.78, 0.48)], start=1):
        p = (center[0] + local[0], center[1] + local[1], island_height(center[0] + local[0], center[1] + local[1]) + 0.18)
        add_box(f"{name} Square Bench {index} Seat", p, (0.58, 0.14, 0.08), materials["wood"], math.radians(8 + index * 58), "Village_1")
    add_box(f"{name} Notice Board Post", (center[0] - 1.12, center[1] + 0.76, island_height(center[0] - 1.12, center[1] + 0.76) + 0.42), (0.08, 0.08, 0.72), materials["wood"], 0.0, "Props")
    add_box(f"{name} Notice Board Face", (center[0] - 1.12, center[1] + 0.76, island_height(center[0] - 1.12, center[1] + 0.76) + 0.73), (0.5, 0.06, 0.34), materials["dark_wood"], math.radians(18), "Props")
    for index, local in enumerate([(0.9, -0.58), (1.05, -0.33), (-0.95, 0.42)], start=1):
        create_prop_barrel(f"{name} Square Bucket Barrel {index}", (center[0] + local[0], center[1] + local[1], island_height(center[0] + local[0], center[1] + local[1]) + 0.08), materials["wood"], materials["metal"], 0.6)

    house_points = []
    house_specs = [
        ("House 1 North Family House", (0.0, 2.62), {"width": 1.42, "depth": 1.12, "wall_height": 0.88, "roof_height": 0.62, "wall_mat": "wall_plaster", "roof_mat": "roof_red", "roof_style": "gable", "door_offset": -0.08, "front_windows": 2, "side_extension": True, "chimney": True, "interior": "family"}),
        ("House 2 Northeast Herb Cottage", (1.88, 1.78), {"width": 0.92, "depth": 1.16, "wall_height": 0.76, "roof_height": 0.48, "wall_mat": "wall_cream", "roof_mat": "roof_orange", "roof_style": "gable", "door_offset": 0.18, "front_windows": 1, "interior": "cottage"}),
        ("House 3 East Formal House", (2.72, 0.08), {"width": 1.58, "depth": 1.22, "wall_height": 0.92, "roof_height": 0.46, "wall_mat": "wall_stone_plaster", "roof_mat": "roof_brown", "roof_style": "hip", "door_width": 0.44, "front_windows": 2, "chimney": True, "interior": "formal"}),
        ("House 4 Southeast Road House", (2.1, -1.72), {"width": 1.18, "depth": 1.02, "wall_height": 0.76, "roof_height": 0.36, "wall_mat": "wall_yellow", "roof_mat": "roof_red_brown", "roof_style": "gable", "door_offset": 0.26, "front_windows": 1, "interior": "family"}),
        ("House 5 South Farmhouse", (0.0, -2.72), {"width": 1.72, "depth": 1.18, "wall_height": 0.86, "roof_height": 0.54, "wall_mat": "wall_stone_plaster", "roof_mat": "roof_brown", "roof_style": "gable", "door_offset": -0.14, "front_windows": 3, "chimney": True, "interior": "farmhouse"}),
        ("House 6 Southwest Timber House", (-2.06, -1.78), {"width": 1.22, "depth": 1.18, "wall_height": 0.8, "roof_height": 0.38, "wall_mat": "wall_timber", "roof_mat": "roof_muted", "roof_style": "shed", "door_offset": 0.18, "front_windows": 1, "side_extension": True, "interior": "work"}),
        ("House 7 West Limewash House", (-2.78, 0.05), {"width": 1.36, "depth": 1.08, "wall_height": 0.98, "roof_height": 0.58, "wall_mat": "wall_lime", "roof_mat": "roof_red", "roof_style": "hip", "front_windows": 2, "porch": True, "interior": "formal"}),
        ("House 8 Northwest Stone Cottage", (-1.88, 1.9), {"width": 1.02, "depth": 0.96, "wall_height": 0.72, "roof_height": 0.4, "wall_mat": "wall_stone", "roof_mat": "roof_gray_red", "roof_style": "gable", "door_offset": -0.18, "front_windows": 1, "interior": "stone_cottage"}),
    ]

    for index, (label, offset, variant) in enumerate(house_specs, start=1):
        x = center[0] + offset[0]
        y = center[1] + offset[1]
        dx = center[0] - x
        dy = center[1] - y
        rotation = math.atan2(dx, -dy) + rng.uniform(-0.06, 0.06)
        create_detailed_house(f"{name} {label}", (x, y), rotation, variant, materials, "Village_1")
        house_points.append((x, y))

        mid_x = (center[0] + x) / 2.0 + rng.uniform(-0.22, 0.22)
        mid_y = (center[1] + y) / 2.0 + rng.uniform(-0.22, 0.22)
        create_road_or_path(f"{name} Footpath To House {index}", [center, (mid_x, mid_y), (x, y)], 0.18, path_material, 0.09)

        if index in (2, 5, 7):
            prop_x, prop_y, _prop_z = local_to_world((x, y, island_height(x, y) + 0.09), rotation, (0.55, 0.55, 0.0))
            create_prop_crate(f"{name} House {index} Crate", (prop_x, prop_y, island_height(prop_x, prop_y) + 0.09), materials["wood"], materials["dark_wood"], 0.9, rotation)
        if index in (1, 4, 8):
            garden_x, garden_y, _garden_z = local_to_world((x, y, island_height(x, y) + 0.09), rotation, (-0.72, 0.58, 0.0))
            create_garden_patch(f"{name} House {index}", (garden_x, garden_y), materials["garden_soil"], materials["garden_green"], rotation + rng.uniform(-0.15, 0.15), 0.85)
        if index in (3, 6):
            wood_x, wood_y, _wood_z = local_to_world((x, y, island_height(x, y) + 0.09), rotation, (0.7, -0.25, 0.0))
            create_prop_woodpile(f"{name} House {index} Chopped Wood", (wood_x, wood_y, island_height(wood_x, wood_y) + 0.09), materials["wood"], 0.9, rotation)
        if index in (2, 6):
            p1 = local_to_world((x, y, island_height(x, y) + 0.09), rotation, (-0.92, 0.82, 0.0))
            p2 = local_to_world((x, y, island_height(x, y) + 0.09), rotation, (-0.2, 1.02, 0.0))
            p3 = local_to_world((x, y, island_height(x, y) + 0.09), rotation, (0.48, 0.82, 0.0))
            create_fence(f"{name} House {index} Garden Fence", [(p1[0], p1[1]), (p2[0], p2[1]), (p3[0], p3[1])], materials["wood"])

    blacksmith_center = (center[0] + 2.95, center[1] - 2.55)
    stable_center = (center[0] - 2.95, center[1] - 2.3)
    granary_center = (center[0] - 3.38, center[1] + 1.05)
    bakehouse_center = (center[0] - 2.7, center[1] + 2.62)
    create_blacksmith(f"{name} Blacksmith Workshop", blacksmith_center, math.radians(138), materials)
    create_stable(f"{name} Stable", stable_center, math.radians(36), materials)
    create_granary(f"{name} Raised Granary", granary_center, math.radians(88), materials)
    create_bakehouse(f"{name} Communal Bakehouse", bakehouse_center, math.radians(148), materials)

    for struct_index, point in enumerate([blacksmith_center, stable_center, granary_center, bakehouse_center], start=1):
        create_road_or_path(f"{name} Path To Structure {struct_index}", [center, ((center[0] + point[0]) / 2.0, (center[1] + point[1]) / 2.0), point], 0.2, path_material, 0.09)

    create_road_or_path(
        f"{name} Curved Road From Square",
        [center, (center[0] + 1.0, center[1] - 0.35), (center[0] + 2.0, center[1] - 0.6)],
        0.34,
        path_material,
        0.095,
    )

    create_cart(f"{name} Small Farm Cart", (center[0] - 1.2, center[1] - 1.08), math.radians(18), materials)
    p1 = (center[0] + 1.45, center[1] - 2.12)
    p2 = (center[0] + 2.25, center[1] - 2.0)
    add_box(f"{name} Laundry Post A", (p1[0], p1[1], island_height(p1[0], p1[1]) + 0.42), (0.06, 0.06, 0.72), materials["wood"], 0.0, "Props")
    add_box(f"{name} Laundry Post B", (p2[0], p2[1], island_height(p2[0], p2[1]) + 0.42), (0.06, 0.06, 0.72), materials["wood"], 0.0, "Props")
    add_box(f"{name} Laundry Line", ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0, island_height((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0) + 0.78), (0.82, 0.025, 0.025), materials["rope"], math.atan2(p2[1] - p1[1], p2[0] - p1[0]), "Props")
    for i, t in enumerate((0.25, 0.5, 0.75), start=1):
        x = p1[0] * (1 - t) + p2[0] * t
        y = p1[1] * (1 - t) + p2[1] * t
        add_box(f"{name} Hanging Laundry {i}", (x, y, island_height(x, y) + 0.62), (0.16, 0.02, 0.22), materials["fabric"], math.atan2(p2[1] - p1[1], p2[0] - p1[0]), "Props")

    for index in range(9):
        angle = math.tau * index / 9.0 + 0.15
        distance = rng.uniform(3.0, 3.7)
        x = center[0] + math.cos(angle) * distance
        y = center[1] + math.sin(angle) * distance
        if normalized_radius(x, y)[0] < BEACH_START - 0.08:
            create_tree(f"{name} Outer Shade Tree {index + 1}", (x, y, island_height(x, y) + 0.03), materials["trunk"], materials["leaves"], rng.uniform(0.72, 1.08))

    return {"center": center, "houses": house_points, "road_anchor": (center[0] + 2.0, center[1] - 0.6)}


def create_fishing_village(name: str, center, dock_info, roof_material, wall_material, door_material, window_material, path_material, materials, seed: int):
    """Create Village 2: a rugged fishing settlement organized around dock work."""
    rng = random.Random(seed)
    dock_shore = dock_info["shore"]
    dock_yard = dock_info["yard"]

    create_flat_patch(f"{name} Pebble Cove Yard", dock_yard, 3.05, 2.15, materials["pebbles"], dock_info["rotation"], 0.09, 8)
    create_flat_patch(f"{name} Worn Dock Work Ground", center, 2.65, 1.7, path_material, dock_info["rotation"] + 0.1, 0.105, 8)
    create_road_or_path(f"{name} Main Dock Track", [center, dock_yard, dock_shore], 0.52, path_material, 0.1)

    house_specs = [
        ("House 1 Dockmaster Fisher House", (-0.8, 0.82), {"width": 1.36, "depth": 1.1, "wall_height": 0.82, "roof_height": 0.42, "wall_mat": "wall_weathered_wood", "roof_mat": "roof_blue", "roof_style": "gable", "front_windows": 2, "porch": True, "interior": "coastal_work"}),
        ("House 2 North Lean-To Cottage", (-1.55, 1.52), {"width": 0.92, "depth": 1.18, "wall_height": 0.72, "roof_height": 0.36, "wall_mat": "wall_weathered_wood", "roof_mat": "roof_green_gray", "roof_style": "shed", "door_offset": 0.2, "front_windows": 1, "side_extension": True, "chimney": True, "interior": "coastal_hut"}),
        ("House 3 South Fishworker House", (1.35, 0.92), {"width": 1.46, "depth": 1.0, "wall_height": 0.72, "roof_height": 0.32, "wall_mat": "wall_dark_plank", "roof_mat": "roof_gray", "roof_style": "gable", "front_windows": 2, "interior": "coastal_work"}),
        ("House 4 Inland Family House", (-0.12, 2.0), {"width": 1.48, "depth": 1.18, "wall_height": 0.86, "roof_height": 0.42, "wall_mat": "wall_fishing_plaster", "roof_mat": "roof_blue_dark", "roof_style": "hip", "front_windows": 2, "chimney": True, "interior": "family"}),
        ("House 5 Northwest Road Cottage", (-2.18, 0.76), {"width": 1.02, "depth": 0.96, "wall_height": 0.74, "roof_height": 0.46, "wall_mat": "wall_weathered_wood", "roof_mat": "roof_green_gray", "roof_style": "gable", "front_windows": 1, "interior": "coastal_work"}),
        ("House 6 Southeast Beach Hut", (1.95, -0.22), {"width": 0.88, "depth": 0.86, "wall_height": 0.62, "roof_height": 0.3, "wall_mat": "wall_dark_wood", "roof_mat": "roof_muted", "roof_style": "shed", "front_windows": 1, "porch": False, "interior": "coastal_hut"}),
        ("House 7 Market House", (0.55, 1.18), {"width": 1.22, "depth": 1.0, "wall_height": 0.8, "roof_height": 0.38, "wall_mat": "wall_whitewashed", "roof_mat": "roof_blue", "roof_style": "gable", "front_windows": 2, "interior": "family"}),
    ]
    house_points = []
    coast_target = dock_info["end"]

    for index, (label, offsets, variant) in enumerate(house_specs, start=1):
        base = Vector((dock_yard[0], dock_yard[1], 0.0))
        side = dock_info["side"]
        inward = -dock_info["direction"]
        location_vec = base + side * offsets[0] + inward * offsets[1]
        x = location_vec.x + rng.uniform(-0.12, 0.12)
        y = location_vec.y + rng.uniform(-0.12, 0.12)
        rotation = math.atan2(coast_target[0] - x, -(coast_target[1] - y)) + rng.uniform(-0.15, 0.15)

        create_detailed_house(f"{name} {label}", (x, y), rotation, variant, materials, "Village_2")
        house_points.append((x, y))
        create_road_or_path(f"{name} Path To House {index}", [(x, y), ((x + dock_yard[0]) / 2.0, (y + dock_yard[1]) / 2.0), dock_yard], 0.16, path_material, 0.095)

    create_road_or_path(
        f"{name} Road Toward Inland Village",
        [center, (center[0] - 0.85, center[1] + 0.3), (center[0] - 1.55, center[1] + 0.55)],
        0.36,
        path_material,
        0.1,
    )

    fish_market_center = Vector((dock_yard[0], dock_yard[1], 0.0)) + dock_info["side"] * 0.92 - dock_info["direction"] * 0.26
    net_shed_center = Vector((dock_yard[0], dock_yard[1], 0.0)) - dock_info["side"] * 1.16 + dock_info["direction"] * 0.1
    smokehouse_center = Vector((dock_yard[0], dock_yard[1], 0.0)) + dock_info["side"] * 2.0 - dock_info["direction"] * 0.88
    repair_center = Vector((dock_yard[0], dock_yard[1], 0.0)) - dock_info["side"] * 1.75 - dock_info["direction"] * 0.62

    create_fish_market(f"{name} Fish Market Shelter", (fish_market_center.x, fish_market_center.y), dock_info["rotation"], materials)
    create_net_shed(f"{name} Net Storage Shed", (net_shed_center.x, net_shed_center.y), dock_info["rail_rotation"], materials)
    create_smokehouse(f"{name} Smokehouse Drying Hut", (smokehouse_center.x, smokehouse_center.y), dock_info["rotation"] + 0.4, materials)
    create_boat_workshop(f"{name} Boat Repair Workshop", (repair_center.x, repair_center.y), dock_info["rail_rotation"] + 0.08, materials)

    for index, point in enumerate([(fish_market_center.x, fish_market_center.y), (net_shed_center.x, net_shed_center.y), (smokehouse_center.x, smokehouse_center.y), (repair_center.x, repair_center.y)], start=1):
        create_road_or_path(f"{name} Work Path {index}", [dock_yard, ((dock_yard[0] + point[0]) / 2.0, (dock_yard[1] + point[1]) / 2.0), point], 0.18, path_material, 0.1)

    prop_base = Vector((dock_yard[0], dock_yard[1], island_height(dock_yard[0], dock_yard[1]) + 0.08))
    for index, offset in enumerate((-0.54, -0.28, 0.28, 0.58), start=1):
        point = prop_base + dock_info["side"] * offset + dock_info["direction"] * 0.18
        create_prop_crate(f"{name} Fishing Crate {index}", (point.x, point.y, point.z), materials["crate"], materials["dark_wood"], rng.uniform(0.78, 1.08), dock_info["rotation"])

    for index, offset in enumerate((-0.72, 0.76), start=1):
        point = prop_base + dock_info["side"] * offset - dock_info["direction"] * 0.42
        create_prop_barrel(f"{name} Salt Barrel {index}", (point.x, point.y, point.z), materials["wood"], materials["metal"], rng.uniform(0.85, 1.05))

    net_center = prop_base + dock_info["side"] * 0.1 - dock_info["direction"] * 0.82
    create_fishing_net(f"{name} Coiled Net", (net_center.x, net_center.y), materials["rope"], dock_info["rotation"] + 0.2, 0.92)
    create_prop_rope(f"{name} Dock Rope Coil", (prop_base.x + dock_info["side"].x * 0.55, prop_base.y + dock_info["side"].y * 0.55, prop_base.z + 0.08), materials, "Props", 0.9)

    rack_center = prop_base - dock_info["side"] * 0.92 - dock_info["direction"] * 0.28
    create_fish_drying_rack(f"{name} Fish Drying Rack", (rack_center.x, rack_center.y), materials["wood"], materials["fish"], dock_info["rotation"], 1.0)

    fence_start = prop_base - dock_info["side"] * 1.22 - dock_info["direction"] * 0.86
    fence_mid = prop_base - dock_info["side"] * 1.52 - dock_info["direction"] * 0.25
    fence_end = prop_base - dock_info["side"] * 1.35 + dock_info["direction"] * 0.32
    create_fence(
        f"{name} Low Working Fence",
        [(fence_start.x, fence_start.y), (fence_mid.x, fence_mid.y), (fence_end.x, fence_end.y)],
        materials["wood"],
        0.36,
    )

    create_cart(f"{name} Fish Handcart", (prop_base.x - dock_info["direction"].x * 1.25, prop_base.y - dock_info["direction"].y * 1.25), dock_info["rotation"], materials)
    for i, side_offset in enumerate((-1.0, 1.0), start=1):
        lantern = Vector((dock_yard[0], dock_yard[1], 0.0)) + dock_info["side"] * side_offset + dock_info["direction"] * 0.62
        add_box(f"{name} Lantern Post {i}", (lantern.x, lantern.y, island_height(lantern.x, lantern.y) + 0.56), (0.07, 0.07, 0.9), materials["wood"], 0.0, "Props")
        add_box(f"{name} Lantern Box {i}", (lantern.x, lantern.y, island_height(lantern.x, lantern.y) + 1.04), (0.16, 0.16, 0.18), materials["lantern"], 0.0, "Props")

    for index in range(7):
        angle = math.tau * index / 7.0 + 0.2
        x = center[0] + math.cos(angle) * rng.uniform(1.8, 2.65)
        y = center[1] + math.sin(angle) * rng.uniform(1.2, 2.0)
        radius, _theta = normalized_radius(x, y)
        if radius < BEACH_START - 0.02:
            create_tree(f"{name} Windbreak Tree {index + 1}", (x, y, island_height(x, y) + 0.03), materials["trunk"], materials["leaves"], rng.uniform(0.58, 0.9))

    return {"center": center, "houses": house_points, "road_anchor": (center[0] - 1.55, center[1] + 0.55), "dock_yard": dock_yard}


def create_boat(name: str, location, rotation_z: float, hull_material, sail_material, mast_material, scale: float = 1.0, boat_type: str = "rowboat"):
    """Create a low-poly boat with a pointed bow, stern, open interior, and seats."""
    length = 1.55 * scale
    width = 0.62 * scale
    height = 0.34 * scale
    rim_z = 0.08 * scale

    local_vertices = [
        (-length * 0.48, -width * 0.38, rim_z),
        (-length * 0.48, width * 0.38, rim_z),
        (length * 0.28, -width * 0.48, rim_z),
        (length * 0.28, width * 0.48, rim_z),
        (length * 0.52, 0.0, rim_z + height * 0.12),
        (-length * 0.38, -width * 0.22, -height),
        (-length * 0.38, width * 0.22, -height),
        (length * 0.2, -width * 0.18, -height),
        (length * 0.2, width * 0.18, -height),
        (length * 0.38, 0.0, -height * 0.8),
    ]
    vertices = [local_to_world(location, rotation_z, vertex) for vertex in local_vertices]
    faces = [
        (0, 2, 7, 5),
        (1, 6, 8, 3),
        (2, 4, 9, 7),
        (3, 8, 9, 4),
        (0, 5, 6, 1),
        (5, 7, 8, 6),
        (7, 9, 8),
        (2, 3, 4),
    ]
    mesh = bpy.data.meshes.new(f"{name}HullMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    hull = bpy.data.objects.new(f"{name} Hull", mesh)
    bpy.context.collection.objects.link(hull)
    hull.data.materials.append(hull_material)
    link_to_collection(hull, "Boats")

    add_box(f"{name} Interior Floor", local_to_world(location, rotation_z, (-0.04 * scale, 0.0, -height * 0.38)), (length * 0.62, width * 0.36, 0.045 * scale), mast_material, rotation_z, "Boats")
    for seat_x in (-0.26, 0.16):
        add_box(f"{name} Wooden Seat", local_to_world(location, rotation_z, (seat_x * length, 0.0, rim_z + 0.04 * scale)), (0.07 * scale, width * 0.68, 0.055 * scale), mast_material, rotation_z, "Boats")
    for rib_x in (-0.34, -0.1, 0.14, 0.34):
        add_box(f"{name} Interior Rib", local_to_world(location, rotation_z, (rib_x * length, 0.0, -height * 0.08)), (0.045 * scale, width * 0.72, 0.045 * scale), mast_material, rotation_z, "Boats")
    add_box(f"{name} Raised Bow Cap", local_to_world(location, rotation_z, (length * 0.48, 0.0, rim_z + 0.08 * scale)), (0.16 * scale, 0.22 * scale, 0.08 * scale), mast_material, rotation_z, "Boats")
    add_box(f"{name} Flat Stern Board", local_to_world(location, rotation_z, (-length * 0.46, 0.0, rim_z + 0.04 * scale)), (0.08 * scale, width * 0.68, 0.12 * scale), mast_material, rotation_z, "Boats")

    if boat_type in {"fishing", "sail"}:
        mast_height = 0.86 * scale
        mast_location = local_to_world(location, rotation_z, (-0.05 * scale, 0.0, mast_height / 2.0))
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.035 * scale, depth=mast_height, location=mast_location)
        mast = bpy.context.object
        mast.name = f"{name} Mast"
        mast.data.materials.append(mast_material)
        link_to_collection(mast, "Boats")

        sail_vertices = [
            local_to_world(location, rotation_z, (-0.02 * scale, 0.0, 0.18 * scale)),
            local_to_world(location, rotation_z, (-0.02 * scale, 0.0, 0.82 * scale)),
            local_to_world(location, rotation_z, (0.46 * scale, 0.0, 0.31 * scale)),
        ]
        sail_mesh = bpy.data.meshes.new(f"{name}SailMesh")
        sail_mesh.from_pydata(sail_vertices, [], [(0, 1, 2)])
        sail_mesh.update()
        sail = bpy.data.objects.new(f"{name} Sail", sail_mesh)
        bpy.context.collection.objects.link(sail)
        sail.data.materials.append(sail_material)
        link_to_collection(sail, "Boats")

        if boat_type == "sail":
            add_box(f"{name} Furled Sail Wrap", local_to_world(location, rotation_z, (0.18 * scale, 0.0, 0.62 * scale)), (0.56 * scale, 0.06 * scale, 0.08 * scale), sail_material, rotation_z, "Boats")
            add_box(f"{name} Rudder", local_to_world(location, rotation_z, (-length * 0.54, 0.0, -height * 0.15)), (0.06 * scale, 0.18 * scale, 0.28 * scale), mast_material, rotation_z, "Boats")

    if boat_type in {"fishing", "rowboat"}:
        for side in (-1.0, 1.0):
            oar_center = local_to_world(location, rotation_z, (-0.08 * scale, side * width * 0.56, rim_z + 0.02 * scale))
            add_box(f"{name} Oar", oar_center, (length * 0.5, 0.035 * scale, 0.035 * scale), mast_material, rotation_z + side * math.radians(16), "Boats")

    if boat_type == "fishing":
        gear_location = local_to_world(location, rotation_z, (-length * 0.25, 0.0, rim_z + 0.1 * scale))
        create_prop_crate(f"{name} Gear Crate", gear_location, mast_material, hull_material, 0.55, rotation_z)
        create_prop_rope(f"{name} Rope", local_to_world(location, rotation_z, (length * 0.1, width * 0.18, rim_z + 0.12 * scale)), {"rope": sail_material}, "Boats", 0.42)
        for index, yoff in enumerate((-0.11, 0.02, 0.15), start=1):
            add_box(f"{name} Folded Net Strand {index}", local_to_world(location, rotation_z, (length * 0.24, yoff * scale, rim_z + 0.12 * scale)), (0.34 * scale, 0.025 * scale, 0.025 * scale), sail_material, rotation_z + 0.2, "Boats")

    return hull


def create_ocean(material):
    add_box("Large Ocean Plane", (0.0, 0.0, -0.115), (46.0, 36.0, 0.035), material, 0.0, "Island")


def create_island_terrain(grass_material, sand_material, cliff_material, foam_material):
    segments = 104
    rings = 20
    vertices = [(0.0, 0.0, island_height(0.0, 0.0))]
    ring_indices = []

    for ring in range(1, rings + 1):
        radius_fraction = ring / rings
        row = []
        for segment in range(segments):
            theta = math.tau * segment / segments
            x, y = organic_point(theta, radius_fraction)
            row.append(len(vertices))
            vertices.append((x, y, island_height(x, y)))
        ring_indices.append(row)

    faces = []
    material_indices = []

    first_ring = ring_indices[0]
    for segment in range(segments):
        faces.append((0, first_ring[segment], first_ring[(segment + 1) % segments]))
        material_indices.append(0)

    for ring_index in range(rings - 1):
        inner = ring_indices[ring_index]
        outer = ring_indices[ring_index + 1]
        middle_fraction = (ring_index + 1.5) / rings
        mat_index = 1 if middle_fraction >= BEACH_START else 0

        for segment in range(segments):
            a = inner[segment]
            b = inner[(segment + 1) % segments]
            c = outer[segment]
            d = outer[(segment + 1) % segments]

            if (segment + ring_index) % 2 == 0:
                faces.extend([(a, c, d), (a, d, b)])
            else:
                faces.extend([(a, c, b), (b, c, d)])
            material_indices.extend([mat_index, mat_index])

    mesh = bpy.data.meshes.new("OrganicIslandTerrainMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    island = bpy.data.objects.new("Main Island - Grass Hills and Beach", mesh)
    bpy.context.collection.objects.link(island)
    island.data.materials.append(grass_material)
    link_to_collection(island, "Island")
    island.data.materials.append(sand_material)
    for polygon, material_index in zip(island.data.polygons, material_indices):
        polygon.material_index = material_index

    # A short skirt gives the coastline a small cliff-like edge above the ocean.
    cliff_vertices = []
    cliff_faces = []
    for segment in range(segments):
        theta = math.tau * segment / segments
        x, y = organic_point(theta, 1.0)
        top_z = island_height(x, y) - 0.01
        cliff_vertices.append((x, y, top_z))
        cliff_vertices.append((x, y, -0.36))

    for segment in range(segments):
        a = segment * 2
        b = ((segment + 1) % segments) * 2
        cliff_faces.append((a, b, b + 1, a + 1))

    cliff_mesh = bpy.data.meshes.new("IslandCoastalCliffMesh")
    cliff_mesh.from_pydata(cliff_vertices, [], cliff_faces)
    cliff_mesh.update()
    cliff = bpy.data.objects.new("Short Coastal Cliff Skirt", cliff_mesh)
    bpy.context.collection.objects.link(cliff)
    cliff.data.materials.append(cliff_material)
    link_to_collection(cliff, "Island")

    foam_vertices = []
    foam_faces = []
    for segment in range(segments):
        theta = math.tau * segment / segments
        inner = organic_point(theta, 1.015)
        outer = organic_point(theta, 1.065)
        foam_vertices.append((inner[0], inner[1], -0.072))
        foam_vertices.append((outer[0], outer[1], -0.071))

    for segment in range(segments):
        a = segment * 2
        b = ((segment + 1) % segments) * 2
        foam_faces.append((a, b, b + 1, a + 1))

    foam_mesh = bpy.data.meshes.new("CoastFoamMesh")
    foam_mesh.from_pydata(foam_vertices, [], foam_faces)
    foam_mesh.update()
    foam = bpy.data.objects.new("Thin Surf Ring Around Island", foam_mesh)
    bpy.context.collection.objects.link(foam)
    foam.data.materials.append(foam_material)
    link_to_collection(foam, "Island")

    return island


def create_rocks(rock_material):
    for index in range(30):
        theta = math.tau * index / 30.0 + random.uniform(-0.08, 0.08)
        radius_fraction = random.uniform(0.91, 1.05)
        x, y = organic_point(theta, radius_fraction)
        z = max(island_height(x, y), -0.06) + 0.03
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=random.uniform(0.16, 0.36), location=(x, y, z))
        rock = bpy.context.object
        rock.name = f"Coastal Low-Poly Rock {index + 1}"
        rock.scale.z *= random.uniform(0.45, 0.9)
        rock.data.materials.append(rock_material)
        link_to_collection(rock, "Props")


def create_dock(wood_material, materials=None, shore_angle: float = -0.62):
    """Create a larger working dock and return useful shoreline anchors."""
    shore_x, shore_y = organic_point(shore_angle, 0.96)
    direction = Vector((shore_x, shore_y, 0.0)).normalized()
    side = Vector((-direction.y, direction.x, 0.0)).normalized()
    plank_rotation = math.atan2(side.y, side.x)
    rail_rotation = math.atan2(direction.y, direction.x)
    start = Vector((shore_x, shore_y, 0.0))
    deck_z = 0.13

    for index in range(10):
        center = start + direction * (index * 0.34)
        add_box(
            f"Fishing Dock Deck Plank {index + 1}",
            (center.x, center.y, deck_z),
            (1.42, 0.28, 0.08),
            wood_material,
            plank_rotation,
            "Village_2",
        )

    platform_center = start + direction * 3.55
    for offset in (-0.28, 0.0, 0.28):
        center = platform_center + direction * offset
        add_box(
            "Fishing Dock End Platform Plank",
            (center.x, center.y, deck_z),
            (1.85, 0.26, 0.08),
            wood_material,
            plank_rotation,
            "Village_2",
        )

    for index in (0, 2, 4, 6, 8, 10):
        center = start + direction * (index * 0.34)
        for sign in (-1.0, 1.0):
            post = center + side * sign * 0.64
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.06, depth=0.78, location=(post.x, post.y, -0.08))
            obj = bpy.context.object
            obj.name = "Fishing Dock Support Post"
            obj.data.materials.append(wood_material)
            link_to_collection(obj, "Village_2")

    for sign in (-1.0, 1.0):
        rail_center = start + direction * 1.58 + side * sign * 0.69
        add_box(
            "Fishing Dock Side Rail",
            (rail_center.x, rail_center.y, deck_z + 0.32),
            (3.2, 0.055, 0.055),
            wood_material,
            rail_rotation,
            "Village_2",
        )

    for index, offset in enumerate((-0.58, 0.58), start=1):
        mooring = platform_center + side * offset
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.075, depth=0.52, location=(mooring.x, mooring.y, deck_z + 0.22))
        post = bpy.context.object
        post.name = f"Fishing Dock Mooring Post {index}"
        post.data.materials.append(wood_material)
        link_to_collection(post, "Village_2")

    ladder_center = start + direction * 2.25 + side * 0.74
    add_box("Fishing Dock Ladder Rail A", (ladder_center.x, ladder_center.y, deck_z - 0.18), (0.05, 0.05, 0.62), wood_material, rail_rotation, "Village_2")
    add_box("Fishing Dock Ladder Rail B", (ladder_center.x + side.x * 0.18, ladder_center.y + side.y * 0.18, deck_z - 0.18), (0.05, 0.05, 0.62), wood_material, rail_rotation, "Village_2")
    for step in range(3):
        rung = ladder_center + side * 0.09
        add_box(f"Fishing Dock Ladder Rung {step + 1}", (rung.x, rung.y, deck_z - 0.36 + step * 0.17), (0.24, 0.035, 0.035), wood_material, plank_rotation, "Village_2")

    if materials:
        create_prop_crate("Fishing Dock Working Crate", (platform_center.x + side.x * 0.38, platform_center.y + side.y * 0.38, deck_z + 0.08), materials["crate"], materials["dark_wood"], 0.84, plank_rotation)
        create_prop_barrel("Fishing Dock Salt Barrel", (platform_center.x - side.x * 0.42, platform_center.y - side.y * 0.42, deck_z + 0.08), materials["wood"], materials["metal"], 0.78)
        create_prop_rope("Fishing Dock Mooring", (platform_center.x, platform_center.y, deck_z + 0.1), materials, "Props", 0.85)

    land_yard = organic_point(shore_angle, 0.82)
    return {
        "shore": (shore_x, shore_y),
        "yard": land_yard,
        "end": (platform_center.x, platform_center.y),
        "direction": direction,
        "side": side,
        "rotation": plank_rotation,
        "rail_rotation": rail_rotation,
    }


def populate_trees(trunk_material, leaves_material, village_areas):
    village_centers = [(area[0], area[1]) for area in village_areas]
    placed = 0
    attempts = 0
    while placed < 78 and attempts < 900:
        attempts += 1
        x = random.uniform(-ISLAND_X_RADIUS * 1.05, ISLAND_X_RADIUS * 1.05)
        y = random.uniform(-ISLAND_Y_RADIUS * 1.05, ISLAND_Y_RADIUS * 1.05)
        radius, _theta = normalized_radius(x, y)
        if radius > BEACH_START - 0.02 or radius < 0.12:
            continue
        if any(math.hypot(x - area[0], y - area[1]) < area[2] for area in village_areas):
            continue

        z = island_height(x, y) + 0.03
        create_tree(f"Island Pine {placed + 1}", (x, y, z), trunk_material, leaves_material, random.uniform(0.65, 1.25))
        placed += 1

    for village_index, center in enumerate(village_centers, start=1):
        for index in range(12):
            angle = math.tau * index / 12.0 + random.uniform(-0.16, 0.16)
            distance = random.uniform(1.8, 3.0)
            x = center[0] + math.cos(angle) * distance
            y = center[1] + math.sin(angle) * distance
            radius, _theta = normalized_radius(x, y)
            if radius < BEACH_START - 0.03:
                create_tree(
                    f"Village {village_index} Nearby Tree {index + 1}",
                    (x, y, island_height(x, y) + 0.03),
                    trunk_material,
                    leaves_material,
                    random.uniform(0.55, 1.0),
                )


def add_lighting_and_camera():
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 9.0), rotation=(math.radians(48), 0.0, math.radians(35)))
    sun = bpy.context.object
    sun.name = "Warm Late Afternoon Sun"
    sun.data.energy = 2.6
    sun.data.angle = math.radians(3.5)

    bpy.ops.object.light_add(type="AREA", location=(-4.0, -5.0, 8.0))
    area = bpy.context.object
    area.name = "Soft Sky Fill Light"
    area.data.energy = 180.0
    area.data.size = 8.0

    bpy.ops.object.camera_add(location=(13.0, -15.0, 12.0))
    camera = bpy.context.object
    target = Vector((0.0, 0.0, 0.35))
    direction = target - Vector(camera.location)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 21.5
    bpy.context.scene.camera = camera

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.color = (0.72, 0.84, 0.98)


def configure_scene():
    try:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        bpy.context.scene.render.engine = "BLENDER_EEVEE"

    if hasattr(bpy.context.scene, "eevee") and hasattr(bpy.context.scene.eevee, "taa_render_samples"):
        bpy.context.scene.eevee.taa_render_samples = 64

    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1200
    try:
        bpy.context.scene.view_settings.view_transform = "Filmic"
        bpy.context.scene.view_settings.look = "Medium High Contrast"
    except TypeError:
        pass
    bpy.context.scene.unit_settings.system = "METRIC"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    for data_block_collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.curves,
        bpy.data.lights,
        bpy.data.cameras,
    ):
        for block in list(data_block_collection):
            if block.users == 0:
                data_block_collection.remove(block)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    clear_scene()
    COLLECTIONS.clear()
    create_scene_collections()

    materials = {
        "ocean": create_material("Deep Teal Ocean", (0.05, 0.32, 0.48, 1.0), 0.55),
        "grass": create_material("Faceted Island Grass", (0.30, 0.58, 0.28, 1.0), 0.9),
        "sand": create_material("Warm Beach Sand", (0.86, 0.72, 0.43, 1.0), 0.9),
        "cliff": create_material("Earthy Coast Cliff", (0.42, 0.32, 0.24, 1.0), 0.88),
        "foam": create_material("Pale Surf Foam", (0.86, 0.96, 0.93, 0.72), 0.55),
        "path": create_material("Packed Dirt Paths", (0.64, 0.48, 0.29, 1.0), 0.9),
        "wall_warm": create_material("Village Cream Walls", (0.78, 0.68, 0.53, 1.0), 0.85),
        "wall_cool": create_material("Village Pale Stone Walls", (0.66, 0.70, 0.68, 1.0), 0.85),
        "wall_fishing": create_material("Fishing Village Weathered Walls", (0.58, 0.62, 0.59, 1.0), 0.88),
        "wall_plaster": create_material("Light Beige Plaster Walls", (0.83, 0.78, 0.65, 1.0), 0.86),
        "wall_cream": create_material("Cream Cottage Plaster", (0.88, 0.8, 0.62, 1.0), 0.86),
        "wall_stone_plaster": create_material("Stone And Plaster Walls", (0.68, 0.64, 0.54, 1.0), 0.9),
        "wall_yellow": create_material("Pale Yellow Plaster", (0.86, 0.76, 0.46, 1.0), 0.86),
        "wall_timber": create_material("Dark Timber Framed Walls", (0.42, 0.32, 0.24, 1.0), 0.88),
        "wall_lime": create_material("Pale Limewash Walls", (0.78, 0.84, 0.66, 1.0), 0.86),
        "wall_stone": create_material("Rough Stone Cottage Walls", (0.5, 0.49, 0.44, 1.0), 0.9),
        "wall_weathered_wood": create_material("Weathered Coastal Boards", (0.48, 0.52, 0.5, 1.0), 0.9),
        "wall_dark_plank": create_material("Dark Rough Timber Planks", (0.28, 0.24, 0.2, 1.0), 0.9),
        "wall_fishing_plaster": create_material("Weathered Fishing Plaster", (0.68, 0.7, 0.64, 1.0), 0.88),
        "wall_dark_wood": create_material("Dark Coastal Hut Wood", (0.22, 0.18, 0.14, 1.0), 0.9),
        "wall_whitewashed": create_material("Whitewashed Coastal Walls", (0.82, 0.84, 0.78, 1.0), 0.86),
        "stable_wall": create_material("Stable Warm Timber Walls", (0.45, 0.3, 0.18, 1.0), 0.9),
        "roof_red": create_material("Village One Red Brown Roofs", (0.54, 0.18, 0.11, 1.0), 0.86),
        "roof_blue": create_material("Village Two Slate Blue Roofs", (0.19, 0.27, 0.36, 1.0), 0.86),
        "roof_gray": create_material("Fishing Workshop Dark Gray Roof", (0.15, 0.18, 0.2, 1.0), 0.86),
        "roof_thatch": create_material("Warm Wooden Well Roof", (0.62, 0.42, 0.18, 1.0), 0.88),
        "roof_orange": create_material("Orange Red Clay Roof", (0.72, 0.28, 0.12, 1.0), 0.86),
        "roof_red_brown": create_material("Muted Red Brown Roof", (0.46, 0.18, 0.1, 1.0), 0.86),
        "roof_brown": create_material("Warm Brown Roof", (0.34, 0.2, 0.1, 1.0), 0.86),
        "roof_muted": create_material("Muted Rustic Roof", (0.29, 0.28, 0.24, 1.0), 0.88),
        "roof_gray_red": create_material("Gray Red Handmade Roof", (0.36, 0.22, 0.2, 1.0), 0.88),
        "roof_green_gray": create_material("Green Gray Coastal Roof", (0.22, 0.33, 0.3, 1.0), 0.88),
        "roof_blue_dark": create_material("Dark Slate Blue Roof", (0.13, 0.2, 0.3, 1.0), 0.86),
        "door": create_material("Dark Wooden Doors", (0.25, 0.14, 0.08, 1.0), 0.82),
        "window": create_material("Soft Blue Windows", (0.55, 0.78, 0.93, 1.0), 0.35),
        "trunk": create_material("Tree Trunks", (0.34, 0.20, 0.10, 1.0), 0.82),
        "leaves": create_material("Low-Poly Tree Greens", (0.13, 0.43, 0.23, 1.0), 0.88),
        "wood": create_material("Weathered Dock Wood", (0.42, 0.24, 0.12, 1.0), 0.82),
        "dark_wood": create_material("Dark Wood Detail", (0.2, 0.12, 0.07, 1.0), 0.84),
        "crate": create_material("Pale Fishing Crate Wood", (0.56, 0.36, 0.18, 1.0), 0.84),
        "bucket": create_material("Dark Bucket Interior", (0.08, 0.07, 0.06, 1.0), 0.55),
        "metal": create_material("Dark Metal Bands", (0.12, 0.12, 0.12, 1.0), 0.45),
        "garden_soil": create_material("Small Garden Soil", (0.28, 0.18, 0.1, 1.0), 0.9),
        "garden_green": create_material("Garden Sprout Rows", (0.16, 0.48, 0.18, 1.0), 0.9),
        "rope": create_material("Fishing Net Rope", (0.74, 0.66, 0.48, 1.0), 0.8),
        "fish": create_material("Dried Fish Ochre", (0.76, 0.48, 0.22, 1.0), 0.78),
        "floor": create_material("Interior Wooden Floors", (0.48, 0.31, 0.16, 1.0), 0.84),
        "fabric": create_material("Warm Homespun Fabric", (0.56, 0.28, 0.24, 1.0), 0.82),
        "pillow": create_material("Pale Pillow Fabric", (0.86, 0.82, 0.72, 1.0), 0.82),
        "rug": create_material("Woven Rug Fabric", (0.38, 0.22, 0.42, 1.0), 0.88),
        "clay": create_material("Clay Pottery And Oven", (0.62, 0.34, 0.18, 1.0), 0.86),
        "fire": create_material("Warm Fire Glow", (1.0, 0.34, 0.08, 1.0), 0.35),
        "black": create_material("Soot Black Iron", (0.04, 0.04, 0.035, 1.0), 0.58),
        "sack": create_material("Burlap Grain Sacks", (0.66, 0.52, 0.34, 1.0), 0.9),
        "hay": create_material("Golden Hay Bales", (0.84, 0.62, 0.24, 1.0), 0.9),
        "paving": create_material("Worn Village Stone Paving", (0.48, 0.45, 0.38, 1.0), 0.92),
        "pebbles": create_material("Pebbly Cove Ground", (0.56, 0.54, 0.47, 1.0), 0.9),
        "lantern": create_material("Warm Lantern Glass", (1.0, 0.72, 0.28, 1.0), 0.35),
        "flower": create_material("Tiny Flower Box Blooms", (0.78, 0.2, 0.3, 1.0), 0.88),
        "boat_hull": create_material("Small Boat Hulls", (0.36, 0.17, 0.10, 1.0), 0.78),
        "sail": create_material("Plain Canvas Sails", (0.92, 0.86, 0.68, 1.0), 0.7),
        "rock": create_material("Coastal Rock", (0.42, 0.43, 0.39, 1.0), 0.86),
    }

    create_ocean(materials["ocean"])
    create_island_terrain(materials["grass"], materials["sand"], materials["cliff"], materials["foam"])

    inland_village_center = (-2.35, -0.45)
    dock_info = create_dock(materials["wood"], materials, shore_angle=-0.62)
    fishing_center_vec = Vector((dock_info["yard"][0], dock_info["yard"][1], 0.0)) - dock_info["direction"] * 0.75
    fishing_village_center = (fishing_center_vec.x, fishing_center_vec.y)

    inland_village = create_village(
        "Hillwell Village",
        inland_village_center,
        materials["roof_red"],
        materials["wall_warm"],
        materials["door"],
        materials["window"],
        materials["path"],
        materials,
        seed=11,
    )
    fishing_village = create_fishing_village(
        "Tidepost Fishing Village",
        fishing_village_center,
        dock_info,
        materials["roof_blue"],
        materials["wall_fishing"],
        materials["door"],
        materials["window"],
        materials["path"],
        materials,
        seed=27,
    )

    create_road_or_path(
        "Main Road Connecting Both Villages",
        [
            inland_village["road_anchor"],
            (-0.65, -0.86),
            (1.15, -1.14),
            (2.85, -1.55),
            (4.2, -2.05),
            fishing_village["road_anchor"],
        ],
        0.42,
        materials["path"],
        0.085,
    )

    populate_trees(
        materials["trunk"],
        materials["leaves"],
        [
            (inland_village_center[0], inland_village_center[1], 3.65),
            (fishing_village_center[0], fishing_village_center[1], 2.85),
            (dock_info["yard"][0], dock_info["yard"][1], 2.1),
        ],
    )
    create_rocks(materials["rock"])

    for index, offset in enumerate((-0.95, 0.95), start=1):
        rock_base = Vector((dock_info["shore"][0], dock_info["shore"][1], 0.0)) + dock_info["side"] * offset - dock_info["direction"] * 0.15
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.24, location=(rock_base.x, rock_base.y, island_height(rock_base.x, rock_base.y) + 0.06))
        rock = bpy.context.object
        rock.name = f"Dockside Coastal Rock {index}"
        rock.scale.z *= 0.55
        rock.data.materials.append(materials["rock"])

    boat_specs = [
        ("Boat 1 Main Fishing Boat Moored At Dock", dock_info["shore"], 1.42, 0.88, "fishing", 1.28, "water"),
        ("Boat 2 Smaller Fishing Boat Tied To Side Post", dock_info["end"], 0.28, -1.12, "fishing", 0.95, "water"),
        ("Boat 3 Utility Rowboat Pulled On Shore", dock_info["yard"], -0.48, 1.82, "rowboat", 0.86, "shore"),
        ("Boat 4 Small Coastal Sailboat Anchored In Cove", dock_info["end"], 1.72, 1.35, "sail", 1.08, "water"),
    ]
    for index, (boat_name, anchor, forward, side_offset, boat_type, scale, placement) in enumerate(boat_specs, start=1):
        boat_center = Vector((anchor[0], anchor[1], 0.0)) + dock_info["direction"] * forward + dock_info["side"] * side_offset
        boat_z = island_height(boat_center.x, boat_center.y) + 0.28 if placement == "shore" else 0.02
        create_boat(
            f"Tidepost {boat_name}",
            (boat_center.x, boat_center.y, boat_z),
            dock_info["rail_rotation"] + random.uniform(-0.12, 0.12),
            materials["boat_hull"],
            materials["sail"],
            materials["wood"],
            scale,
            boat_type,
        )

    add_lighting_and_camera()
    configure_scene()

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format="GLB", use_selection=False)
    print(f"Saved Blender file: {BLEND_PATH}")
    print(f"Exported GLB preview: {GLB_PATH}")


if __name__ == "__main__":
    main()
