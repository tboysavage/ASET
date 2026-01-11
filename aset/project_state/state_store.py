from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from aset.utils.file_ops import ensure_dir


@dataclass
class ProjectSpec:
    raw_prompt: str
    clarified_spec: str


@dataclass
class ArchitectureDoc:
    content: str


@dataclass
class ProjectState:
    spec: ProjectSpec
    architecture: Optional[ArchitectureDoc] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"spec": asdict(self.spec)}
        data["architecture"] = asdict(self.architecture) if self.architecture else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectState":
        spec = ProjectSpec(**data["spec"])
        arch = data.get("architecture")
        architecture = ArchitectureDoc(**arch) if arch else None
        return cls(spec=spec, architecture=architecture)


class ProjectStateStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = ensure_dir(root_dir)
        self._state_file = self.root_dir / "project_state.json"

    def save(self, state: ProjectState) -> None:
        self._state_file.write_text(json.dumps(state.to_dict(), indent=2))

    def load(self) -> ProjectState:
        if not self._state_file.exists():
            raise FileNotFoundError(f"No project_state.json in {self.root_dir}")
        return ProjectState.from_dict(json.loads(self._state_file.read_text()))
