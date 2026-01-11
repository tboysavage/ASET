from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Literal

from aset.llm.providers.gemini_api import GeminiProvider
from aset.llm.providers.local_llm_api import LocalLLMProvider

logger = logging.getLogger(__name__)

LLMRole = Literal["planning", "code_gen", "devops"]


@dataclass
class LLMRequest:
    messages: List[Dict[str, str]]
    role: LLMRole = "code_gen"


class LLMRouter:
    """
    Simple multi-provider router:
    - Chooses provider chain based on `role`
    - Tries providers in order, falling back on exceptions
    """

    def __init__(self) -> None:
        # Read config from env (optional)
        #gemini_model = os.getenv("GEMINI_MODEL_PLANNING", "gemini-2.0-flash")
        planning_model = os.getenv("GEMINI_MODEL_PLANNING", "gemini-2.5-pro")
        code_model = os.getenv("GEMINI_MODEL_CODE", "gemini-2.5-pro")
        devops_model = os.getenv("GEMINI_MODEL_DEVOPS", "gemini-2.5-pro")
        # Gemini providers
        self._gemini_planning = GeminiProvider(model=planning_model)
        self._gemini_code = GeminiProvider(model=code_model)
        self._gemini_devops = GeminiProvider(model=devops_model)

        # Optional: local fallback
        local_planner_model = os.getenv("LOCAL_LLM_MODEL_PLANNING", "llama3.1:8b")
        local_code_model = os.getenv("LOCAL_LLM_MODEL_CODE", "qwen2.5-coder:7b")
        local_devops_model = os.getenv("LOCAL_LLM_MODEL_DEVOPS", "llama3.1:8b")

        self._local_planning = LocalLLMProvider(model=local_planner_model, name="local-planning")
        self._local_code = LocalLLMProvider(model=local_code_model, name="local-code")
        self._local_devops = LocalLLMProvider(model=local_devops_model, name="local-devops")

        # Wiring: which providers to try for each role, in order
        self.providers_by_role: dict[LLMRole, list[Any]] = {
            # Prefer cloud for planning/spec, but fall back to local if quota hit / offline
            "planning": [
                self._gemini_planning,
                #self._local_planning,
            ],
            # Code generation: default to local model to avoid quotas
            "code_gen": [
                #self._local_code,
                self._gemini_planning,  # optional fallback if you want
            ],
            # DevOps: local only by default (can be very chatty)
            "devops": [
                #self._local_devops,
                self._gemini_devops,  # optional fallback if needed
            ],
        }

    def call(self, req: LLMRequest) -> str:
        role: LLMRole = req.role
        providers = self.providers_by_role.get(role, [])

        if not providers:
            raise RuntimeError(f"No LLM providers configured for role: {role}")

        last_error: Exception | None = None

        for idx, provider in enumerate(providers):
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            logger.info("LLMRouter: role=%s trying provider[%d]=%s", role, idx, provider_name)

            try:
                return provider.chat(req.messages)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "LLMRouter: provider %s for role=%s failed (%s). Trying next provider if any.",
                    provider_name,
                    role,
                    exc,
                )
                continue

        # All providers failed
        raise RuntimeError(f"All LLM providers failed for role={role}: {last_error}")
