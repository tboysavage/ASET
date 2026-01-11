from __future__ import annotations

import json
import re
from typing import Any, Optional

from core.agent_base import BaseAgent
from core.protocol import ProjectBlueprint, Fragment, StateVariable


class ArchitectAgent(BaseAgent):
    """
    Generates a ProjectBlueprint.

    CRITICAL BEHAVIOR:
    - Vertex output can vary (e.g. render_ui vs render_main_dashboard).
    - We normalize to a CANONICAL fragment API so downstream codegen is stable.
      This makes "missing import name" issues effectively impossible.
    """

    CANONICAL_FRAGMENTS = [
        "initialize_state",
        "render_sidebar_controls",
        "load_prices",
        "compute_metrics",
        "render_main_dashboard",
    ]

    def execute(self, input_data: Any) -> ProjectBlueprint:
        user_prompt = str(input_data).strip()

        self.log("Attempting Vertex blueprint generation (route=architect).")
        bp = self._try_vertex_blueprint(user_prompt)
        if bp is None:
            app_name = self._title_case_app_name(user_prompt)
            self.log(f"Falling back to deterministic blueprint for: {app_name}")
            bp = self._fallback_blueprint(user_prompt, app_name)

        # Normalize IDs + ensure canonical fragments exist
        bp = self._normalize_blueprint(bp)

        self.log(f"Final blueprint (normalized) app_name={bp.app_name} fragments={[f.id for f in bp.logic_fragments]}")
        return bp

    def _try_vertex_blueprint(self, user_prompt: str) -> Optional[ProjectBlueprint]:
        system = (
            "You are a senior product + software architect.\n"
            "You output ONLY valid JSON with no markdown fences.\n"
            "Your JSON MUST match the provided schema.\n"
            "Be concise. Prefer small, testable fragments.\n"
        )

        schema_hint = {
            "app_name": "string",
            "global_state": [
                {"name": "string", "type": "string", "description": "string"}
            ],
            "logic_fragments": [
                {
                    "id": "string",
                    "description": "string",
                    "inputs": ["string"],
                    "outputs": ["string"],
                }
            ],
            "ui_layout": "string",
        }

        prompt = (
            "Create a ProjectBlueprint for a small Streamlit stock tracker app.\n"
            "The app should have sidebar controls for tickers + period, and a main dashboard with chart + metrics.\n\n"
            f"USER REQUEST:\n{user_prompt}\n\n"
            f"SCHEMA (shape only):\n{json.dumps(schema_hint, indent=2)}\n\n"
            "Rules:\n"
            "- Return JSON only.\n"
            "- Prefer 4-8 fragments.\n"
            "- Use these exact fragment IDs if possible:\n"
            "  initialize_state, render_sidebar_controls, load_prices, compute_metrics, render_main_dashboard\n"
            "- If you propose different names, keep them semantically equivalent.\n"
        )

        try:
            raw = self.llm.generate_text(prompt=prompt, system=system, route="architect")
        except Exception as e:
            self.log(f"Vertex call failed: {e}")
            return None

        raw_json = self._extract_json_object(raw)
        if raw_json is None:
            self.log("Vertex response did not contain a JSON object.")
            return None

        try:
            bp = ProjectBlueprint.model_validate_json(raw_json)
            if not bp.app_name or not bp.logic_fragments:
                self.log("Vertex blueprint missing app_name or logic_fragments.")
                return None
            return bp
        except Exception as e:
            self.log(f"Vertex blueprint validation failed: {e}")
            return None

    def _fallback_blueprint(self, user_prompt: str, app_name: str) -> ProjectBlueprint:
        return ProjectBlueprint(
            app_name=app_name,
            global_state=[
                StateVariable(
                    name="tickers",
                    type="list[str]",
                    description="List of stock symbols to track, e.g., ['AAPL', 'GOOG'].",
                ),
                StateVariable(
                    name="period",
                    type="str",
                    description="Time period for historical data, e.g., '1y', '6mo'.",
                ),
                StateVariable(
                    name="price_data",
                    type="pd.DataFrame",
                    description="DataFrame holding historical price data for all tracked tickers.",
                ),
                StateVariable(
                    name="status_message",
                    type="str",
                    description="User-facing status messages.",
                ),
            ],
            logic_fragments=[
                Fragment(
                    id="initialize_state",
                    description="Initialize session state defaults (tickers, period, price_data, status_message).",
                    inputs=[],
                    outputs=["tickers", "period", "price_data", "status_message"],
                ),
                Fragment(
                    id="render_sidebar_controls",
                    description="Render sidebar UI for managing tickers and selecting period.",
                    inputs=["tickers", "period"],
                    outputs=["tickers", "period"],
                ),
                Fragment(
                    id="load_prices",
                    description="Fetch historical prices for tickers and period. Use yfinance or mock fallback.",
                    inputs=["tickers", "period"],
                    outputs=["price_data", "status_message"],
                ),
                Fragment(
                    id="compute_metrics",
                    description="Compute latest price and percent change from a series.",
                    inputs=["price_series"],
                    outputs=["metrics_dict"],
                ),
                Fragment(
                    id="render_main_dashboard",
                    description="Render chart + metrics for selected ticker.",
                    inputs=["tickers", "price_data", "status_message"],
                    outputs=[],
                ),
            ],
            ui_layout="Sidebar: tickers + period. Main: ticker selector, metrics, chart.",
        )

    def _normalize_blueprint(self, bp: ProjectBlueprint) -> ProjectBlueprint:
        """
        Normalize common variant IDs into canonical ones so downstream is stable.

        Canonical:
          render_sidebar_controls
          render_main_dashboard

        Variants we map:
          render_sidebar_input -> render_sidebar_controls
          render_ui -> render_main_dashboard
        """
        id_map = {
            "render_sidebar_input": "render_sidebar_controls",
            "render_sidebar": "render_sidebar_controls",
            "sidebar_controls": "render_sidebar_controls",
            "render_ui": "render_main_dashboard",
            "render_dashboard": "render_main_dashboard",
            "main_dashboard": "render_main_dashboard",
        }

        # Rewrite fragment IDs
        new_frags: list[Fragment] = []
        seen = set()

        for f in bp.logic_fragments:
            new_id = id_map.get(f.id, f.id)
            f2 = f.model_copy(update={"id": new_id})

            # If multiple map to same canonical id, keep the first occurrence.
            if f2.id in seen:
                continue

            new_frags.append(f2)
            seen.add(f2.id)

        bp = bp.model_copy(update={"logic_fragments": new_frags})

        # Ensure global_state has the basics we use in the app
        gs_names = {s.name for s in bp.global_state}
        gs_out = list(bp.global_state)

        def add_state(name: str, typ: str, desc: str) -> None:
            nonlocal gs_out
            if name not in gs_names:
                gs_out.append(StateVariable(name=name, type=typ, description=desc))
                gs_names.add(name)

        add_state("tickers", "list[str]", "List of tickers to track.")
        add_state("period", "str", "Period string for history.")
        add_state("price_data", "pd.DataFrame", "Price history data.")
        add_state("status_message", "str", "User-facing status messages.")

        bp = bp.model_copy(update={"global_state": gs_out})

        # Ensure canonical fragments exist; add minimal ones if missing
        frag_ids = {f.id for f in bp.logic_fragments}

        def ensure_fragment(fid: str, desc: str, inputs: list[str], outputs: list[str]) -> None:
            nonlocal bp
            if fid in frag_ids:
                return
            bp.logic_fragments.append(
                Fragment(id=fid, description=desc, inputs=inputs, outputs=outputs)
            )
            frag_ids.add(fid)

        ensure_fragment(
            "initialize_state",
            "Initialize defaults for tickers/period/price_data/status_message.",
            [],
            ["tickers", "period", "price_data", "status_message"],
        )
        ensure_fragment(
            "render_sidebar_controls",
            "Render sidebar inputs for tickers + period.",
            ["tickers", "period"],
            ["tickers", "period"],
        )
        ensure_fragment(
            "load_prices",
            "Load prices for tickers + period using yfinance or mock fallback.",
            ["tickers", "period"],
            ["price_data", "status_message"],
        )
        ensure_fragment(
            "compute_metrics",
            "Compute latest, change, pct change from a series.",
            ["price_series"],
            ["metrics_dict"],
        )
        ensure_fragment(
            "render_main_dashboard",
            "Render main dashboard: selector, metrics, chart, status.",
            ["tickers", "price_data", "status_message"],
            [],
        )

        return bp

    def _title_case_app_name(self, prompt: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9 ]+", "", prompt).strip()
        if not cleaned:
            return "ASET App"
        return " ".join(w.capitalize() for w in cleaned.split()[:6])

    def _extract_json_object(self, text: str) -> Optional[str]:
        if not text:
            return None

        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1].strip()
                    try:
                        json.loads(candidate)
                        return candidate
                    except Exception:
                        return None
        return None
