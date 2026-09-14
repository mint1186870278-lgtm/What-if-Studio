from __future__ import annotations

import asyncio

from src.core import anet_gateway


def test_anet_does_not_fallback_to_local_autogen(monkeypatch) -> None:
    monkeypatch.setattr(anet_gateway, "_SVC_CLIENT", None)
    monkeypatch.setattr(anet_gateway, "_DAEMON_READY", False)
    monkeypatch.setattr(anet_gateway, "_probe_sdk", lambda: (None, False))
    result = asyncio.run(anet_gateway.call_service("autogen-discussion", {"prompt": "test"}))
    assert result["status"] == "unavailable"
    assert "not used as a fallback" in result["message"]
