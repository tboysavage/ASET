from __future__ import annotations

from pathlib import Path

from aset.agents.shared.base_agent import BaseAgent
from aset.project_state.state_store import ProjectState
from aset.llm.router.llm_router import LLMRequest
from aset.utils.file_ops import ensure_dir


class BackendEngineerAgent(BaseAgent):
    """
    Generates backend code as a big text blob.
    DevOpsEngineerAgent is responsible for turning that into files.
    """

    def __init__(self, llm_router, project_root: Path) -> None:
        super().__init__(llm_router)
        self.project_root = project_root
        self._prompt_path = Path(__file__).with_name("prompt.md")
        self._system_prompt = self._prompt_path.read_text()

    def run(self, state: ProjectState) -> ProjectState:

        if state.architecture is None:
            raise ValueError("Architecture is required before backend generation.")

        spec = state.spec.clarified_spec
        arch = state.architecture.content

        user_prompt = (
            "CLARIFIED SPEC:\n\n"
            f"{spec}\n\n"
            "ARCHITECTURE:\n\n"
            f"{arch}\n\n"
            "Generate the backend codebase now, following the file bundle format."
        )

        req = LLMRequest(
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            role="code_gen",
        )
        output = self._call_llm(req)

        out_dir = ensure_dir(self.project_root / "project_state" / "codebase")
        raw_path = out_dir / "backend_generation.txt"
        raw_path.write_text(output)

        self.logger.info("Backend raw generation saved to %s", raw_path)
        return state
