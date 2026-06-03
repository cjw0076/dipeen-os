import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
DOC_OUT_DIR = ROOT / "docs" / "brand-assets" / "blender-mcp-office"
WEB_OUT_DIR = ROOT / "web" / "public" / "assets" / "office-3d"


BLENDER_CODE = r'''
import os
from math import radians

import bpy


bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()


def material(name, color, roughness=0.45, metallic=0.0, alpha=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    mat.show_transparent_back = False
    if alpha is not None or color[3] < 1:
        mat.blend_method = 'BLEND'
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3] if alpha is None else alpha
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    return mat


MAT_FLOOR = material("dipeen_floor_graphite", (0.035, 0.041, 0.052, 1), 0.62)
MAT_FLOOR_ALT = material("dipeen_floor_panel", (0.065, 0.078, 0.096, 1), 0.58)
MAT_GRID = material("dipeen_floor_grid_blue", (0.18, 0.39, 0.82, 1), 0.36)
MAT_EDGE = material("dipeen_edge_metal", (0.45, 0.51, 0.61, 1), 0.24, 0.25)
MAT_DARK = material("dipeen_station_dark", (0.025, 0.029, 0.038, 1), 0.52)
MAT_GLASS = material("dipeen_glass_blue", (0.18, 0.38, 0.95, 0.38), 0.14, 0.0, 0.38)
MAT_SCREEN = material("dipeen_screen_blue", (0.12, 0.34, 0.95, 1), 0.25)
MAT_GREEN = material("dipeen_online_green", (0.20, 0.83, 0.60, 1), 0.3)
MAT_YELLOW = material("dipeen_pm_yellow", (0.96, 0.78, 0.28, 1), 0.35)
MAT_CYAN = material("dipeen_fe_blue", (0.28, 0.55, 0.96, 1), 0.32)
MAT_VIOLET = material("dipeen_be_violet", (0.61, 0.45, 0.98, 1), 0.34)
MAT_PINK = material("dipeen_qa_pink", (0.94, 0.40, 0.72, 1), 0.36)
MAT_PLANT = material("dipeen_plant_green", (0.17, 0.56, 0.34, 1), 0.55)


def cube(name, loc, scale, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    obj.color = mat.diffuse_color
    if bevel > 0:
        bevel_mod = obj.modifiers.new("soft_radius", "BEVEL")
        bevel_mod.width = bevel
        bevel_mod.segments = 2
        normal_mod = obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)
        bpy.ops.object.modifier_apply(modifier=normal_mod.name)
        obj.select_set(False)
    return obj


def cylinder(name, loc, radius, depth, mat, vertices=32, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    obj.color = mat.diffuse_color
    if bevel > 0:
        bevel_mod = obj.modifiers.new("soft_radius", "BEVEL")
        bevel_mod.width = bevel
        bevel_mod.segments = 2
        normal_mod = obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)
        bpy.ops.object.modifier_apply(modifier=normal_mod.name)
        obj.select_set(False)
    return obj


def station(role, x, y, accent):
    prefix = f"dipeen_station_{role.lower()}"
    cube(f"{prefix}_desk", (x, y, 0.42), (1.25, 0.72, 0.18), MAT_DARK, 0.035)
    cube(f"{prefix}_leg_l", (x - 0.46, y - 0.22, 0.16), (0.12, 0.12, 0.52), MAT_EDGE, 0.018)
    cube(f"{prefix}_leg_r", (x + 0.46, y - 0.22, 0.16), (0.12, 0.12, 0.52), MAT_EDGE, 0.018)
    cube(f"{prefix}_monitor_back", (x, y + 0.18, 0.92), (0.72, 0.08, 0.48), MAT_GLASS, 0.035)
    cube(f"{prefix}_screen", (x, y + 0.13, 0.92), (0.58, 0.035, 0.34), MAT_SCREEN, 0.02)
    cube(f"{prefix}_status_dot", (x + 0.26, y + 0.105, 1.08), (0.08, 0.025, 0.08), MAT_GREEN, 0.02)
    cube(f"{prefix}_keyboard", (x, y - 0.23, 0.56), (0.58, 0.2, 0.045), MAT_EDGE, 0.02)
    cube(f"{prefix}_role_tile", (x - 0.47, y + 0.24, 0.56), (0.18, 0.18, 0.045), accent, 0.02)
    cylinder(f"{prefix}_seat", (x, y - 0.68, 0.45), 0.22, 0.12, accent, 24, 0.025)
    cube(f"{prefix}_seat_base", (x, y - 0.68, 0.25), (0.10, 0.10, 0.28), MAT_EDGE, 0.018)


def server_rack(x, y):
    cube("dipeen_server_rack_body", (x, y, 0.82), (0.62, 0.46, 1.25), MAT_DARK, 0.035)
    for i in range(5):
        z = 0.32 + i * 0.2
        cube(f"dipeen_server_rack_slot_{i}", (x, y - 0.235, z), (0.5, 0.035, 0.055), MAT_EDGE, 0.01)
        cube(f"dipeen_server_rack_light_{i}", (x + 0.22, y - 0.26, z), (0.035, 0.02, 0.035), MAT_GREEN if i % 2 else MAT_SCREEN, 0.01)


def command_wall(x, y):
    cube("dipeen_command_wall_panel", (x, y, 1.18), (1.65, 0.08, 0.88), MAT_GLASS, 0.04)
    for i, width in enumerate([0.98, 0.7, 1.18, 0.52]):
        cube(f"dipeen_command_wall_line_{i}", (x - 0.24 + i * 0.15, y - 0.055, 1.42 - i * 0.16), (width, 0.025, 0.035), MAT_SCREEN if i % 2 == 0 else MAT_GREEN, 0.01)
    cube("dipeen_command_wall_badge", (x + 0.65, y - 0.06, 0.84), (0.18, 0.025, 0.18), MAT_YELLOW, 0.02)


def meeting_table(x, y):
    cylinder("dipeen_meeting_table_top", (x, y, 0.48), 0.55, 0.12, MAT_DARK, 40, 0.025)
    cube("dipeen_meeting_table_base", (x, y, 0.25), (0.18, 0.18, 0.38), MAT_EDGE, 0.025)
    for i, (dx, dy, mat) in enumerate([(0, 0.75, MAT_YELLOW), (0.75, 0, MAT_CYAN), (0, -0.75, MAT_VIOLET), (-0.75, 0, MAT_PINK)]):
        cylinder(f"dipeen_meeting_seat_{i}", (x + dx, y + dy, 0.34), 0.2, 0.12, mat, 24, 0.02)


def plant(name, x, y):
    cylinder(f"{name}_pot", (x, y, 0.22), 0.16, 0.32, MAT_EDGE, 24, 0.015)
    cylinder(f"{name}_leaf_a", (x - 0.08, y, 0.58), 0.11, 0.48, MAT_PLANT, 16, 0.015)
    cylinder(f"{name}_leaf_b", (x + 0.08, y + 0.04, 0.62), 0.10, 0.42, MAT_PLANT, 16, 0.015)


# Floor and zones.
cube("dipeen_office_floor_base", (0, 0, -0.04), (7.2, 4.8, 0.08), MAT_FLOOR, 0.02)
cube("dipeen_office_floor_command_zone", (-1.95, 1.32, 0.005), (2.55, 1.55, 0.025), MAT_FLOOR_ALT, 0.015)
cube("dipeen_office_floor_build_zone", (0.85, 0.82, 0.006), (3.4, 1.95, 0.025), MAT_FLOOR_ALT, 0.015)
cube("dipeen_office_floor_meeting_zone", (1.75, -1.35, 0.007), (2.35, 1.55, 0.025), MAT_FLOOR_ALT, 0.015)

for ix, x in enumerate([-3.6, -2.4, -1.2, 0, 1.2, 2.4, 3.6]):
    cube(f"dipeen_floor_grid_x_{ix}", (x, 0, 0.02), (0.018, 4.65, 0.018), MAT_GRID, 0.004)
for iy, y in enumerate([-2.4, -1.2, 0, 1.2, 2.4]):
    cube(f"dipeen_floor_grid_y_{iy}", (0, y, 0.021), (7.05, 0.018, 0.018), MAT_GRID, 0.004)

# Glass perimeter and room separators.
cube("dipeen_glass_wall_north", (0, 2.42, 0.72), (7.15, 0.08, 1.28), MAT_GLASS, 0.02)
cube("dipeen_glass_wall_west", (-3.62, 0, 0.72), (0.08, 4.85, 1.28), MAT_GLASS, 0.02)
cube("dipeen_glass_room_split", (0.28, -0.45, 0.58), (0.06, 2.1, 1.0), MAT_GLASS, 0.02)
cube("dipeen_glass_meeting_back", (1.75, -2.05, 0.58), (2.2, 0.06, 1.0), MAT_GLASS, 0.02)

# Props.
station("PM", -2.55, 1.08, MAT_YELLOW)
station("FE", -0.85, 0.9, MAT_CYAN)
station("BE", 0.9, 0.9, MAT_VIOLET)
station("QA", -0.78, -0.78, MAT_PINK)
meeting_table(1.75, -1.24)
server_rack(3.05, 0.95)
command_wall(-2.15, 2.05)
plant("dipeen_plant_nw", -3.12, -1.82)
plant("dipeen_plant_ne", 3.12, 1.98)
cube("dipeen_sofa_body", (3.0, -1.25, 0.36), (1.05, 0.44, 0.32), MAT_DARK, 0.04)
cube("dipeen_sofa_back", (3.0, -1.48, 0.62), (1.05, 0.12, 0.52), MAT_GLASS, 0.035)

# Lights and camera for preview.
bpy.ops.object.light_add(type='AREA', location=(0, -3.7, 5.0))
light = bpy.context.object
light.name = "dipeen_office_key_area_light"
light.data.energy = 650
light.data.size = 5

bpy.ops.object.camera_add(location=(5.8, -6.2, 4.8), rotation=(radians(60), 0, radians(43)))
bpy.context.scene.camera = bpy.context.object

bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
bpy.context.scene.display.shading.color_type = 'MATERIAL'
bpy.context.scene.display.shading.light = 'STUDIO'
bpy.context.scene.display.shading.show_object_outline = False
bpy.context.scene.render.film_transparent = True
bpy.context.scene.render.resolution_x = 1600
bpy.context.scene.render.resolution_y = 1100
bpy.context.scene.view_settings.view_transform = 'Standard'
bpy.context.scene.view_settings.look = 'None'

doc_out = r"__DOC_OUT_DIR__"
web_out = r"__WEB_OUT_DIR__"
os.makedirs(doc_out, exist_ok=True)
os.makedirs(web_out, exist_ok=True)

blend_path = os.path.join(doc_out, "dipeen-office-scene.blend")
doc_glb = os.path.join(doc_out, "dipeen-office-scene.glb")
web_glb = os.path.join(web_out, "dipeen-office-scene.glb")
preview = os.path.join(doc_out, "dipeen-office-scene-preview.png")

bpy.ops.wm.save_as_mainfile(filepath=blend_path)
bpy.ops.export_scene.gltf(filepath=doc_glb, export_format='GLB')
bpy.ops.export_scene.gltf(filepath=web_glb, export_format='GLB')
bpy.context.scene.render.filepath = preview
bpy.ops.render.render(write_still=True)

print("DIPEEN_OFFICE_ASSET_READY", doc_out, web_out)
'''


