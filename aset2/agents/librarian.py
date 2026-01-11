from __future__ import annotations

from typing import Any, Set
from core.agent_base import BaseAgent


class LibrarianAgent(BaseAgent):
    """
    Produces requirements.txt for the GENERATED app.

    For Stock Tracker MVP we include:
    - streamlit
    - pandas
    - numpy
    - yfinance (optional at runtime, but included so it works out of the box)
    """

    def execute(self, input_data: Any) -> str:
        self.log("Producing requirements.txt for generated project")

        reqs: Set[str] = {
            "streamlit>=1.30",
            "pandas>=2.0",
            "numpy>=1.24",
            "yfinance>=0.2",
        }
        return "\n".join(sorted(reqs)) + "\n"
