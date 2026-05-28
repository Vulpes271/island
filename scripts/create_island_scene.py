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


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 0.0
    t = clamp((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


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


def boundary_factor(theta: float) -> float:
    """Organic outline multiplier used by both terrain and object placement."""
    return (
        1.0
        + 0.14 * math.sin(theta * 3.0 + 0.4)
        + 0.09 * math.sin(theta * 5.0 - 1.1)
        + 0.06 * math.sin(theta * 8.0 + 2.0)
        + 0.035 * math.cos(theta * 11.0 - 0.7)
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


def add_box(name: str, location, dimensions, material, rotation_z: float = 0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0.0, 0.0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    if material:
        obj.data.materials.append(material)
    return obj


def create_roof(name: str, origin, rotation_z: float, width: float, depth: float, wall_height: float, roof_height: float, material):
    eave = 0.12
    w = width + eave * 2.0
    d = depth + eave * 2.0
    local_vertices = [
        (-w / 2.0, -d / 2.0, wall_height),
        (w / 2.0, -d / 2.0, wall_height),
        (0.0, -d / 2.0, wall_height + roof_height),
        (-w / 2.0, d / 2.0, wall_height),
        (w / 2.0, d / 2.0, wall_height),
        (0.0, d / 2.0, wall_height + roof_height),
    ]
    vertices = [local_to_world(origin, rotation_z, vertex) for vertex in local_vertices]
    faces = [
        (0, 1, 2),
        (3, 5, 4),
        (0, 3, 4, 1),
        (1, 4, 5, 2),
        (0, 2, 5, 3),
    ]

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def create_house(name: str, location, rotation_z: float, wall_material, roof_material, door_material, window_material, scale: float = 1.0):
    """Create a small low-poly cottage with walls, roof, door, and windows."""
    width = random.uniform(0.78, 1.08) * scale
    depth = random.uniform(0.82, 1.16) * scale
    wall_height = random.uniform(0.55, 0.72) * scale
    roof_height = random.uniform(0.34, 0.48) * scale

    wall_center = local_to_world(location, rotation_z, (0.0, 0.0, wall_height / 2.0))
    add_box(f"{name} Walls", wall_center, (width, depth, wall_height), wall_material, rotation_z)
    create_roof(f"{name} Gabled Roof", location, rotation_z, width, depth, wall_height, roof_height, roof_material)

    door_width = width * 0.22
    door_height = wall_height * 0.62
    door_center = local_to_world(location, rotation_z, (0.0, -depth / 2.0 - 0.026, door_height / 2.0))
    add_box(f"{name} Door", door_center, (door_width, 0.05, door_height), door_material, rotation_z)

    window_size = min(width, wall_height) * 0.18
    for side in (-1.0, 1.0):
        window_center = local_to_world(location, rotation_z, (side * width * 0.28, -depth / 2.0 - 0.028, wall_height * 0.58))
        add_box(f"{name} Front Window", window_center, (window_size, 0.045, window_size), window_material, rotation_z)

    side_window_center = local_to_world(location, rotation_z, (width / 2.0 + 0.026, 0.08, wall_height * 0.58))
    add_box(f"{name} Side Window", side_window_center, (0.045, window_size, window_size), window_material, rotation_z)

    return {
        "name": name,
        "location": location,
        "width": width,
        "depth": depth,
        "height": wall_height + roof_height,
    }


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
    return obj


def create_village(name: str, center, roof_material, wall_material, door_material, window_material, path_material, house_count: int, radius: float, seed: int):
    """Create a clustered village with multiple houses and internal paths."""
    rng = random.Random(seed)
    village_center = (center[0], center[1], island_height(center[0], center[1]) + 0.08)

    house_points = []
    loop_points = []
    for index in range(house_count):
        angle = math.tau * index / house_count + rng.uniform(-0.22, 0.22)
        distance = rng.uniform(radius * 0.55, radius)
        x = center[0] + math.cos(angle) * distance * rng.uniform(0.9, 1.25)
        y = center[1] + math.sin(angle) * distance * rng.uniform(0.75, 1.05)

        # Pull any stray house back toward the center so every cottage remains on grass.
        for _ in range(5):
            r, _theta = normalized_radius(x, y)
            if r < BEACH_START - 0.06:
                break
            x = (x + center[0]) / 2.0
            y = (y + center[1]) / 2.0

        z = island_height(x, y) + 0.08
        dx = center[0] - x
        dy = center[1] - y
        rotation = math.atan2(dx, -dy)
        scale = rng.uniform(0.78, 1.15)
        create_house(f"{name} House {index + 1}", (x, y, z), rotation, wall_material, roof_material, door_material, window_material, scale)
        house_points.append((x, y))
        loop_points.append((x * 0.78 + center[0] * 0.22, y * 0.78 + center[1] * 0.22))

    sorted_loop = sorted(loop_points, key=lambda point: math.atan2(point[1] - center[1], point[0] - center[0]))
    create_road_or_path(f"{name} Loop Path", sorted_loop + [sorted_loop[0]], 0.22, path_material, 0.07)
    for index, point in enumerate(house_points):
        if index % 2 == 0 or index == len(house_points) - 1:
            create_road_or_path(f"{name} House Spur {index + 1}", [center, point], 0.15, path_material, 0.075)

    # A tiny village well gives each cluster a readable center without adding much geometry.
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.22, depth=0.16, location=(village_center[0], village_center[1], village_center[2] + 0.08))
    well = bpy.context.object
    well.name = f"{name} Stone Well"
    well.data.materials.append(bpy.data.materials["Coastal Rock"])

    return {"center": center, "houses": house_points}


def create_boat(name: str, location, rotation_z: float, hull_material, sail_material, mast_material, scale: float = 1.0):
    """Create a simple low-poly boat with a mast and triangular sail."""
    length = 1.25 * scale
    width = 0.48 * scale
    height = 0.24 * scale

    local_vertices = [
        (-length / 2.0, -width / 2.0, 0.0),
        (length / 2.0, -width / 2.0, 0.0),
        (length / 2.0, width / 2.0, 0.0),
        (-length / 2.0, width / 2.0, 0.0),
        (-length * 0.34, -width * 0.26, -height),
        (length * 0.34, -width * 0.26, -height),
        (length * 0.34, width * 0.26, -height),
        (-length * 0.34, width * 0.26, -height),
    ]
    vertices = [local_to_world(location, rotation_z, vertex) for vertex in local_vertices]
    faces = [
        (0, 1, 2, 3),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
        (4, 7, 6, 5),
    ]
    mesh = bpy.data.meshes.new(f"{name}HullMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    hull = bpy.data.objects.new(f"{name} Hull", mesh)
    bpy.context.collection.objects.link(hull)
    hull.data.materials.append(hull_material)

    mast_height = 0.85 * scale
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.035 * scale, depth=mast_height, location=(location[0], location[1], location[2] + mast_height / 2.0))
    mast = bpy.context.object
    mast.name = f"{name} Mast"
    mast.data.materials.append(mast_material)

    sail_vertices = [
        local_to_world(location, rotation_z, (0.04 * scale, 0.0, 0.18 * scale)),
        local_to_world(location, rotation_z, (0.04 * scale, 0.0, 0.82 * scale)),
        local_to_world(location, rotation_z, (0.48 * scale, 0.0, 0.28 * scale)),
    ]
    sail_mesh = bpy.data.meshes.new(f"{name}SailMesh")
    sail_mesh.from_pydata(sail_vertices, [], [(0, 1, 2)])
    sail_mesh.update()
    sail = bpy.data.objects.new(f"{name} Sail", sail_mesh)
    bpy.context.collection.objects.link(sail)
    sail.data.materials.append(sail_material)
    return hull


def create_ocean(material):
    add_box("Large Low-Poly Ocean Plane", (0.0, 0.0, -0.115), (46.0, 36.0, 0.035), material, 0.0)


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


def create_dock(wood_material):
    theta = -math.pi / 2.0 - 0.18
    shore_x, shore_y = organic_point(theta, 0.95)
    direction = Vector((shore_x, shore_y, 0.0)).normalized()
    rotation = math.atan2(-direction.x, direction.y)
    start = Vector((shore_x, shore_y, 0.0))

    for index in range(8):
        center = start + direction * (index * 0.34)
        add_box(
            f"Wood Dock Plank {index + 1}",
            (center.x, center.y, 0.12),
            (1.35, 0.28, 0.08),
            wood_material,
            rotation,
        )

    for index in (1, 3, 5, 7):
        center = start + direction * (index * 0.34)
        side = Vector((-direction.y, direction.x, 0.0))
        for sign in (-1.0, 1.0):
            post = center + side * sign * 0.58
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.055, depth=0.55, location=(post.x, post.y, -0.03))
            obj = bpy.context.object
            obj.name = "Wood Dock Post"
            obj.data.materials.append(wood_material)


def populate_trees(trunk_material, leaves_material, village_centers):
    placed = 0
    attempts = 0
    while placed < 78 and attempts < 900:
        attempts += 1
        x = random.uniform(-ISLAND_X_RADIUS * 1.05, ISLAND_X_RADIUS * 1.05)
        y = random.uniform(-ISLAND_Y_RADIUS * 1.05, ISLAND_Y_RADIUS * 1.05)
        radius, _theta = normalized_radius(x, y)
        if radius > BEACH_START - 0.02 or radius < 0.12:
            continue
        if any(math.hypot(x - center[0], y - center[1]) < 1.8 for center in village_centers):
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

    materials = {
        "ocean": create_material("Deep Teal Ocean", (0.05, 0.32, 0.48, 1.0), 0.55),
        "grass": create_material("Faceted Island Grass", (0.30, 0.58, 0.28, 1.0), 0.9),
        "sand": create_material("Warm Beach Sand", (0.86, 0.72, 0.43, 1.0), 0.9),
        "cliff": create_material("Earthy Coast Cliff", (0.42, 0.32, 0.24, 1.0), 0.88),
        "foam": create_material("Pale Surf Foam", (0.86, 0.96, 0.93, 0.72), 0.55),
        "path": create_material("Packed Dirt Paths", (0.64, 0.48, 0.29, 1.0), 0.9),
        "wall_warm": create_material("Village Cream Walls", (0.78, 0.68, 0.53, 1.0), 0.85),
        "wall_cool": create_material("Village Pale Stone Walls", (0.66, 0.70, 0.68, 1.0), 0.85),
        "roof_red": create_material("Village One Red Brown Roofs", (0.54, 0.18, 0.11, 1.0), 0.86),
        "roof_blue": create_material("Village Two Slate Blue Roofs", (0.19, 0.27, 0.36, 1.0), 0.86),
        "door": create_material("Dark Wooden Doors", (0.25, 0.14, 0.08, 1.0), 0.82),
        "window": create_material("Soft Blue Windows", (0.55, 0.78, 0.93, 1.0), 0.35),
        "trunk": create_material("Tree Trunks", (0.34, 0.20, 0.10, 1.0), 0.82),
        "leaves": create_material("Low-Poly Tree Greens", (0.13, 0.43, 0.23, 1.0), 0.88),
        "wood": create_material("Weathered Dock Wood", (0.42, 0.24, 0.12, 1.0), 0.82),
        "boat_hull": create_material("Small Boat Hulls", (0.36, 0.17, 0.10, 1.0), 0.78),
        "sail": create_material("Plain Canvas Sails", (0.92, 0.86, 0.68, 1.0), 0.7),
        "rock": create_material("Coastal Rock", (0.42, 0.43, 0.39, 1.0), 0.86),
    }

    create_ocean(materials["ocean"])
    create_island_terrain(materials["grass"], materials["sand"], materials["cliff"], materials["foam"])

    village_one_center = (-5.35, -1.55)
    village_two_center = (5.2, 1.7)
    create_village(
        "Sunset Village",
        village_one_center,
        materials["roof_red"],
        materials["wall_warm"],
        materials["door"],
        materials["window"],
        materials["path"],
        house_count=9,
        radius=1.85,
        seed=11,
    )
    create_village(
        "Harborwatch Village",
        village_two_center,
        materials["roof_blue"],
        materials["wall_cool"],
        materials["door"],
        materials["window"],
        materials["path"],
        house_count=8,
        radius=1.75,
        seed=27,
    )

    create_road_or_path(
        "Main Road Connecting Both Villages",
        [
            village_one_center,
            (-3.25, -0.95),
            (-1.15, -0.22),
            (0.9, 0.2),
            (3.2, 0.95),
            village_two_center,
        ],
        0.35,
        materials["path"],
        0.085,
    )

    populate_trees(materials["trunk"], materials["leaves"], [village_one_center, village_two_center])
    create_rocks(materials["rock"])
    create_dock(materials["wood"])

    boat_angles = [-math.pi / 2.0 - 0.35, -math.pi / 2.0 + 0.24, -math.pi / 2.0 + 0.65, 0.18]
    for index, theta in enumerate(boat_angles, start=1):
        x, y = organic_point(theta, random.uniform(1.24, 1.42))
        create_boat(
            f"Small Sailboat {index}",
            (x, y, 0.02),
            theta + math.pi / 2.0 + random.uniform(-0.25, 0.25),
            materials["boat_hull"],
            materials["sail"],
            materials["wood"],
            random.uniform(0.82, 1.08),
        )

    add_lighting_and_camera()
    configure_scene()

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format="GLB", use_selection=False)
    print(f"Saved Blender file: {BLEND_PATH}")
    print(f"Exported GLB preview: {GLB_PATH}")


if __name__ == "__main__":
    main()
