import io
import json
import os
import socket
import traceback
from contextlib import redirect_stdout

import bpy


def _json_ready(buffer: bytes):
    try:
        return json.loads(buffer.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _scene_info():
    objects = []
    for obj in bpy.context.scene.objects:
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "location": [round(value, 4) for value in obj.location],
                "dimensions": [round(value, 4) for value in obj.dimensions],
            }
        )

    return {
        "name": bpy.context.scene.name,
        "object_count": len(bpy.context.scene.objects),
        "objects": objects[:20],
        "materials_count": len(bpy.data.materials),
        "materials": [material.name for material in bpy.data.materials[:20]],
    }


def _execute_code(code: str):
    namespace = {"bpy": bpy}
    capture_buffer = io.StringIO()
    with redirect_stdout(capture_buffer):
        exec(code, namespace)

    return {"executed": True, "result": capture_buffer.getvalue()}


def _execute_command(command):
    command_type = command.get("type")
    params = command.get("params") or {}

    if command_type == "get_telemetry_consent":
        result = {"consent": False}
    elif command_type in {
        "get_polyhaven_status",
        "get_hyper3d_status",
        "get_sketchfab_status",
        "get_hunyuan3d_status",
    }:
        result = {
            "enabled": False,
            "message": f"{command_type} is disabled in the Dipeen headless smoke bridge.",
        }
    elif command_type == "get_scene_info":
        result = _scene_info()
    elif command_type == "execute_code":
        result = _execute_code(params.get("code", ""))
    else:
        raise ValueError(f"Unsupported Blender MCP command: {command_type}")

    return {"status": "success", "result": result}


def _serve(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("localhost", port))
        server.listen(1)
        print(f"BLENDER_MCP_HEADLESS_READY port={port}", flush=True)

        while True:
            client, address = server.accept()
            print(f"Blender MCP headless client connected: {address}", flush=True)
            with client:
                buffer = b""
                while True:
                    chunk = client.recv(8192)
                    if not chunk:
                        break

                    buffer += chunk
                    command = _json_ready(buffer)
                    if command is None:
                        continue

                    try:
                        response = _execute_command(command)
                    except Exception as exc:
                        traceback.print_exc()
                        response = {"status": "error", "message": str(exc)}

                    client.sendall(json.dumps(response).encode("utf-8"))
                    buffer = b""

            print("Blender MCP headless client disconnected", flush=True)


def main() -> None:
    _serve(int(os.environ.get("BLENDER_MCP_PORT", "9876")))


if __name__ == "__main__":
    main()
