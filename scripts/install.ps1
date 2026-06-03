# dipeen one-touch bootstrap (Windows). 얇게: uv + dipeen-agent 설치까지.
#   런타임(bun)·러너·auth는 dipeen-agent setup/BYOK가 담당(이 스크립트 책임 아님).
# 사용: irm https://raw.githubusercontent.com/cjw0076/dipeen-os/main/scripts/install.ps1 | iex
#   그 후: dipeen-agent join "<invite-url>" --start-worker
#   (또는 $env:DIPEEN_INVITE 설정 후 위 한 줄)
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "[install] uv 설치..."
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "[install] dipeen-agent 설치(git subdir)..."
uv tool install "git+https://github.com/cjw0076/dipeen-os.git#subdirectory=agent-client"

if ($env:DIPEEN_INVITE) {
  Write-Host "[install] 팀 합류..."
  dipeen-agent join "$env:DIPEEN_INVITE" --start-worker
} else {
  Write-Host "설치 완료. 실행: dipeen-agent join `"<invite-url>`" --start-worker"
}
