from __future__ import annotations

from pathlib import Path

from aset.agents.shared.base_agent import BaseAgent
from aset.llm.router.llm_router import LLMRouter
from aset.project_state.state_store import (
    ProjectState,
    ArchitectureDoc,
)
from aset.utils.file_ops import ensure_dir


class ArchitectAgent(BaseAgent):
    """
    Takes the clarified product spec and produces an architecture document.
    """

    def __init__(self, llm_router: LLMRouter, project_root: Path) -> None:
        super().__init__(llm_router)
        self.project_root = project_root
        self._prompt_path = Path(__file__).with_name("prompt.md")
        self._system_prompt = self._prompt_path.read_text()

    def run(self, state: ProjectState) -> ProjectState:
        self.logger.info("Generating architecture for project.")

        spec_text = state.spec.clarified_spec

        user_prompt = (
            "Here is the clarified product specification:\n\n"
            f"{spec_text}\n\n"
            "Based on this spec, design the architecture as requested in your instructions."
        )

        arch_md = self._call_llm(
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
            role="planning",
        )

        # Persist to filesystem for humans
        arch_dir = ensure_dir(self.project_root / "project_state" / "architecture")
        (arch_dir / "architecture.md").write_text(arch_md)

        # Update ProjectState
        state.architecture = ArchitectureDoc(content=arch_md)
        return state
