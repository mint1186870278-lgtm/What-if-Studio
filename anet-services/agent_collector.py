from __future__ import annotations

import os
from typing import Any, Dict

from anthropic import Anthropic
from fastapi import FastAPI


APP_NAME = "agent-collector"
APP_PORT = 7104
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

app = FastAPI(title=APP_NAME)


def call_llm(payload: Dict[str, Any]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    topic = str(payload.get("topic", "")).strip()
    ending = str(payload.get("ending", "")).strip()
    if not api_key:
        return (
            f"[fallback] reference collection for topic={topic or 'unknown'}, "
            f"ending={ending or 'unknown'}"
        )

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=700,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are agent-collector. Provide practical source collection "
                    "suggestions for film production, including references, footage "
                    "keywords and risk notes.\n"
                    f"Topic: {topic}\nTarget ending: {ending}"
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
