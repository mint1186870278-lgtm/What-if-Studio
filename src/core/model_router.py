"""Configurable model router for text LLM and video generation.

Abstracts provider differences behind a unified interface so users can
plug in their own API keys for any supported provider.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ModelProvider(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    SILICONFLOW = "siliconflow"


class VideoProvider(str, Enum):
    HAPPYHORSE = "happyhorse"
    KLING = "kling"
    WAN = "wan"
    SEEDANCE = "seedance"
    FFMPEG = "ffmpeg"


# ---------------------------------------------------------------------------
# Provider metadata — base URLs, env-var keys, default models
# ---------------------------------------------------------------------------

_PROVIDER_META: dict[ModelProvider, dict[str, str]] = {
    ModelProvider.OPENAI: {
        "key_env": "OPENAI_API_KEY",
        "base_env": "OPENAI_BASE_URL",
        "model_env": "OPENAI_MODEL",
        "default_base": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    ModelProvider.CLAUDE: {
        "key_env": "ANTHROPIC_API_KEY",
        "base_env": "ANTHROPIC_BASE_URL",
        "model_env": "ANTHROPIC_MODEL",
        "default_base": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-20250514",
    },
    ModelProvider.ZHIPU: {
        "key_env": "ZHIPU_API_KEY",
        "base_env": "ZHIPU_BASE_URL",
        "model_env": "ZHIPU_MODEL",
        "default_base": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
    },
    ModelProvider.DEEPSEEK: {
        "key_env": "DEEPSEEK_API_KEY",
        "base_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "default_base": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    ModelProvider.SILICONFLOW: {
        "key_env": "SILICONFLOW_API_KEY",
        "base_env": "SILICONFLOW_BASE_URL",
        "model_env": "SILICONFLOW_MODEL",
        "default_base": "https://api.siliconflow.cn/v1",
        "default_model": "Qwen/Qwen2.5-7B-Instruct",
    },
}


def _resolve_api_key(provider: ModelProvider) -> str | None:
    meta = _PROVIDER_META[provider]
    attr = meta["key_env"].lower()
    val = getattr(settings, attr, None) or os.getenv(meta["key_env"])
    return val.strip() if val else None


def _resolve_base_url(provider: ModelProvider) -> str:
    meta = _PROVIDER_META[provider]
    attr = (meta["base_env"].lower().removesuffix("_base_url") + "_base_url")
    val = getattr(settings, attr, None) or os.getenv(meta["base_env"])
    return (val or meta["default_base"]).strip().rstrip("/")


def _resolve_model(provider: ModelProvider) -> str:
    meta = _PROVIDER_META[provider]
    env_val = os.getenv(meta.get("model_env", ""))
    if env_val:
        return env_val.strip()
    return meta["default_model"]


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ProviderNotAvailableError(RuntimeError):
    """Raised when a model provider has no configured API key."""


class VideoGenerationError(RuntimeError):
    """Raised when video generation fails."""


# ---------------------------------------------------------------------------
# Text model router
# ---------------------------------------------------------------------------

class TextModelRouter:
    """Singleton router for text LLM calls across providers."""

    _instance: TextModelRouter | None = None
    _clients: dict[ModelProvider, Any] = {}

    def __new__(cls) -> TextModelRouter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_openai_client(self, provider: ModelProvider) -> Any:
        if provider not in self._clients:
            from openai import AsyncOpenAI
            key = _resolve_api_key(provider)
            if not key:
                raise ProviderNotAvailableError(f"No API key configured for {provider.value}")
            base = _resolve_base_url(provider)
            self._clients[provider] = AsyncOpenAI(api_key=key, base_url=base)
        return self._clients[provider]

    def get_available_providers(self) -> list[ModelProvider]:
        return [p for p in ModelProvider if _resolve_api_key(p)]

    async def generate(
        self,
        provider: ModelProvider,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Non-streaming text generation."""
        model = _resolve_model(provider)

        if provider == ModelProvider.CLAUDE:
            return await self._generate_claude(messages, model, temperature, max_tokens)

        client = self._get_openai_client(provider)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def generate_stream(
        self,
        provider: ModelProvider,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Streaming text generation."""
        model = _resolve_model(provider)

        if provider == ModelProvider.CLAUDE:
            async for chunk in self._generate_claude_stream(messages, model, temperature, max_tokens):
                yield chunk
            return

        client = self._get_openai_client(provider)
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    # -- Claude via native Anthropic API --------------------------------------

    async def _generate_claude(
        self, messages: list[dict], model: str, temperature: float, max_tokens: int,
    ) -> str:
        key = _resolve_api_key(ModelProvider.CLAUDE)
        if not key:
            raise ProviderNotAvailableError("No API key configured for Claude")
        base = _resolve_base_url(ModelProvider.CLAUDE)
        system, chat_msgs = _split_system_messages(messages)

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": _to_claude_messages(chat_msgs),
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block.get("text", "")
            return ""

    async def _generate_claude_stream(
        self, messages: list[dict], model: str, temperature: float, max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        key = _resolve_api_key(ModelProvider.CLAUDE)
        if not key:
            raise ProviderNotAvailableError("No API key configured for Claude")
        base = _resolve_base_url(ModelProvider.CLAUDE)
        system, chat_msgs = _split_system_messages(messages)

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": _to_claude_messages(chat_msgs),
            "stream": True,
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{base}/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=300,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield delta.get("text", "")
                        elif event.get("type") == "error":
                            raise VideoGenerationError(event.get("error", {}).get("message", "Claude stream error"))


def _split_system_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts = []
    chat = []
    for m in messages:
        if m.get("role") == "system":
            system_parts.append(str(m.get("content", "")))
        else:
            chat.append(m)
    return "\n".join(system_parts), chat


def _to_claude_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m.get("role", "user")
        if role == "assistant":
            role = "assistant"
        else:
            role = "user"
        out.append({"role": role, "content": str(m.get("content", ""))})
    return out


# ---------------------------------------------------------------------------
# Video model router
# ---------------------------------------------------------------------------

class VideoModelRouter:
    """Singleton router for video generation across providers."""

    _instance: VideoModelRouter | None = None

    def __new__(cls) -> VideoModelRouter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_available_providers(self) -> list[VideoProvider]:
        available: list[VideoProvider] = [VideoProvider.FFMPEG]
        if settings.happyhorse_api_key:
            available.append(VideoProvider.HAPPYHORSE)
        if settings.kling_api_key:
            available.append(VideoProvider.KLING)
        if settings.wan_api_key:
            available.append(VideoProvider.WAN)
        if settings.seedance_api_key:
            available.append(VideoProvider.SEEDANCE)
        return available

    async def generate_storyboard(
        self,
        script: str,
        provider: ModelProvider = ModelProvider.OPENAI,
        **kwargs,
    ) -> dict:
        """Generate a storyboard/preview from a script using a text LLM.

        Returns {"frames": [{"description": str, "timing": str}], "total_duration": str}
        """
        text_router = TextModelRouter()
        prompt = (
            "你是一位资深分镜师。请将以下剧本拆分为分镜脚本，为每一幕写出画面描述和预计时长。\n\n"
            f"剧本：\n{script}\n\n"
            "请输出JSON格式，keys: frames (数组, 每项含description和timing), total_duration。只输出JSON，不要其他文字。"
        )
        try:
            raw = await text_router.generate(
                provider=provider,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
        except ProviderNotAvailableError:
            raw = await text_router.generate(
                provider=ModelProvider.OPENAI,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
        try:
            return json.loads(_extract_json(raw))
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse storyboard JSON, using heuristic fallback")
            return _heuristic_storyboard(script)

    async def generate_video(
        self,
        prompt: str,
        provider: VideoProvider,
        source_video_url: str | None = None,
        reference_images: list[str] | None = None,
        output_path: str | None = None,
    ) -> str:
        """Generate a video. Returns the output file path."""
        if provider == VideoProvider.HAPPYHORSE:
            return await self._generate_happyhorse(prompt, source_video_url, reference_images, output_path)
        elif provider == VideoProvider.KLING:
            return await self._generate_kling(prompt, output_path)
        elif provider == VideoProvider.WAN:
            return await self._generate_wan(prompt, output_path)
        elif provider == VideoProvider.SEEDANCE:
            return await self._generate_seedance(prompt, source_video_url, reference_images, output_path)
        elif provider == VideoProvider.FFMPEG:
            return await self._generate_ffmpeg(prompt, output_path)
        raise VideoGenerationError(f"Unknown video provider: {provider}")

    # -- HappyHorse (delegate to existing pipeline) ---------------------------

    async def _generate_happyhorse(
        self,
        prompt: str,
        source_video_url: str | None,
        reference_images: list[str] | None,
        output_path: str | None,
    ) -> str:
        from src.core.video_pipeline import _submit_happyhorse, _poll_happyhorse

        if not source_video_url:
            raise VideoGenerationError("HappyHorse requires a source video URL")

        task_id = await _submit_happyhorse(prompt, source_video_url, reference_images)
        logger.info("HappyHorse task submitted: %s", task_id[:12])
        result_url = await _poll_happyhorse(task_id)

        out = Path(output_path or settings.storage_temp_path / f"hh_{task_id[:12]}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            resp = await client.get(result_url, timeout=300, follow_redirects=True)
            resp.raise_for_status()
            out.write_bytes(resp.content)
        logger.info("HappyHorse video saved: %s", out)
        return str(out)

    # -- Kling ---------------------------------------------------------------

    async def _generate_kling(self, prompt: str, output_path: str | None) -> str:
        key = settings.kling_api_key
        base = settings.kling_base_url or "https://api.kling.kuaishou.com"
        if not key:
            raise ProviderNotAvailableError("No KLING_API_KEY configured")

        out = Path(output_path or settings.storage_temp_path / f"kling_{hash(prompt) & 0xFFFFFFF:07x}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            # Submit
            submit_resp = await client.post(
                f"{base.rstrip('/')}/v1/videos/text2video",
                headers=headers,
                json={
                    "model_name": "kling-v1",
                    "prompt": prompt,
                    "duration": "5",
                    "mode": "std",
                },
                timeout=60,
            )
            submit_resp.raise_for_status()
            task_id = submit_resp.json()["data"]["task_id"]
            logger.info("Kling task submitted: %s", task_id[:12])

            # Poll
            for i in range(60):
                await asyncio.sleep(10)
                poll_resp = await client.get(
                    f"{base.rstrip('/')}/v1/videos/text2video/{task_id}",
                    headers=headers,
                    timeout=30,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                status = data["data"]["task_status"]
                if status == "succeed":
                    video_url = data["data"]["task_result"]["videos"][0]["url"]
                    dl = await client.get(video_url, timeout=300)
                    dl.raise_for_status()
                    out.write_bytes(dl.content)
                    logger.info("Kling video saved: %s", out)
                    return str(out)
                elif status == "failed":
                    raise VideoGenerationError(f"Kling task failed: {data}")
            raise TimeoutError("Kling task timed out")

    # -- Wan -----------------------------------------------------------------

    async def _generate_wan(self, prompt: str, output_path: str | None) -> str:
        key = settings.wan_api_key
        base = settings.wan_base_url
        if not key:
            raise ProviderNotAvailableError("No WAN_API_KEY configured")

        out = Path(output_path or settings.storage_temp_path / f"wan_{hash(prompt) & 0xFFFFFFF:07x}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            submit_resp = await client.post(
                f"{base.rstrip('/')}/api/v1/video/generate",
                headers=headers,
                json={"prompt": prompt, "duration": 5},
                timeout=60,
            )
            submit_resp.raise_for_status()
            task_id = submit_resp.json().get("task_id") or submit_resp.json().get("id")
            logger.info("Wan task submitted: %s", str(task_id)[:12])

            for i in range(60):
                await asyncio.sleep(10)
                poll_resp = await client.get(
                    f"{base.rstrip('/')}/api/v1/tasks/{task_id}",
                    headers=headers,
                    timeout=30,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                status = data.get("status") or data.get("state", "")
                if status in ("completed", "succeeded", "done"):
                    video_url = data.get("video_url") or data.get("output_url", "")
                    if video_url:
                        dl = await client.get(video_url, timeout=300)
                        dl.raise_for_status()
                        out.write_bytes(dl.content)
                        logger.info("Wan video saved: %s", out)
                        return str(out)
                    raise VideoGenerationError("Wan task completed but no video URL found")
                elif status in ("failed", "error"):
                    raise VideoGenerationError(f"Wan task failed: {data}")
            raise TimeoutError("Wan task timed out")

    # -- Seedance (legacy / self-hosted) -----------------------------------

    async def _generate_seedance(
        self,
        prompt: str,
        source_video_url: str | None,
        reference_images: list[str] | None,
        output_path: str | None,
    ) -> str:
        key = settings.seedance_api_key
        base = settings.seedance_api_url or "http://localhost:8000"
        if not key:
            raise ProviderNotAvailableError("No SEEDANCE_API_KEY configured")

        out = Path(output_path or settings.storage_temp_path / f"seedance_{hash(prompt) & 0xFFFFFFF:07x}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {"prompt": prompt}
        if source_video_url:
            body["video_url"] = source_video_url
        if reference_images:
            body["reference_images"] = reference_images

        async with httpx.AsyncClient() as client:
            # Submit
            submit_resp = await client.post(
                f"{base.rstrip('/')}/api/v1/video/generate",
                headers=headers,
                json=body,
                timeout=60,
            )
            submit_resp.raise_for_status()
            data = submit_resp.json()
            task_id = data.get("task_id") or data.get("id") or data.get("job_id")
            if not task_id:
                raise VideoGenerationError(f"Seedance submit returned no task_id: {data}")
            logger.info("Seedance task submitted: %s", str(task_id)[:12])

            # Poll
            for _ in range(60):
                await asyncio.sleep(10)
                poll_resp = await client.get(
                    f"{base.rstrip('/')}/api/v1/tasks/{task_id}",
                    headers=headers,
                    timeout=30,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                status = data.get("status") or data.get("state", "")
                if status in ("completed", "succeeded", "done"):
                    video_url = data.get("video_url") or data.get("output_url", "")
                    if video_url:
                        dl = await client.get(video_url, timeout=300)
                        dl.raise_for_status()
                        out.write_bytes(dl.content)
                        logger.info("Seedance video saved: %s", out)
                        return str(out)
                    raise VideoGenerationError("Seedance completed but no video URL found")
                elif status in ("failed", "error"):
                    raise VideoGenerationError(f"Seedance task failed: {data}")
            raise TimeoutError("Seedance task timed out")

    # -- ffmpeg fallback -----------------------------------------------------

    async def _generate_ffmpeg(self, prompt: str, output_path: str | None) -> str:
        from src.core.video_pipeline import _generate_ffmpeg_video
        out = output_path or str(settings.storage_temp_path / f"ffmpeg_{hash(prompt) & 0xFFFFFFF:07x}.mp4")
        return await asyncio.to_thread(_generate_ffmpeg_video, prompt, "", out)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Extract JSON from text that may have markdown fences or surrounding prose."""
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return m.group(0)
    return text


def _heuristic_storyboard(script: str) -> dict:
    paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()][:8]
    frames = []
    for i, para in enumerate(paragraphs):
        frames.append({
            "description": para[:200],
            "timing": f"{3 + i * 2}s-{5 + i * 2}s",
        })
    return {
        "frames": frames,
        "total_duration": f"{max(5, len(frames) * 5)}s",
    }


# ---------------------------------------------------------------------------
# Convenience composite
# ---------------------------------------------------------------------------

class ModelRouter:
    def __init__(self):
        self.text = TextModelRouter()
        self.video = VideoModelRouter()


model_router = ModelRouter()
