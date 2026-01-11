from __future__ import annotations

from typing import Any, List

from core.agent_base import BaseAgent
from core.protocol import Fragment
from core.sandbox import Sandbox
from agents.debugger import DebuggerAgent


class LogicCoderAgent(BaseAgent):
    """
    Deterministic implementations for the canonical Stock Tracker fragments:
      - initialize_state
      - render_sidebar_controls
      - load_prices
      - compute_metrics
      - render_main_dashboard

    Unknown fragments fall back to a stub.
    """

    def __init__(self, llm, verbose: bool = True):
        super().__init__(llm, verbose)
        self.sandbox = Sandbox()
        self.debugger_agent = DebuggerAgent(llm, verbose=verbose)

    def execute(self, input_data: Any) -> str:
        fragment: Fragment = input_data
        self.log(f"Generating code for fragment: {fragment.id}")
        return self.generate_robust_code(fragment)

    def generate_robust_code(self, fragment: Fragment) -> str:
        attempts = 0

        code = self._specialized_code(fragment)
        if code is None:
            code = self._stub_code(fragment)

        while attempts < 3:
            error = self.sandbox.run_check(code)
            if not error:
                return code

            self.log(f"Attempt {attempts + 1} failed: {error}")
            fix_prompt = (
                "Fix the Python code below so it parses and runs.\n\n"
                f"FRAGMENT CONTRACT:\n"
                f"- id: {fragment.id}\n"
                f"- inputs: {fragment.inputs}\n"
                f"- outputs: {fragment.outputs}\n\n"
                f"ERROR:\n{error}\n\n"
                f"CODE:\n{code}\n"
            )
            code = self.debugger_agent.execute(fix_prompt)
            attempts += 1

        raise RuntimeError("Failed to generate working code after 3 attempts.")

    def _specialized_code(self, fragment: Fragment) -> str | None:
        fid = fragment.id

        if fid == "initialize_state":
            return '''import pandas as pd

def initialize_state():
    """
    Initialize session state defaults (tickers, period, price_data, status_message).
    Returns a dict with keys: tickers, period, price_data, status_message.
    """
    tickers = ["AAPL"]
    period = "6mo"
    price_data = pd.DataFrame()
    status_message = "Ready."
    return {"tickers": tickers, "period": period, "price_data": price_data, "status_message": status_message}
'''

        if fid == "render_sidebar_controls":
            return '''import streamlit as st

def render_sidebar_controls(tickers, period):
    """
    Render sidebar UI for managing the ticker list and selecting the data period.
    Returns updated {tickers, period}.
    """
    st.sidebar.header("Controls")

    period_options = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"]
    if period not in period_options:
        period = "6mo"
    period = st.sidebar.selectbox("Period", period_options, index=period_options.index(period))

    st.sidebar.subheader("Tickers")
    tickers = list(tickers or [])

    new_ticker = st.sidebar.text_input("Add ticker", value="", placeholder="e.g., MSFT").strip().upper()
    add_clicked = st.sidebar.button("Add", use_container_width=True)

    if add_clicked and new_ticker:
        if new_ticker not in tickers:
            tickers.append(new_ticker)

    if tickers:
        remove = st.sidebar.multiselect("Remove tickers", options=tickers, default=[])
        if remove:
            remove_set = set(remove)
            tickers = [t for t in tickers if t not in remove_set]

    st.sidebar.caption("Tip: Try AAPL, MSFT, GOOG.")
    return {"tickers": tickers, "period": period}
'''

        if fid == "load_prices":
            return '''import pandas as pd
import numpy as np

def load_prices(tickers, period):
    """
    Fetch historical stock prices using yfinance for the tickers and period.
    Returns {price_data, status_message}.
    price_data is a DataFrame with a DateTime index and one column per ticker.
    """
    status_message = ""
    tickers = [t.strip().upper() for t in (tickers or []) if t and t.strip()]

    if not tickers:
        return {"price_data": pd.DataFrame(), "status_message": "No tickers provided."}

    try:
        import yfinance as yf

        data = yf.download(
            tickers=tickers,
            period=period,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        price_df = pd.DataFrame()

        # Multi-ticker: MultiIndex columns like (TICKER, Field)
        if isinstance(data.columns, pd.MultiIndex):
            closes = {}
            for t in tickers:
                if (t, "Close") in data.columns:
                    closes[t] = data[(t, "Close")]
                elif (t, "Adj Close") in data.columns:
                    closes[t] = data[(t, "Adj Close")]
            if closes:
                price_df = pd.DataFrame(closes)

        # Single-ticker: flat columns like ["Open","High","Low","Close"...]
        else:
            if "Close" in data.columns:
                price_df = pd.DataFrame({tickers[0]: data["Close"]})
            elif "Adj Close" in data.columns:
                price_df = pd.DataFrame({tickers[0]: data["Adj Close"]})

        price_df = price_df.dropna(how="all")

        if price_df.empty:
            status_message = "No price data returned (check tickers or period). Using mock data."
            raise ValueError(status_message)

        status_message = f"Loaded prices for {len(price_df.columns)} ticker(s)."
        return {"price_data": price_df, "status_message": status_message}

    except Exception as e:
        # Mock fallback: random walk per ticker
        n = 180
        idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
        rng = np.random.default_rng(42)

        mock = {}
        for t in tickers:
            start = float(rng.uniform(50, 500))
            steps = rng.normal(loc=0.0, scale=1.0, size=n).cumsum()
            series = start + steps
            series = np.maximum(series, 1.0)
            mock[t] = series

        price_df = pd.DataFrame(mock, index=idx)
        status_message = f"Using mock data (yfinance unavailable or failed): {e}"
        return {"price_data": price_df, "status_message": status_message}
'''

        if fid == "compute_metrics":
            return '''def compute_metrics(price_series):
    """
    Calculate key metrics like latest price and percentage change from a price series.
    Returns {metrics_dict}.
    """
    metrics_dict = {"latest": None, "change": None, "pct_change": None}

    if price_series is None:
        return {"metrics_dict": metrics_dict}

    try:
        s = price_series.dropna()
        if len(s) < 2:
            if len(s) == 1:
                metrics_dict["latest"] = float(s.iloc[-1])
            return {"metrics_dict": metrics_dict}

        latest = float(s.iloc[-1])
        prev = float(s.iloc[-2])
        change = latest - prev
        pct = (change / prev) * 100.0 if prev != 0 else None

        metrics_dict["latest"] = latest
        metrics_dict["change"] = change
        metrics_dict["pct_change"] = pct
        return {"metrics_dict": metrics_dict}
    except Exception:
        return {"metrics_dict": metrics_dict}
'''

        if fid == "render_main_dashboard":
            return '''import streamlit as st

def render_main_dashboard(tickers, price_data, status_message=""):
    """
    Render main dashboard with selector, metrics, chart, and status message.
    Calls compute_metrics (defined in same module).
    """
    st.subheader("Dashboard")

    if status_message:
        st.info(status_message)

    if not tickers:
        st.warning("Add one or more tickers in the sidebar to get started.")
        return {}

    if price_data is None or getattr(price_data, "empty", True):
        st.warning("No price data loaded yet.")
        return {}

    available = [t for t in tickers if t in price_data.columns] or list(price_data.columns)
    if not available:
        st.warning("No matching tickers in the price data.")
        return {}

    selected = st.selectbox("Select stock", options=available, index=0)

    series = price_data[selected].dropna()
    metrics_out = compute_metrics(series)
    m = metrics_out.get("metrics_dict") or {}

    c1, c2, c3 = st.columns(3)
    c1.metric("Latest", f"{m.get('latest'):.2f}" if isinstance(m.get("latest"), (int, float)) else "—")
    c2.metric("Change", f"{m.get('change'):+.2f}" if isinstance(m.get("change"), (int, float)) else "—")
    pct = m.get("pct_change")
    c3.metric("% Change", f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "—")

    st.line_chart(series, use_container_width=True)
    st.caption("Data uses yfinance if available; otherwise mock prices are shown.")
    return {}
'''

        return None

    def _stub_code(self, fragment: Fragment) -> str:
        fn = fragment.id
        args = ", ".join(fragment.inputs) if fragment.inputs else ""

        outputs_list = fragment.outputs or []
        out_dict_items = ", ".join([f"'{o}': {o}" for o in outputs_list])

        assigns: List[str] = []
        for o in outputs_list:
            assigns.append(f"    {o} = None")

        assigns_block = "\n".join(assigns) if assigns else "    pass"

        return (
            f"def {fn}({args}):\n"
            f"    \"\"\"{fragment.description}\"\"\"\n"
            f"{assigns_block}\n"
            f"    return {{{out_dict_items}}}\n"
        )