async def main() -> None:
    DOC_OUT_DIR.mkdir(parents=True, exist_ok=True)
    WEB_OUT_DIR.mkdir(parents=True, exist_ok=True)

    code = (
        BLENDER_CODE
        .replace("__DOC_OUT_DIR__", str(DOC_OUT_DIR).replace("\\", "\\\\"))
        .replace("__WEB_OUT_DIR__", str(WEB_OUT_DIR).replace("\\", "\\\\"))
    )

    params = StdioServerParameters(
        command="uvx",
        args=["blender-mcp"],
        env={
            **os.environ,
            "BLENDER_HOST": "localhost",
            "BLENDER_PORT": os.environ.get("BLENDER_MCP_PORT", "9876"),
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "execute_blender_code",
                {
                    "code": code,
                    "user_prompt": "Generate a modular Dipeen 3D virtual office GLB asset pack for the office route.",
                },
            )
            scene = await session.call_tool(
                "get_scene_info",
                {"user_prompt": "Summarize the generated Dipeen virtual office scene."},
            )

    print(json.dumps(
        {
            "execute_result": [item.text for item in result.content if hasattr(item, "text")],
            "scene_info": [item.text for item in scene.content if hasattr(item, "text")],
            "outputs": {
                "blend": str(DOC_OUT_DIR / "dipeen-office-scene.blend"),
                "doc_glb": str(DOC_OUT_DIR / "dipeen-office-scene.glb"),
                "web_glb": str(WEB_OUT_DIR / "dipeen-office-scene.glb"),
                "preview": str(DOC_OUT_DIR / "dipeen-office-scene-preview.png"),
            },
        },
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
