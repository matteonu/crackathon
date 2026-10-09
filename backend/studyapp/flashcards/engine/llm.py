"""Model client and generation prompts. No PDF or HTTP route concerns live here."""

from __future__ import annotations

import base64
import json
import os
from urllib.request import Request, urlopen

from .models import DocumentContext


class ModelError(RuntimeError):
    pass


class ModelClient:
    def __init__(self, *, model: str | None = None, api_key: str | None = None, endpoint: str | None = None):
        self.model = model or os.environ.get("MODEL", "gpt-5-mini")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        self.endpoint = endpoint or os.environ.get("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses")

    def generate_json(self, document: DocumentContext, *, purpose: str, feedback=None, target_count: int = 5) -> dict:
        if not self.api_key:
            raise ModelError("The model API key is missing.")
        instruction = prompt_for(purpose, target_count)
        if feedback:
            instruction += "\nGeneral and per-card feedback:\n" + json.dumps(feedback, ensure_ascii=False)
        content = [{"type": "input_text", "text": instruction}]
        for page in document.pages:
            if page.text:
                content.append({"type": "input_text", "text": f"[Page {page.number}]\n{page.text}"})
            if page.image is not None:
                content.append({"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(page.image).decode()})
        body = {"model": self.model, "input": [{"role": "user", "content": content}], "text": {"format": {"type": "json_object"}}}
        request = Request(self.endpoint, data=json.dumps(body).encode(), method="POST", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode())
            text = "".join(part.get("text", "") for item in result.get("output", []) if item.get("type") == "message" for part in item.get("content", []) if part.get("type") == "output_text")
            return json.loads(text)
        except Exception as exc:
            raise ModelError("The model request could not be completed.") from exc


def prompt_for(purpose: str, target_count: int) -> str:
    if purpose == "examples":
        return f'Return only JSON {{"cards":[{{"front":string,"back":string,"type":"basic"|"cloze"|"application","source_pages":[number]}}]}}. Create exactly about {target_count} representative example cards.'
    if purpose == "final_cards":
        return f'Return only JSON {{"cards":[{{"front":string,"back":string,"type":"basic"|"cloze"|"application","source_pages":[number]}}]}}. Create up to {target_count} high-quality atomic flashcards.'
    return 'Return structured JSON for the requested exercise output.'
