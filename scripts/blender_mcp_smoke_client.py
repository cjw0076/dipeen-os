import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "brand-assets" / "blender-mcp-test"


BLENDER_CODE = r'''
import bpy
from mathutils import Vector
from math import radians

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def mat(name, color, roughness=0.42, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    material.blend_method = 'BLEND'
    material.show_transparent_back = False
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    return material

dark = mat("Dipeen Dark Graphite", (0.035, 0.039, 0.048, 1), 0.55)
glass = mat("Dipeen Glass Blue", (0.18, 0.36, 1.0, 0.48), 0.18)
blue = mat("Dipeen FE Blue", (0.23, 0.51, 0.96, 1), 0.32)
green = mat("Dipeen Online Green", (0.20, 0.83, 0.60, 1), 0.28)
edge = mat("Dipeen Edge Metal", (0.5, 0.56, 0.66, 1), 0.22, 0.2)

def cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    obj.color = material.diffuse_color
    bevel = obj.modifiers.new("dipeen_soft_edge", "BEVEL")
    bevel.width = 0.025
    bevel.segments = 3
    obj.modifiers.new("dipeen_weighted_normals", "WEIGHTED_NORMAL")
    return obj

desk = cube("dipeen_prop_desk_body", (0, 0, 0.45), (3.4, 1.5, 0.2), dark)
cube("dipeen_prop_desk_leg_l", (-1.35, -0.5, 0.05), (0.18, 0.18, 0.75), edge)
cube("dipeen_prop_desk_leg_r", (1.35, -0.5, 0.05), (0.18, 0.18, 0.75), edge)
cube("dipeen_prop_monitor", (0, -0.1, 1.15), (1.35, 0.1, 0.82), glass)
cube("dipeen_prop_monitor_base", (0, -0.1, 0.7), (0.32, 0.16, 0.28), edge)
cube("dipeen_prop_keyboard", (0, -0.52, 0.62), (1.25, 0.35, 0.06), edge)
cube("dipeen_prop_terminal_panel", (0.05, -0.155, 1.15), (1.1, 0.045, 0.58), blue)
cube("dipeen_prop_online_dot", (0.52, -0.18, 1.42), (0.12, 0.035, 0.12), green)

bpy.ops.object.light_add(type='AREA', location=(0, -3, 5))
light = bpy.context.object
light.name = "dipeen_key_area_light"
light.data.energy = 450
light.data.size = 4

bpy.ops.object.camera_add(location=(3.6, -4.4, 3.2), rotation=(radians(60), 0, radians(42)))
bpy.context.scene.camera = bpy.context.object

bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
bpy.context.scene.display.shading.color_type = 'MATERIAL'
bpy.context.scene.display.shading.light = 'STUDIO'
bpy.context.scene.display.shading.show_object_outline = False
bpy.context.scene.render.film_transparent = True
bpy.context.scene.render.resolution_x = 1200
bpy.context.scene.render.resolution_y = 900
bpy.context.scene.view_settings.view_transform = 'Standard'
bpy.context.scene.view_settings.look = 'None'

out_dir = r"__OUT_DIR__"
import os
os.makedirs(out_dir, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "dipeen-desk-prop.blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, "dipeen-desk-prop.glb"), export_format='GLB')
bpy.context.scene.render.filepath = os.path.join(out_dir, "dipeen-desk-prop-preview.png")
bpy.ops.render.render(write_still=True)

print("DIPEEN_BLENDER_PROP_READY", out_dir)
'''


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    code = BLENDER_CODE.replace("__OUT_DIR__", str(OUT_DIR).replace("\\", "\\\\"))

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
            tools = await session.list_tools()
            result = await session.call_tool(
                "execute_blender_code",
                {
                    "code": code,
                    "user_prompt": "Create a Dipeen isometric FE desk prop GLB and preview PNG.",
                },
            )
            scene = await session.call_tool(
                "get_scene_info",
                {"user_prompt": "Summarize the generated Dipeen test prop scene."},
            )

    print(json.dumps(
        {
            "tools": [tool.name for tool in tools.tools],
            "execute_result": [item.text for item in result.content if hasattr(item, "text")],
            "scene_info": [item.text for item in scene.content if hasattr(item, "text")],
            "outputs": {
                "blend": str(OUT_DIR / "dipeen-desk-prop.blend"),
                "glb": str(OUT_DIR / "dipeen-desk-prop.glb"),
                "preview": str(OUT_DIR / "dipeen-desk-prop-preview.png"),
            },
        },
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
