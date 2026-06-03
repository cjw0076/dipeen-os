"""
P-1: claw-code 패턴 6개 도구 정의 + execute_tool().

openai function calling 스키마로 정의 → run_agent_loop()에서 tool_calls 실행.
참조: claw-code-main/src/tools.py, not-claude-code-emulator-master/src/routes/messages.ts
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

# ─── Tool Schema (openai function calling format) ───────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "bash_execute",
            "description": (
                "Run a shell command in the workspace directory. "
                "Use for build, test, git operations, installing packages, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read the contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from workspace root",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default: 8000)",
                        "default": 8000,
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write or overwrite a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from workspace root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_patch",
            "description": (
                "Replace the first occurrence of 'old' with 'new' in a file. "
                "Use for targeted edits without rewriting the whole file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from workspace root",
                    },
                    "old": {
                        "type": "string",
                        "description": "Exact text to find (must be unique in file)",
                    },
                    "new": {
                        "type": "string",
                        "description": "Replacement text",
                    },
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a path in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from workspace root (default: '.')",
                        "default": ".",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a pattern in workspace files (grep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex or literal string to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Subdirectory to search in (default: workspace root)",
                        "default": ".",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "File glob pattern to filter (e.g. '*.py')",
                        "default": "*",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


# ─── Tool Executor ────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, workspace: Path) -> str:
    """도구 이름 + 인자 → 결과 문자열. 실패 시 'error: ...' 접두어."""
    try:
        match name:
            case "bash_execute":
                return _bash_execute(args, workspace)
            case "file_read":
                return _file_read(args, workspace)
            case "file_write":
                return _file_write(args, workspace)
            case "file_patch":
                return _file_patch(args, workspace)
            case "list_dir":
                return _list_dir(args, workspace)
            case "search_files":
                return _search_files(args, workspace)
            case _:
                return f"error: unknown tool '{name}'"
    except Exception as e:
        return f"error: {name} failed — {e}"


def _bash_execute(args: dict, workspace: Path) -> str:
    command = args.get("command", "")
    timeout = int(args.get("timeout", 30))
    if not command:
        return "error: command is required"
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = r.stdout
        err = r.stderr
        parts = []
        if out.strip():
            parts.append(out.strip())
        if err.strip():
            parts.append(f"[stderr]\n{err.strip()}")
        if r.returncode != 0:
            parts.append(f"[exit code: {r.returncode}]")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s"


def _file_read(args: dict, workspace: Path) -> str:
    rel = args.get("path", "").lstrip("/")
    max_chars = int(args.get("max_chars", 8000))
    if not rel:
        return "error: path is required"
    target = workspace / rel
    if not target.exists():
        return f"error: file not found: {rel}"
    if not target.is_file():
        return f"error: not a file: {rel}"
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... (truncated at {max_chars} chars)"
        return content
    except Exception as e:
        return f"error: cannot read {rel} — {e}"


def _file_write(args: dict, workspace: Path) -> str:
    rel = args.get("path", "").lstrip("/")
    content = args.get("content", "")
    if not rel:
        return "error: path is required"
    target = workspace / rel
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"written: {rel} ({len(content)} chars)"
    except Exception as e:
        return f"error: cannot write {rel} — {e}"


def _file_patch(args: dict, workspace: Path) -> str:
    rel = args.get("path", "").lstrip("/")
    old_text = args.get("old", "")
    new_text = args.get("new", "")
    if not rel:
        return "error: path is required"
    if not old_text:
        return "error: old text is required"
    target = workspace / rel
    if not target.exists():
        return f"error: file not found: {rel}"
    try:
        original = target.read_text(encoding="utf-8", errors="replace")
        if old_text not in original:
            return f"error: old text not found in {rel}"
        patched = original.replace(old_text, new_text, 1)
        target.write_text(patched, encoding="utf-8")
        return f"patched: {rel}"
    except Exception as e:
        return f"error: cannot patch {rel} — {e}"


def _list_dir(args: dict, workspace: Path) -> str:
    rel = args.get("path", ".").lstrip("/") or "."
    target = workspace / rel
    if not target.exists():
        return f"error: path not found: {rel}"
    try:
        entries = []
        for item in sorted(target.iterdir()):
            kind = "dir" if item.is_dir() else "file"
            size = ""
            if item.is_file():
                try:
                    size = f" ({item.stat().st_size} bytes)"
                except Exception:
                    pass
            entries.append(f"{kind}  {item.name}{size}")
        return "\n".join(entries) if entries else "(empty directory)"
    except Exception as e:
        return f"error: cannot list {rel} — {e}"


def _search_files(args: dict, workspace: Path) -> str:
    pattern = args.get("pattern", "")
    search_path = args.get("path", ".").lstrip("/") or "."
    file_glob = args.get("file_glob", "*")
    if not pattern:
        return "error: pattern is required"
    target = workspace / search_path

    # ripgrep 우선, 없으면 grep fallback
    try:
        rg = subprocess.run(
            ["rg", "--no-heading", "-n", "--glob", file_glob, pattern, str(target)],
            capture_output=True, text=True, timeout=15,
        )
        if rg.returncode in (0, 1):  # 0=found, 1=not found
            out = rg.stdout.strip()
            if not out:
                return f"no matches for '{pattern}'"
            lines = out.splitlines()
            if len(lines) > 50:
                lines = lines[:50]
                lines.append(f"... ({len(out.splitlines()) - 50} more lines truncated)")
            return "\n".join(lines)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # grep fallback
    try:
        r = subprocess.run(
            ["grep", "-r", "-n", pattern, str(target),
             "--include", file_glob, "--max-count=50"],
            capture_output=True, text=True, timeout=15,
        )
        out = r.stdout.strip()
        return out if out else f"no matches for '{pattern}'"
    except Exception as e:
        return f"error: search failed — {e}"
