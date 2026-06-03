"""ArtifactStore (M1 / §5,9) — artifacts/{artifact_id}/manifest.json (+선택 content 파일).

조직 기억의 핵심은 채팅 아니라 산출물. Artifact는 1급이고 영속. content_ref는 같은 폴더의 파일을 가리킨다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contracts import Artifact, ArtifactLocation


class ArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root) / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, artifact: Artifact, *, content: Optional[bytes] = None,
             filename: Optional[str] = None) -> Artifact:
        d = self.root / artifact.artifact_id
        d.mkdir(parents=True, exist_ok=True)
        if content is not None and filename:
            (d / filename).write_bytes(content)
            # content를 가리키는 location 자동 추가(없으면)
            uri = f"file://{(d / filename).as_posix()}"
            if not any(loc.uri == uri for loc in artifact.locations):
                artifact.locations.append(ArtifactLocation(uri=uri))
        (d / "manifest.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        return artifact

    def save_all(self, artifacts: list[Artifact]) -> None:
        for a in artifacts:
            self.save(a)

    def load(self, artifact_id: str) -> Optional[Artifact]:
        m = self.root / artifact_id / "manifest.json"
        if not m.exists():
            return None
        return Artifact.model_validate_json(m.read_text(encoding="utf-8"))

    def list(self, *, task_id: Optional[str] = None) -> list[Artifact]:
        out: list[Artifact] = []
        for d in sorted(self.root.glob("A-*")):
            a = self.load(d.name)
            if a and (task_id is None or a.task_id == task_id):
                out.append(a)
        return out
