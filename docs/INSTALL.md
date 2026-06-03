# dipeen 원터치 설치

빈 머신에서 한 줄로 팀에 합류합니다. installer는 **uv + dipeen-agent**만 설치하고,
런타임(bun 등)은 `dipeen-agent setup`이, auth(BYOK)는 사용자가 직접 처리합니다.

## Unix (macOS / Linux)
```sh
curl -fsSL https://raw.githubusercontent.com/cjw0076/dipeen-os/main/scripts/install.sh \
  | sh -s -- "https://demo.dipeen.app/api/teams/join?code=XXXX"
```

## Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/cjw0076/dipeen-os/main/scripts/install.ps1 | iex
dipeen-agent join "https://demo.dipeen.app/api/teams/join?code=XXXX" --start-worker
```

## 무엇이 자동인가
- **installer**(install.sh/ps1): `uv` 설치 → `dipeen-agent` 설치(git subdir) → `join`. 그 이상은 하지 않음.
- **`dipeen-agent setup`**: 선택한 러너의 런타임 의존성(omo-opencode → `bun`)을 **러너 설치 전에** 자동 설치.
- **permission 실행**: 기본 `dry_run`(`DIPEEN_PERMISSION_EXECUTOR_MODE`) — 사람이 명시 opt-in해야 실제 실행.
- **auth / BYOK는 자동화하지 않음** — 키는 로컬에만. `setup`이 auth 명령만 안내합니다.

## 설치 후 점검
```
dipeen-agent doctor      # 코어 도구(git/python/node/uv/bun) + 러너 상태 한 화면
dipeen-agent setup --dry-run   # 러너/런타임 설치 계획만(실행 안 함)
```

## 동작 순서 (setup)
1. 러너 상태 확인 → 미설치 목록 산출
2. 미설치 러너의 런타임 의존성(예: `bun`) 먼저 설치
3. 러너 설치(npm/uv)
4. auth 안내(BYOK — 사용자가 직접)
5. `dipeen-agent start` 또는 `worker`로 합류

## 왜 installer는 얇은가
OS 분기·멱등·dry_run·테스트가 필요한 런타임 설치 로직은 Python(`dipeen_agent/onboarding.py`)에
모읍니다. ps1/sh는 부트스트랩(uv + dipeen-agent + join)만 담당해 두 벌의 중복·취약성을 최소화합니다.
설계 근거: `docs/superpowers/specs/one_touch_bootstrap.md`.
