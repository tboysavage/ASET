from __future__ import annotations

from typing import Any
from core.agent_base import BaseAgent


class DebuggerAgent(BaseAgent):
    """
    MVP: debugging via routed model calls.
    - debug_fast -> Ollama (local)
    - integrate/tests -> Vertex (future escalation)
    """

    def execute(self, input_data: Any) -> str:
        prompt = str(input_data)

        self.log("Requesting fix from local model (route=debug_fast).")
        fix = self.llm.generate_code(
            prompt=prompt,
            route="debug_fast",
            system="You fix Python code. Output only the corrected full code, no commentary.",
        )
        return fix
