from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from aset.llm.router.llm_router import LLMRouter, LLMRequest
from aset.utils.logger import get_logger


class BaseAgent(ABC):
    """
    Base class for all agents.
    Provides access to the LLM router and a logger.
    """

    def __init__(self, llm_router: LLMRouter) -> None:
        self.llm = llm_router
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        ...

    def _call_llm(
        self,
        system_prompt: Union[str, LLMRequest],
        user_prompt: Optional[str] = None,
        role: str = "default",
    ) -> str:
        """
        Flexible LLM caller.

        Supports:
        - New style (used by ProductManagerAgent, Architect, etc.):
            _call_llm(system_prompt="...", user_prompt="...", role="planning")
        - Old style (used by BackendEngineerAgent, etc.):
            _call_llm(req: LLMRequest)
        """
        # Old style: _call_llm(req)
        if isinstance(system_prompt, LLMRequest):
            req = system_prompt
        else:
            # New style: _call_llm(system_prompt, user_prompt, role)
            if user_prompt is None:
                raise ValueError(
                    "user_prompt must be provided when calling _call_llm "
                    "with (system_prompt: str, user_prompt: str, role: str)."
                )

            messages: List[Dict[str, str]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            req = LLMRequest(messages=messages, role=role)  # type: ignore[arg-type]

        self.logger.info("Calling LLM with role=%s", req.role)
        return self.llm.call(req)
