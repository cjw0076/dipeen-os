import json
import os
import platform
import shutil
from pathlib import Path

# .env 파일 자동 로드 (agent-client/.env)
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key not in os.environ:  # 환경변수가 이미 있으면 .env보다 우선
                os.environ[key] = val


# API 서버 URL (VPN 내부)
API_URL = os.environ.get("DIPEEN_API_URL", "http://127.0.0.1:8000")

# 에이전트 식별
AGENT_ID = os.environ.get("DIPEEN_AGENT_ID", "fe-agent")
AGENT_ROLE = os.environ.get("DIPEEN_AGENT_ROLE", "Frontend Engineer")

# Phase F: LLM provider + 페르소나 선언
LLM_PROVIDER = os.environ.get("AGENT_LLM_PROVIDER", "anthropic")
# 이 에이전트가 수행 가능한 페르소나 목록 (콤마 구분)
AGENT_PERSONAS = [
    p.strip()
    for p in os.environ.get("AGENT_PERSONAS", "coder").split(",")
    if p.strip()
]

# 실행기 선택 (anthropic provider 한정):
#   claude(기본) — Claude Code `-p`, 단발 실행
#   omo         — oh-my-opencode Ralph Loop(완료까지 자가수정, run-to-true-completion)
# omo 전제: `npm i -g oh-my-opencode` + 1회 `opencode auth login`(구독 → API 크레딧 0).
AGENT_EXECUTOR = os.environ.get("AGENT_EXECUTOR", "claude").lower()
OMO_AGENT      = os.environ.get("OMO_AGENT", "Sisyphus")  # Sisyphus|Hephaestus|Atlas|Prometheus

# L-1: 팀 JWT 토큰 (DIPEEN_TOKEN 환경변수로 설정)
DIPEEN_TOKEN = os.environ.get("DIPEEN_TOKEN", "")

