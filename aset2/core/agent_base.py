from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from core.llm import LLMProvider


class BaseAgent(ABC):
    def __init__(self, llm: LLMProvider, verbose: bool = True):
        self.llm = llm
        self.verbose = verbose

    def log(self, message: str) -> None:
        if self.verbose:
            print(f"[{self.__class__.__name__}] {message}")

    @abstractmethod
    def execute(self, input_data: Any) -> Any:
        """Every agent must implement this method."""
        raise NotImplementedError
