"""Coordinator 실 배선 데모 — 진짜 claude가 회의를 분해(worker 평면, BYOK, propose-only).

회의 transcript → 진짜 claude headless(worker 실행) → JSON plan → parse_llm_plan → decompose → ActionCandidate[].
**실행/confirm 0** — 후보만. 사람이 승인해야 작업이 된다(Core 실행0·승인경계 유지). Core는 키 0(claude auth=worker 로컬).
"""
import asyncio
import os
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

WS = tempfile.mkdtemp(prefix="coord-")        # Windows-native scratch(빈 git repo — run_task가 workspace 필요)
os.environ["NAT_WORKSPACE"] = os.path.join(WS, "nat")
for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
    subprocess.run(cmd, cwd=WS)

import app.nat.providers  # noqa: E402,F401
from app.nat.core import pipeline  # noqa: E402
from app.nat.core.coordinator import decompose, decompose_prompt, parse_llm_plan, render_transcript  # noqa: E402
from app.nat.contracts import Message, SenderRef  # noqa: E402

CY = "\033[36m"
msgs = [Message(room_id="r", sender=SenderRef(type="human", id="user://pm"), body=b) for b in [
    "팀 온보딩 흐름을 개선하자",
    "doctor 출력에 runner support level(primary/preview)을 표시하자",
    "capability_advertised는 probe healthy일 때만이라는 테스트도 추가하자",
]]
transcript = render_transcript(msgs)


async def go():
    return await pipeline.run_task(decompose_prompt(transcript), provider="claude",
                                   workspace_root=WS, store_root=os.environ["NAT_WORKSPACE"],
                                   bypass=True, timeout_sec=220)


print(f"{CY}=== Coordinator 실 배선 — 진짜 claude가 회의 분해 (propose-only) ==={chr(27)}[0m\n")
print("회의 transcript:")
for m in msgs:
    print(f"  - {m.body}")
print("\n진짜 claude headless 실행 중(worker 평면, BYOK)…\n")

outcome = asyncio.run(go())
plan = parse_llm_plan(outcome.raw.stdout)
cands = decompose(msgs, llm=lambda _t: plan)

print(f"{CY}── 진짜 claude 분해 결과(ActionCandidate[]) ──{chr(27)}[0m")
if not cands:
    print("  (파싱된 후보 0 — LLM이 JSON을 안 냄. stdout[:300]:)")
    print("  " + (outcome.raw.stdout or "")[:300].replace("\n", "\n  "))
for c in cands:
    print(f"  • [{c.suggested_role or '미정'}/{c.suggested_provider}] {c.intent}  (repo={c.scope.get('repo') or '-'})")
print(f"\n{CY}{len(cands)} 후보 — propose-only(enqueue/confirm 0). 사람이 승인해야 작업이 된다. Core는 키 0.{chr(27)}[0m")
