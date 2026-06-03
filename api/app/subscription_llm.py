"""Credit-free Claude calls via the local Claude Max **subscription** OAuth token.

dipeen 원칙 #6 (구독-크레딧0): ANTHROPIC_API_KEY 없이, 이미 로그인된 Claude Code
구독 세션의 OAuth 토큰(`~/.claude/.credentials.json`)으로 Anthropic Messages API를
직접 호출한다. API 키 과금 0.

이 모듈은 Claude Code가 쓰는 **공개 OAuth 프로토콜**(Bearer + `oauth-2025-04-20`
beta + Claude Code 신원 system 블록)을 직접 구현한다. 토큰 해석/리프레시 패턴은
nousresearch/hermes-agent(`agent/anthropic_adapter.py`)를 참조해 재구현했다 — 같은
프로토콜을 opencode·pi-ai 등도 동일하게 사용.

왜 subprocess(`claude -p`)가 아니라 직접 호출인가:
  - `claude -p`는 전체 Claude Code 프로세스를 띄워 느리고, 빈 출력 시 JSON 파싱이
    깨진다(live 버그: "Expecting value: line 1 column 1"). 직접 호출은 깨끗한 JSON을
    빠르게 돌려주고 구독으로 크레딧 0을 유지한다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

# ── 프로토콜 상수 (Claude Code가 보내는 것과 동일) ──────────────────────────
_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_OAUTH_TOKEN_URLS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)
_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_OAUTH_BETAS = "claude-code-20250219,oauth-2025-04-20"
_ANTHROPIC_VERSION = "2023-06-01"
# OAuth 요청은 system 프롬프트 첫 블록이 Claude Code 신원이어야 라우팅된다.
_CC_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."
_CC_VERSION_FALLBACK = "2.1.114"
_EXPIRY_BUFFER_MS = 60_000

_CRED_PATH = Path.home() / ".claude" / ".credentials.json"
_cc_version_cache: Optional[str] = None


# ── Claude Code 버전 (User-Agent — 너무 낮으면 Anthropic이 거부) ────────────
def claude_code_version() -> str:
    global _cc_version_cache
    if _cc_version_cache is not None:
        return _cc_version_cache
    ver = _CC_VERSION_FALLBACK
    appdata = os.environ.get("APPDATA", "")
    candidates = [
        Path(appdata) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "package.json",
        Path.home() / ".npm-global" / "lib" / "node_modules" / "@anthropic-ai" / "claude-code" / "package.json",
        Path("/usr/local/lib/node_modules/@anthropic-ai/claude-code/package.json"),
    ]
    for pkg in candidates:
        try:
            if pkg.exists():
                v = json.loads(pkg.read_text(encoding="utf-8")).get("version")
                if v and str(v)[0].isdigit():
                    ver = str(v)
                    break
        except Exception:
            continue
    _cc_version_cache = ver
    return ver


def _user_agent() -> str:
    return f"claude-cli/{claude_code_version()} (external, cli)"


# ── 자격증명 읽기/검증/리프레시 ──────────────────────────────────────────────
def read_credentials() -> Optional[dict[str, Any]]:
    """`~/.claude/.credentials.json`의 claudeAiOauth 블록을 반환 (없으면 None)."""
    try:
        if not _CRED_PATH.exists():
            return None
        data = json.loads(_CRED_PATH.read_text(encoding="utf-8"))
        oauth = data.get("claudeAiOauth")
        if isinstance(oauth, dict) and oauth.get("accessToken"):
            return {
                "accessToken": oauth["accessToken"],
                "refreshToken": oauth.get("refreshToken", ""),
                "expiresAt": oauth.get("expiresAt", 0),
                "scopes": oauth.get("scopes", []),
            }
    except Exception:
        return None
    return None


def _is_valid(creds: dict[str, Any]) -> bool:
    exp = creds.get("expiresAt", 0)
    if not exp:
        return bool(creds.get("accessToken"))
    return int(time.time() * 1000) < (exp - _EXPIRY_BUFFER_MS)


def _refresh(creds: dict[str, Any]) -> Optional[str]:
    """만료된 OAuth 토큰을 refresh_token으로 갱신하고 파일에 기록. 새 access token 반환."""
    refresh_token = creds.get("refreshToken", "")
    if not refresh_token:
        return None
    payload = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": _OAUTH_CLIENT_ID,
    }).encode()
    for endpoint in _OAUTH_TOKEN_URLS:
        try:
            req = urllib.request.Request(
                endpoint, data=payload, method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": _user_agent(),
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            access = result.get("access_token", "")
            if not access:
                continue
            _write_back(
                access,
                result.get("refresh_token", refresh_token),
                int(time.time() * 1000) + int(result.get("expires_in", 3600)) * 1000,
            )
            return access
        except Exception:
            continue
    return None


def _write_back(access: str, refresh: str, expires_at_ms: int) -> None:
    """갱신된 자격증명을 credentials.json에 원자적으로 기록 (다른 필드 보존)."""
    try:
        existing: dict[str, Any] = {}
        if _CRED_PATH.exists():
            existing = json.loads(_CRED_PATH.read_text(encoding="utf-8"))
        oauth = existing.get("claudeAiOauth", {})
        oauth["accessToken"] = access
        oauth["refreshToken"] = refresh
        oauth["expiresAt"] = expires_at_ms
        existing["claudeAiOauth"] = oauth
        _CRED_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CRED_PATH.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        os.replace(tmp, _CRED_PATH)  # atomic
    except Exception:
        pass  # best-effort: 다음 호출에서 재시도


def resolve_oauth_token() -> Optional[str]:
    """크레딧 0 OAuth access token 해석.

    우선순위: CLAUDE_CODE_OAUTH_TOKEN 환경변수 → credentials.json(만료 시 자동 리프레시).
    ANTHROPIC_API_KEY는 (과금되므로) 일부러 사용하지 않는다.
    """
    env_tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    creds = read_credentials()
    # 리프레시 가능한 파일 자격증명이 있으면 그것을 선호 (정적 env 토큰은 갱신 불가)
    if env_tok and not (creds and creds.get("refreshToken")):
        return env_tok
    if creds:
        if _is_valid(creds):
            return creds["accessToken"]
        refreshed = _refresh(creds)
        if refreshed:
            return refreshed
    return env_tok or None


def available() -> bool:
    """구독 크레딧0 경로가 사용 가능한가 (토큰 해석 가능 여부)."""
    return resolve_oauth_token() is not None


# ── 직접 Messages API 호출 (크레딧 0) ────────────────────────────────────────
def _build_system(system: Optional[str]) -> list[dict[str, str]]:
    blocks = [{"type": "text", "text": _CC_SYSTEM_PREFIX}]
    if system:
        blocks.append({"type": "text", "text": system})
    return blocks


def complete_text(
    system: str,
    user_content: str,
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 2048,
    timeout: int = 180,
) -> str:
    """구독 OAuth로 Messages API를 직접 호출 → assistant 텍스트 반환 (크레딧 0).

    실패 시 예외를 던진다 (호출자가 fallback 결정).
    """
    token = resolve_oauth_token()
    if not token:
        raise RuntimeError("구독 OAuth 토큰 없음 — `claude` 로그인 필요 (크레딧0 경로 불가)")
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": _build_system(system),
        "messages": [{"role": "user", "content": user_content or "응답하세요."}],
    }
    req = urllib.request.Request(
        _MESSAGES_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
            "anthropic-beta": _OAUTH_BETAS,
            "authorization": f"Bearer {token}",
            "user-agent": _user_agent(),
            "x-app": "cli",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def _extract_json(text: str) -> dict:
    """assistant 텍스트에서 JSON 객체 추출 (코드펜스/잡음 제거)."""
    t = text.strip()
    if "```" in t:
        seg = t.split("```")
        t = seg[1] if len(seg) > 1 else t
        if t.startswith("json"):
            t = t[4:]
    if "{" in t and "}" in t:
        t = t[t.index("{"): t.rindex("}") + 1]
    if not t:
        return {}
    return json.loads(t)


def complete_json(
    system: str,
    user_content: str,
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 2048,
    timeout: int = 180,
) -> dict:
    """complete_text + JSON 파싱 (pm_loop의 `_call_claude_cli` drop-in)."""
    instr = (
        "\n\n[IMPORTANT: Output ONLY the raw JSON object described above. "
        "No prose, no markdown fences.]"
    )
    text = complete_text(
        (system or "") , (user_content or "응답하세요.") + instr,
        model=model, max_tokens=max_tokens, timeout=timeout,
    )
    return _extract_json(text)
