from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aset.agents.product_manager.agent import ProductManagerAgent
from aset.agents.backend_engineer.agent import BackendEngineerAgent
from aset.agents.architect.agent import ArchitectAgent
from aset.agents.devops_engineer.agent import DevOpsEngineerAgent
from aset.agents.devops_engineer.config import DevOpsRepairConfig
from aset.llm.router.llm_router import LLMRouter
from aset.project_state.state_store import ProjectStateStore, ProjectState
from aset.utils.file_ops import ensure_dir
from aset.utils.logger import get_logger


@dataclass
class OrchestratorConfig:
    project_root: Path


class Orchestrator:
    """
    Top-level controller.

    v1 pipeline:
    1) Product Manager: clarify spec
    2) Architect: design architecture
    (Next steps later: GitHub scout, engineers, QA, critic, etc.)
    """

    def __init__(self, cfg: OrchestratorConfig) -> None:
        self.cfg = cfg
        self.logger = get_logger("Orchestrator")
        self.llm_router = LLMRouter()

        self.pm_agent = ProductManagerAgent(
            llm_router=self.llm_router,
            project_root=self.cfg.project_root,
        )
        self.architect_agent = ArchitectAgent(
            llm_router=self.llm_router,
            project_root=self.cfg.project_root,
        )
        self.backend_agent = BackendEngineerAgent(
            llm_router=self.llm_router,
            project_root=self.cfg.project_root,
        )
        self.devops_agent = DevOpsEngineerAgent(
            llm_router=self.llm_router,
            project_root=self.cfg.project_root,
            cfg=DevOpsRepairConfig(max_iterations=5),
        )


        # Prepare state store
        state_dir = ensure_dir(self.cfg.project_root / "project_state")
        self.state_store = ProjectStateStore(root_dir=state_dir)

    def run(self, user_prompt: str) -> ProjectState:
        self.logger.info("Starting orchestration for new project.")

        # Phase 1: product specification
        state = self.pm_agent.run(raw_prompt=user_prompt)
        self.state_store.save(state)
        self.logger.info("Specification completed and saved.")

        # Phase 2: architecture design
        state = self.architect_agent.run(state)
        self.state_store.save(state)
        self.logger.info("Architecture completed and saved.")

        # Phase 3: backend generation
        state = self.backend_agent.run(state)
        self.state_store.save(state)
        self.logger.info("Backend generation completed and saved.")

        # Phase 4: DevOps repair loop
        state = self.devops_agent.run(state)
        self.state_store.save(state)
        self.logger.info("DevOps repair phase completed.")




        return state
