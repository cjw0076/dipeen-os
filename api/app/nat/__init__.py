"""Dipeen NAT — Normalized Agent Translation Layer.

SSOT: docs/nat-architecture-v1.md. 서로 다른 agent runtime(Claude/Codex/OMO/Hermes)을 Dipeen 공통
조직 계약으로 왕복 번역한다. 3원칙: Translation · Isolation · Verification.
구조(§15): contracts(이 step) → core(outbound/inbound/reconciler) → domains → providers.
"""
from . import contracts  # noqa: F401
