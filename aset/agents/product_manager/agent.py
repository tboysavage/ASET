from __future__ import annotations

from pathlib import Path

from aset.agents.shared.base_agent import BaseAgent
from aset.llm.router.llm_router import LLMRouter
from aset.project_state.state_store import ProjectSpec, ProjectState
from aset.utils.file_ops import ensure_dir


class ProductManagerAgent(BaseAgent):
    """
    Interprets the raw user prompt and produces a clarified product spec.
    """

    def __init__(self, llm_router: LLMRouter, project_root: Path) -> None:
        super().__init__(llm_router)
        self.project_root = project_root
        self._prompt_path = Path(__file__).with_name("prompt.md")
        self._system_prompt = self._prompt_path.read_text()

    def run(self, raw_prompt: str) -> ProjectState:
        self.logger.info("Generating clarified spec for prompt: %s", raw_prompt)

        user_prompt = (
            "User request:\n"
            f"{raw_prompt}\n\n"
            "Please produce a clarified product spec. "
            "Use Markdown with headings: Overview, User Roles, Functional Requirements, "
            "Non-Functional Requirements, MVP Scope, Out of Scope."
        )

        clarified_spec = self._call_llm(
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
            role="planning",
        )

        spec = ProjectSpec(
            raw_prompt=raw_prompt,
            clarified_spec=clarified_spec,
        )
        state = ProjectState(spec=spec)

        # Persist spec into project_state/requirements/spec.md for humans too
        req_dir = ensure_dir(self.project_root / "project_state" / "requirements")
        (req_dir / "spec.md").write_text(clarified_spec)

        return state
