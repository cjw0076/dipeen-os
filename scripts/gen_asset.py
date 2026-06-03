#!/usr/bin/env python3
"""Generate a Dipeen raster asset from a prompt.

This script is intentionally small and dependency-light. It calls the OpenAI
Images API, writes the source PNG, then writes a transparent PNG copy. If the
model output is opaque magenta chroma key, it removes that key locally.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import time
from pathlib import Path

import requests
from PIL import Image


IMAGE_ENDPOINT = "https://api.openai.com/v1/images/generations"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Dipeen UI asset PNG.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--source", required=True, help="Repo-relative or absolute output PNG path.")
    parser.add_argument("--transparent", help="Repo-relative or absolute transparent PNG path.")
    parser.add_argument("--root", default=".", help="Workspace root for relative paths.")
    parser.add_argument("--model", default=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"))
    parser.add_argument("--size", default=os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"))
    parser.add_argument("--quality", default=os.getenv("OPENAI_IMAGE_QUALITY", "low"))
    parser.add_argument(
        "--background",
        choices=["transparent", "opaque", "auto"],
        default=os.getenv("OPENAI_IMAGE_BACKGROUND", "transparent"),
    )
    return parser.parse_args()


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def transparent_prompt(prompt: str) -> str:
    replacements = {
        "on a perfectly flat solid #ff00ff chroma-key background for background removal": "with a clean transparent background",
        "on a transparent-friendly solid #ff00ff chroma-key background": "with a clean transparent background",
        "Background: one uniform #ff00ff color only, no floor, no shadow, no reflection, no texture, no text, no watermark.": "Background: transparent PNG only, no floor, no shadow, no reflection, no texture, no text, no watermark.",
        "Avoid using #ff00ff anywhere in the subject.": "",
    }
    normalized = prompt
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized.strip() + "\nReturn a PNG with transparent background."


def call_image_api(args: argparse.Namespace, prompt: str) -> bytes:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    payload = {
        "model": args.model,
        "prompt": prompt,
        "size": args.size,
        "quality": args.quality,
        "n": 1,
        "output_format": "png",
        "background": args.background,
    }

    response = requests.post(
        IMAGE_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI Images API failed: {response.status_code} {response.text[:1000]}")

    data = response.json()
    try:
        image_b64 = data["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected image response shape: {json.dumps(data)[:1000]}") from exc

    return base64.b64decode(image_b64)


def has_transparency(path: Path) -> bool:
    with Image.open(path) as image:
        if image.mode not in ("RGBA", "LA"):
            return False
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255


def remove_magenta_key(source: Path, target: Path, tolerance: int = 32) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
        pixels = []
        for red, green, blue, alpha in rgba.getdata():
            is_key = (
                abs(red - 255) <= tolerance
                and green <= tolerance
                and abs(blue - 255) <= tolerance
            )
            pixels.append((red, green, blue, 0 if is_key else alpha))
        rgba.putdata(pixels)
        rgba.save(target)


def write_metadata(source: Path, args: argparse.Namespace, prompt: str) -> None:
    metadata = {
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": args.model,
        "size": args.size,
        "quality": args.quality,
        "background": args.background,
        "prompt": prompt,
    }
    source.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    source = resolve_path(root, args.source)
    transparent = resolve_path(root, args.transparent) if args.transparent else None
    api_prompt = transparent_prompt(args.prompt) if args.background == "transparent" else args.prompt

    source.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = call_image_api(args, api_prompt)
    source.write_bytes(image_bytes)
    write_metadata(source, args, api_prompt)

    if transparent:
        if has_transparency(source):
            transparent.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, transparent)
        else:
            remove_magenta_key(source, transparent)

    print(json.dumps({
        "source": str(source),
        "transparent": str(transparent) if transparent else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"gen_asset.py error: {exc}", file=sys.stderr)
        raise SystemExit(1)
