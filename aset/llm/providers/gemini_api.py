import os
from typing import Dict, List

from google import genai


class GeminiProvider:
    """
    Gemini Developer API via Google Gen AI SDK (google-genai).
    Uses GEMINI_API_KEY.
    """

    def __init__(self, model: str = "gemini-2.5-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")

        # This client uses the Gemini Developer API when given an API key.
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def chat(self, messages: List[Dict[str, str]]) -> str:
        # Flatten role-based messages into a single prompt.
        parts = []
        for m in messages:
            role = m.get("role", "user").upper()
            content = m.get("content", "")
            parts.append(f"{role}:\n{content}")
        prompt = "\n\n".join(parts)

        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return resp.text or ""
