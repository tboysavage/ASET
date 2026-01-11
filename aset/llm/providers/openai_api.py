from __future__ import annotations

import os
from typing import List, Dict, Any, Optional

import openai  # you'll need `openai` in requirements


class OpenAIProvider:
    """
    Tiny wrapper around OpenAI's ChatCompletion/Responses API.
    Replace with the exact client you’re using.
    """

    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4.1-mini"):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")

        openai.api_key = api_key
        self.default_model = default_model

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs: Any) -> str:
        model = model or self.default_model

        # NOTE: adjust to the exact SDK version you're using
        completion = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        return completion.choices[0].message["content"]
