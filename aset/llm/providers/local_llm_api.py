import os
import logging
from typing import List, Dict, Any

import requests

logger = logging.getLogger(__name__)


class LocalLLMProvider:
    """
    Local LLM provider, designed to talk to Ollama by default.

    Default config (overridable via env):
      - LOCAL_LLM_URL (default: http://localhost:11434/api/chat)
      - LOCAL_LLM_MODEL (default: llama3.1:8b)
    """

    def __init__(self, model: str | None = None, url: str | None = None, name: str = "local"):
        self.name = name
        self.url = url or os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
        self.model = model or os.getenv("LOCAL_LLM_MODEL", "llama3.1:8b")

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Call a local LLM (Ollama-style /api/chat endpoint) with an OpenAI-like messages list.
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        logger.info("LocalLLMProvider[%s]: calling %s model=%s", self.name, self.url, self.model)
        try:
            resp = requests.post(self.url, json=payload, timeout=600)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("LocalLLMProvider[%s] request failed: %s", self.name, exc)
            raise

        data = resp.json()

        # Ollama /api/chat format: { "message": {"role": "...", "content": "..."}, "done": true }
        if isinstance(data, dict) and "message" in data:
            msg = data["message"]
            if isinstance(msg, dict) and "content" in msg:
                return msg["content"]

        # Fallback for OpenAI-like style
        if isinstance(data, dict) and "choices" in data:
            choices = data["choices"]
            if choices and "message" in choices[0]:
                return choices[0]["message"]["content"]

        logger.error("LocalLLMProvider[%s]: unexpected response format: %s", self.name, data)
        raise RuntimeError("Unexpected local LLM response format")
