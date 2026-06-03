"""omo-bun link — omo가 bun을 못 찾는 spawnSync ENOENT 진단·수정(BUN_BINARY 자동 설정).

빈 머신 부트스트랩 자동화: bun 설치 후 omo(oh-my-opencode)가 내부 spawnSync("bun")로 bun.exe를
찾도록 BUN_BINARY를 잡아준다(npm 셰임 bun.cmd만 PATH에 있을 때 ENOENT 나는 문제).
"""
import os
import platform
from pathlib import Path

from dipeen_agent import bun_link


def test_find_bun_binary_from_env(monkeypatch, tmp_path):
    bun = tmp_path / "bun.exe"
    bun.write_text("", encoding="utf-8")
    monkeypatch.setenv("BUN_BINARY", str(bun))
    assert bun_link.find_bun_binary() == str(bun)


def test_find_bun_binary_from_npm_node_modules(monkeypatch, tmp_path):
    monkeypatch.delenv("BUN_BINARY", raising=False)
    monkeypatch.setattr(bun_link.os.path, "expanduser", lambda p: str(tmp_path / "nohome"))
    npm = tmp_path / "npm"
    npm.mkdir()
    (npm / "bun.cmd").write_text("", encoding="utf-8")           # 셰임만 PATH에
    nm = npm / "node_modules" / "bun" / "bin"
    nm.mkdir(parents=True)
    (nm / "bun.exe").write_text("", encoding="utf-8")            # 실체
    monkeypatch.setattr(bun_link.shutil, "which", lambda n: str(npm / "bun.cmd") if n == "bun" else None)
    assert bun_link.find_bun_binary() == str(nm / "bun.exe")


def test_find_bun_binary_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("BUN_BINARY", raising=False)
    monkeypatch.setattr(bun_link.os.path, "expanduser", lambda p: str(tmp_path / "nohome"))
    monkeypatch.setattr(bun_link.shutil, "which", lambda n: None)
    assert bun_link.find_bun_binary() is None


def test_bun_link_command_windows(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    cmd = bun_link.bun_link_command("C:/x/bun.exe")
    assert "setx BUN_BINARY" in cmd and "bun.exe" in cmd


def test_bun_link_command_unix(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert "export BUN_BINARY" in bun_link.bun_link_command("/x/bun")


def test_needs_bun_link_true_when_env_unset_and_shim_only(monkeypatch, tmp_path):
    monkeypatch.delenv("BUN_BINARY", raising=False)
    monkeypatch.setattr(bun_link.shutil, "which", lambda n: str(tmp_path / "bun.cmd") if n == "bun" else None)
    assert bun_link.needs_bun_link() is True                     # 셰임만 + BUN_BINARY 없음 → link 필요


def test_needs_bun_link_false_when_env_set(monkeypatch, tmp_path):
    bun = tmp_path / "bun.exe"
    bun.write_text("", encoding="utf-8")
    monkeypatch.setenv("BUN_BINARY", str(bun))
    assert bun_link.needs_bun_link() is False                    # BUN_BINARY 설정됨 → link 불필요


def test_apply_bun_link_dry_run_no_exec(monkeypatch, tmp_path, capsys):
    bun = tmp_path / "bun.exe"
    bun.write_text("", encoding="utf-8")
    monkeypatch.setattr(bun_link, "find_bun_binary", lambda: str(bun))
    called = []
    monkeypatch.setattr(bun_link.subprocess, "run", lambda *a, **k: called.append(a) or None)
    rc = bun_link.apply_bun_link(dry_run=True)
    assert rc == 0
    assert called == []                                          # dry_run은 setx 실행 0
    assert "BUN_BINARY" in capsys.readouterr().out


def test_apply_bun_link_no_bun_fails(monkeypatch):
    monkeypatch.setattr(bun_link, "find_bun_binary", lambda: None)
    assert bun_link.apply_bun_link() == 1                        # bun 실파일 없으면 실패(정직)
