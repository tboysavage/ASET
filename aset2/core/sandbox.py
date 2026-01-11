from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional


@dataclass
class SandboxResult:
    ok: bool
    error: Optional[str] = None


class Sandbox:
    """
    MVP: lightweight syntax check. Later we can run subprocess, venv, E2B, etc.
    """

    def run_check(self, code: str) -> Optional[str]:
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"SyntaxError: {e}"