# M-1: 멀티 LLM 프로바이더 설정
AGENT_MODEL       = os.environ.get("AGENT_MODEL", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
KIMI_API_KEY      = os.environ.get("KIMI_API_KEY", "")
QWEN_API_KEY      = os.environ.get("QWEN_API_KEY", "")
TOGETHER_API_KEY  = os.environ.get("TOGETHER_API_KEY", "")
OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OPENAI_COMPAT_BASE_URL = os.environ.get("OPENAI_COMPAT_BASE_URL", "")
OPENAI_COMPAT_API_KEY  = os.environ.get("OPENAI_COMPAT_API_KEY", "none")

# provider → {base_url, api_key, default_model}
# 모두 OpenAI-compatible API → openai Python SDK base_url 스왑으로 동작
_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_COMPAT_URL = os.environ.get("OPENAI_COMPAT_BASE_URL", "")
PROVIDER_CONFIGS: dict[str, dict] = {
    "gemini": {
        "base_url":      "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key":       os.environ.get("GEMINI_API_KEY", ""),
        "default_model": "gemini-2.0-flash",
    },
    "kimi": {
        "base_url":      "https://api.moonshot.cn/v1",
        "api_key":       os.environ.get("KIMI_API_KEY", ""),
        "default_model": "kimi-k2.5",
    },
    "qwen": {
        "base_url":      "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key":       os.environ.get("QWEN_API_KEY", ""),
        "default_model": "qwen2.5-coder-32b-instruct",
    },
    "together": {
        "base_url":      "https://api.together.xyz/v1",
        "api_key":       os.environ.get("TOGETHER_API_KEY", ""),
        "default_model": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    },
    "ollama": {
        "base_url":      _OLLAMA_URL,
        "api_key":       "ollama",  # Ollama는 인증 불필요
        "default_model": "qwen2.5-coder:32b",
    },
    "openai-compat": {
        "base_url":      _COMPAT_URL,
        "api_key":       os.environ.get("OPENAI_COMPAT_API_KEY", "none"),
        "default_model": "",
    },
}

# P-3: 가용 프로바이더 우선순위 체인 (API key가 설정된 것만 포함)
# anthropic은 subprocess 경로로 처리되어 별도 — SDK 경로 provider만 포함
def _build_fallback_chain() -> list[str]:
    chain = []
    _key_envs = {
        "gemini": "GEMINI_API_KEY",
        "kimi": "KIMI_API_KEY",
        "qwen": "QWEN_API_KEY",
        "together": "TOGETHER_API_KEY",
        "ollama": None,  # 로컬 — 항상 가용 (base_url 있으면)
        "openai-compat": "OPENAI_COMPAT_BASE_URL",  # base_url 필요
    }
    for provider, env_var in _key_envs.items():
        if provider == "ollama":
            chain.append(provider)  # 로컬이므로 항상 포함
        elif env_var and os.environ.get(env_var, "").strip():
            chain.append(provider)
    return chain

FALLBACK_CHAIN: list[str] = _build_fallback_chain()

# J-3: 카테고리(복잡도)별 모델 라우팅 — 비용 최적화
# Claude Code CLI는 ANTHROPIC_MODEL 환경변수를 참조
_DEFAULT_CATEGORY_MAP = {
    "trivial": "claude-haiku-4-5",
    "quick":   "claude-haiku-4-5",
    "normal":  "claude-sonnet-4-6",
    "deep":    "claude-sonnet-4-6",
}
try:
    _custom = os.environ.get("CATEGORY_MODEL_MAP_JSON", "")
    CATEGORY_MODEL_MAP: dict[str, str] = (
        json.loads(_custom) if _custom.strip() else _DEFAULT_CATEGORY_MAP
    )
except Exception:
    CATEGORY_MODEL_MAP = _DEFAULT_CATEGORY_MAP

# 에이전트 작업 공간 — dipeen 소스와 분리된 별도 프로젝트 폴더
# DIPEEN_WORKSPACE 환경변수로 대상 프로젝트 경로를 지정
# 기본값: dipeen_v2/../dipeen-projects/default (dipeen 소스 옆에 자동 생성)
_DEFAULT_WORKSPACE = Path(__file__).parent.parent.parent.parent / "dipeen-projects" / "default"
WORKSPACE = Path(os.environ.get("DIPEEN_WORKSPACE", str(_DEFAULT_WORKSPACE))).resolve()

# 복잡도 키워드
TRIVIAL_KEYWORDS = [
    "색상", "color", "배경색", "문자열 변경", "값 수정", "수치 변경",
    "텍스트 변경", "라벨 변경", "단순 수정", "글자 색", "폰트 크기",
]
COMPLEX_KEYWORDS = [
    "새로운", "신규", "아키텍처", "전체", "리팩토링", "refactor",
    "새 컴포넌트", "API 연동", "페이지 추가", "새 페이지", "설계",
]


def find_opencode_exe() -> str:
    """Windows SIGUSR2 우회: opencode.exe 직접 경로 반환."""
    if platform.system() == "Windows":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        candidates = [
            appdata / "npm" / "node_modules" / "opencode-ai" / "node_modules"
                     / "opencode-windows-x64" / "bin" / "opencode.exe",
            appdata / "npm" / "node_modules" / "opencode-ai" / "node_modules"
                     / "opencode-windows-x64-baseline" / "bin" / "opencode.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
    found = shutil.which("opencode")
    return found or "opencode"


# Phase F: provider → CLI 커맨드 빌더
# key: llm_provider 값 / value: (exe_finder, args_builder)
# 새 provider 추가 시 이 맵만 수정하면 됨
def build_cli_cmd(provider: str, prompt: str) -> list[str]:
    """LLM provider에 맞는 CLI 커맨드 반환. 미설치 시 claude CLI로 fallback."""
    provider = provider.lower()

    if provider == "anthropic":
        # 실행기 = omo (oh-my-opencode): Ralph Loop로 완료까지 자가수정.
        # 종료코드 0 = 성공 → runtime의 기존 `returncode == 0` 판정이 그대로 동작(완료 마커 불필요).
        # 산출물은 git diff로 추출(기존 경로 재사용). Popen이 .CMD 풀경로를 shell 없이 직접 실행하므로
        # 큰 프롬프트를 argv로 넘겨도 안전(cmd /c 불필요).
        if AGENT_EXECUTOR == "omo":
            omo = shutil.which("omo") or shutil.which("oh-my-opencode")
            if omo:
                return [omo, "run", "--directory", str(WORKSPACE),
                        "--agent", OMO_AGENT, "--json", prompt]
            print("[agent] AGENT_EXECUTOR=omo 이나 omo 미설치 → claude로 fallback "
                  "(설치: npm i -g oh-my-opencode && opencode auth login)", flush=True)

        claude_exe = shutil.which("claude")
        if claude_exe:
            # Claude Code CLI: -p (print/non-interactive) + --dangerously-skip-permissions (파일 수정 허용)
            return [claude_exe, "-p", "--dangerously-skip-permissions", prompt]
        # opencode fallback
        opencode = find_opencode_exe()
        return [opencode, "run", prompt]

    elif provider == "openai":
        exe = shutil.which("codex")
        if exe:
            return [exe, "exec", "-q", prompt]

    elif provider == "google":
        exe = shutil.which("gemini")
        if exe:
            return [exe, "-p", prompt]

    # fallback: 설치 안 된 provider → opencode
    print(f"[agent] '{provider}' CLI 미설치 → opencode fallback", flush=True)
    return [find_opencode_exe(), "run", prompt]
