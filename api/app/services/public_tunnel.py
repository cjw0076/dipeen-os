"""공개 도달성 — Cloudflare quick tunnel로 로컬 HQ를 공개 HTTPS/WSS로 노출.

VPS 없이 노드/관객 폰이 HQ에 닿게 한다(다중 디바이스 데모의 도달성 층). cloudflared가 outbound로
CF에 붙어 NAT·인바운드 포트 0, 자동 TLS, *계정 불요*(quick tunnel). dipeen-up/온보딩이 호출.

- quick tunnel: 지금 즉시, 무계정 → 랜덤 `*.trycloudflare.com` (데모용).
- named tunnel(고정 도메인): Cloudflare API/MCP + 도메인 필요 → 후속(production).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared() -> str | None:
    """PATH → winget Links → winget Packages 순으로 cloudflared 탐색."""
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    link = local / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe"
    if link.exists():
        return str(link)
    pkgs = local / "Microsoft" / "WinGet" / "Packages"
    if pkgs.exists():
        for p in pkgs.glob("Cloudflare.cloudflared_*/cloudflared.exe"):
            return str(p)
    return None


def install_hint() -> str:
    return "cloudflared 미설치 — `winget install Cloudflare.cloudflared` (또는 `npm i -g cloudflared`)"


def wss_url(https_url: str, path: str = "/ws/hermes/agent") -> str:
    """공개 https URL → 노드가 붙을 wss URL."""
    return https_url.replace("https://", "wss://", 1).rstrip("/") + path


def start_quick_tunnel(port: int = 8000, timeout: float = 30.0):
    """cloudflared quick tunnel 시작 → (proc, public_https_url).

    종료: proc.terminate(). cloudflared가 종단점을 출력할 때까지(최대 timeout) 대기.
    """
    exe = find_cloudflared()
    if not exe:
        raise RuntimeError(install_hint())
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                raise RuntimeError("cloudflared가 종료됨 — 터널 실패")
            continue
        m = _URL_RE.search(line)
        if m:
            return proc, m.group(0)
    proc.terminate()
    raise RuntimeError("터널 URL을 시간 내 받지 못함")


def build_human_url(web_url: str, api_url: str) -> str:
    """사람이 열 web URL — web 터널에 ?api=<인코딩된 api 터널>을 붙인다."""
    return web_url.rstrip("/") + "/?api=" + urllib.parse.quote(api_url, safe="")


def start_dual_tunnel(api_port: int = 8000, web_port: int = 3000, timeout: float = 30.0):
    """API·web 두 quick tunnel 기동 → (api_proc, api_url, web_proc, web_url).

    둘 다 성공해야 반환한다. web 터널이 실패하면 이미 뜬 api 터널을 정리한다(부분 노출 방지).
    """
    api_proc, api_url = start_quick_tunnel(api_port, timeout=timeout)
    try:
        web_proc, web_url = start_quick_tunnel(web_port, timeout=timeout)
    except Exception:
        api_proc.terminate()
        raise
    return api_proc, api_url, web_proc, web_url


if __name__ == "__main__":  # `cd api && python -m app.services.public_tunnel`
    _api_port = int(os.environ.get("DIPEEN_HQ_PORT", "8000"))
    _web_port = int(os.environ.get("DIPEEN_WEB_PORT", "3000"))
    print(f"[tunnel] HQ API(:{_api_port}) + web(:{_web_port})를 공개로 노출하는 중… (cloudflared ×2)")
    try:
        _api_proc, _api_url, _web_proc, _web_url = start_dual_tunnel(_api_port, _web_port)
    except RuntimeError as e:
        print(f"[tunnel] 실패: {e}")
        raise SystemExit(1)
    _human = build_human_url(_web_url, _api_url)
    print(f"[tunnel] 공개 API   : {_api_url}")
    print(f"[tunnel] 공개 web   : {_web_url}")
    print(f"[tunnel] 노드 WSS   : {wss_url(_api_url)}")
    print("[tunnel] ── 사람(관전+운영): 이 URL을 폰/브라우저로 여세요 ──")
    print(f"[tunnel]   {_human}")
    print("[tunnel] ── 워커(다른 PC) 합류 ──")
    print(f"[tunnel]   dipeen-agent connect --code <CODE> --api-url {_api_url}")
    print("[tunnel] ⚠ quick tunnel은 로컬 HQ를 공개 인터넷에 노출합니다 — 테스트 중에만 켜고 끝나면 Ctrl+C.")
    print("[tunnel] (Ctrl+C로 종료)")
    try:
        _api_proc.wait()
    except KeyboardInterrupt:
        _api_proc.terminate()
        _web_proc.terminate()
