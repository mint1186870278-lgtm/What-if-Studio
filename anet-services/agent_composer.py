from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI
from anthropic import Anthropic


APP_NAME = "agent-composer"
APP_PORT = 7101
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

app = FastAPI(title=APP_NAME)


def call_llm(payload: Dict[str, Any]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    topic = str(payload.get("topic", "")).strip()
    scene = str(payload.get("scene", "")).strip()
    style = str(payload.get("style", "adaptive-hybrid")).strip()
    if not api_key:
        return (
            f"[fallback] soundtrack plan for topic={topic or 'unknown'}, "
            f"scene={scene or 'unknown'}, style={style}"
        )

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=700,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are agent-composer. Propose soundtrack direction with style, "
                    "rhythm curve, instrumentation and 3 practical cue suggestions.\n"
                    f"Topic: {topic}\nScene: {scene}\nPreferred style: {style}"
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
