"""dipeen workspace — host CLI 핸들러(자족 모듈). cli.py가 한 줄로 와이어(사용자 WIP 충돌 회피).

cli.py의 build_parser()에 추가:
    from .workspace_cli import add_workspace_parser
    add_workspace_parser(sub)      # sub = p.add_subparsers(...)

`dipeen workspace init --mode public-demo` → .dipeen/workspace.yaml → web UI가 그 mode로 렌더.
"""
from __future__ import annotations

import argparse
import json

import yaml

from .core import workspace_spec as ws

_MODES = ["public_demo", "team", "production", "debug"]


def cmd_workspace(args) -> int:
    action = getattr(args, "action", None)
    root = getattr(args, "root", ".") or "."
    if action == "init":
        mode = getattr(args, "mode", "team").replace("-", "_")
        spec = ws.default_spec(mode if mode in _MODES else "team", workspace_id=getattr(args, "id", "default"))
        p = ws.save_spec(spec, root)
        print(f"[workspace] init mode={spec.mode} → {p}")
        print(f"[workspace] panels: {', '.join(spec.ui.panels)}")
        return 0
    if action == "apply":
        spec = ws.load_spec(root)
        if spec is None:
            print("[workspace] .dipeen/workspace.yaml 없음 — 먼저 `dipeen workspace init`")
            return 1
        ws.save_spec(spec, root)
        print(f"[workspace] applied mode={spec.mode} ({len(spec.ui.panels)} panels)")
        return 0
    if action == "compose":
        mode = getattr(args, "mode", None)
        spec = ws.load_spec(root)
        if spec is None:
            normalized = (mode or "team").replace("-", "_")
            spec = ws.default_spec(normalized if normalized in _MODES else "team",
                                   workspace_id=getattr(args, "id", "default"))
        payload = spec.model_dump(mode="json")
        if getattr(args, "format", "yaml") == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
        return 0
    if action == "open":
        import webbrowser
        url = getattr(args, "url", "http://localhost:3000") or "http://localhost:3000"
        print(f"[workspace] open {url}")
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — headless면 그냥 URL만 출력
            pass
        return 0
    print("[workspace] init | apply | open 중 하나")
    return 1


def add_workspace_parser(sub) -> None:
    """cli.py build_parser()에서 호출: add_workspace_parser(sub)."""
    w = sub.add_parser("workspace", help="팀 작업공간 구성(mode→web UI). host가 spec을 만들고 web은 렌더만")
    wa = w.add_subparsers(dest="action", required=True)

    init = wa.add_parser("init", help="mode로 .dipeen/workspace.yaml 생성")
    init.add_argument("--mode", default="team", help="public-demo | team | production | debug")
    init.add_argument("--id", dest="id", default="default", help="workspace_id")
    init.add_argument("--root", default=".", help="작업공간 루트(.dipeen/ 생성 위치)")
    init.set_defaults(fn=cmd_workspace)

    ap = wa.add_parser("apply", help="현재 workspace.yaml 재적용")
    ap.add_argument("--root", default=".")
    ap.set_defaults(fn=cmd_workspace)

    cp = wa.add_parser("compose", help="현재 또는 기본 TeamWorkspaceSpec 출력")
    cp.add_argument("--root", default=".")
    cp.add_argument("--mode", default=None, help="spec이 없을 때 사용할 mode")
    cp.add_argument("--id", dest="id", default="default", help="spec이 없을 때 사용할 workspace_id")
    cp.add_argument("--format", choices=["yaml", "json"], default="yaml")
    cp.set_defaults(fn=cmd_workspace)

    op = wa.add_parser("open", help="web UI 열기")
    op.add_argument("--url", default="http://localhost:3000")
    op.set_defaults(fn=cmd_workspace)
