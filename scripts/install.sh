#!/bin/sh
# dipeen one-touch bootstrap (Unix). 얇게: uv + dipeen-agent + join만.
#   런타임(bun)·러너·auth는 dipeen-agent setup/BYOK가 담당(이 스크립트 책임 아님).
# 사용: curl -fsSL https://raw.githubusercontent.com/cjw0076/dipeen-os/main/scripts/install.sh \
#         | sh -s -- "https://demo.dipeen.app/join?code=XXXX"
set -e
INVITE="${1:-${DIPEEN_INVITE:-}}"

if ! command -v uv >/dev/null 2>&1; then
  echo "[install] uv 설치…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[install] dipeen-agent 설치(git subdir)…"
uv tool install "git+https://github.com/cjw0076/dipeen-os.git#subdirectory=agent-client"

if [ -n "$INVITE" ]; then
  echo "[install] 팀 합류…"
  dipeen-agent join "$INVITE" --start-worker
else
  echo "설치 완료. 실행: dipeen-agent join \"<invite-url>\" --start-worker"
fi
