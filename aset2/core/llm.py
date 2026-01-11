from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional

import requests


class LLMProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_code(self, prompt: str, *, system: Optional[str] = None) -> str:
        raise NotImplementedError


# -------------------------
# Ollama (local)
# -------------------------
@dataclass
class OllamaConfig:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1"
    temperature: float = 0.2
    timeout_seconds: int = 300


class OllamaLLM(LLMProvider):
    """
    Uses Ollama's /api/chat endpoint (local HTTP server).
    """

    def __init__(self, cfg: OllamaConfig):
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")

    def _chat(self, prompt: str, system: Optional[str]) -> str:
        url = f"{self.base_url}/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
        }

        r = requests.post(url, json=payload, timeout=self.cfg.timeout_seconds)
        r.raise_for_status()
        data = r.json()

        # Ollama chat response format: {"message": {"content": "..."}}
        return (data.get("message") or {}).get("content", "")

    def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        return self._chat(prompt, system)

    def generate_code(self, prompt: str, *, system: Optional[str] = None) -> str:
        code_system = system or "You are a senior software engineer. Output only code."
        return self._chat(prompt, code_system)


# -------------------------
# Vertex AI (Gemini)
# -------------------------
@dataclass
class VertexConfig:
    project: str
    location: str = "us-central1"
    model: str = "gemini-2.5-pro"
    temperature: float = 0.2


class VertexLLM(LLMProvider):
    """
    Uses the unified Google Gen AI Python SDK with vertexai=True.
    """

    def __init__(self, cfg: VertexConfig):
        self.cfg = cfg
        from google import genai  # lazy import so local-only usage still works
        self.client = genai.Client(vertexai=True, project=cfg.project, location=cfg.location)

    def _generate(self, prompt: str, system: Optional[str]) -> str:
        full_prompt = prompt if not system else f"{system}\n\n{prompt}"

        resp = self.client.models.generate_content(
            model=self.cfg.model,
            contents=full_prompt,
            config={"temperature": self.cfg.temperature},
        )
        return getattr(resp, "text", "") or ""

    def generate_text(self, prompt: str, *, system: Optional[str] = None) -> str:
        return self._generate(prompt, system)

    def generate_code(self, prompt: str, *, system: Optional[str] = None) -> str:
        code_system = system or "You are a senior software engineer. Output only code."
        return self._generate(prompt, code_system)


# -------------------------
# Router
# -------------------------
class RoutedLLM(LLMProvider):
    """
    Route calls by 'route' name to either vertex or ollama.

    Agents can call:
      self.llm.generate_text(..., route="architect")
      self.llm.generate_code(..., route="fragment")
    """

    def __init__(self, providers: Dict[str, LLMProvider], routes: Dict[str, str], default: str):
        if default not in providers:
            raise ValueError(f"Default provider '{default}' not found in providers={list(providers.keys())}")
        self.providers = providers
        self.routes = routes
        self.default = default

    def _pick(self, route: Optional[str]) -> LLMProvider:
        if route and route in self.routes:
            provider_name = self.routes[route]
            provider = self.providers.get(provider_name)
            if provider is None:
                raise ValueError(
                    f"Route '{route}' maps to unknown provider '{provider_name}'. "
                    f"Known providers: {list(self.providers.keys())}"
                )
            return provider
        return self.providers[self.default]

    def generate_text(self, prompt: str, *, system: Optional[str] = None, route: Optional[str] = None) -> str:  # type: ignore[override]
        return self._pick(route).generate_text(prompt, system=system)

    def generate_code(self, prompt: str, *, system: Optional[str] = None, route: Optional[str] = None) -> str:  # type: ignore[override]
        return self._pick(route).generate_code(prompt, system=system)
