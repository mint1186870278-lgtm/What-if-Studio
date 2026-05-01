from __future__ import annotations

import os
from typing import Any, Dict

from anthropic import Anthropic
from fastapi import FastAPI


APP_NAME = "agent-director"
APP_PORT = 7103
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

app = FastAPI(title=APP_NAME)


def call_llm(payload: Dict[str, Any]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    topic = str(payload.get("topic", "")).strip()
    ending = str(payload.get("ending", "")).strip()
    tone = str(payload.get("tone", "balanced")).strip()
    if not api_key:
        return (
            f"[fallback] directing note for topic={topic or 'unknown'}, "
            f"ending={ending or 'unknown'}, tone={tone}"
        )

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are agent-director. Return a concise production brief with "
                    "story goal, conflict curve, and 3 execution directives.\n"
                    f"Topic: {topic}\nDesired ending: {ending}\nTone: {tone}"
                ),
            }
        ],
    )
    blocks = getattr(message, "content", None) or []
    for item in blocks:
        text = getattr(item, "text", "")
        if text:
            return text
    return "[empty-llm-response]"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "agent": APP_NAME}


@app.post("/generate")
def generate(req: Dict[str, Any]) -> Dict[str, Any]:
    return {"agent": APP_NAME, "result": call_llm(req)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=APP_PORT)
