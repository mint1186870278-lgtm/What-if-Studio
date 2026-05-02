"""ANet gateway wrapper — proper integration with anet SDK.

Three-tier fallback:
  1. Local AutoGen dispatch (always tried first)
  2. ANet P2P mesh (via anet SDK + daemon)
  3. Mocked response (last resort)

Usage
-----
    result = await anet_gateway.call_service("autogen.discussion", {...})
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents import dispatch_autogen_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK client — lazily initialised so the import won't crash when the
# ``anet`` package or its daemon is unavailable.
# ---------------------------------------------------------------------------

_SVC_CLIENT: Any = None
_DAEMON_READY: bool = False


def _probe_sdk() -> tuple[Any, bool]:
    """Try to import anet SDK and probe the local daemon.

    Returns
    -------
    (svc_client | None, daemon_reachable: bool)
    """
    try:
        from anet.svc import SvcClient  # type: ignore[import-untyped]
    except Exception:
        logger.info("anet-sdk not installed; ANet P2P disabled")
        return None, False

    client = SvcClient()
    # Probe daemon health
    try:
        import httpx
        resp = httpx.get("http://127.0.0.1:3998/api/status", timeout=2)
        ok = resp.status_code == 200
        if ok:
            logger.info("✅ ANet daemon reachable at 127.0.0.1:3998")
        else:
            logger.warning("ANet daemon responded with status %s", resp.status_code)
        return client, ok
    except Exception as exc:
        logger.info("ANet daemon not reachable (%s); ANet P2P disabled", exc)
        return client, False


def _ensure_probed() -> None:
    global _SVC_CLIENT, _DAEMON_READY
    if _SVC_CLIENT is None:
        _SVC_CLIENT, _DAEMON_READY = _probe_sdk()


# ---------------------------------------------------------------------------
# Public helpers (called from main.py lifespan)
# ---------------------------------------------------------------------------


def is_daemon_ready() -> bool:
    _ensure_probed()
    return _DAEMON_READY


def get_svc_client() -> Any:
    _ensure_probed()
    return _SVC_CLIENT


# ---------------------------------------------------------------------------
# Service registration
# ---------------------------------------------------------------------------

ANET_SERVICE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "yinanping-studio",
        "endpoint": "http://127.0.0.1:8000",
        "paths": [
            "/api/sessions/{id}/stream",
            "/api/gateway/invoke",
            "/api/video-jobs",
            "/api/video-jobs/{id}/events",
            "/api/projects",
            "/api/sessions",
        ],
        "tags": [
            "video-editing",
            "ai-agent",
            "debate",
            "hackathon",
            "autogen",
        ],
        "description": "AI video editing studio with multi-agent director debate, script generation, and video rendering pipeline",
    },
]


async def register_anet_services() -> list[dict[str, Any]]:
    """Register all local services on the ANet mesh.

    Safe to call even when the daemon is down — returns immediately.
    Returns a list of registration responses (or empty dicts on failure).
    """
    _ensure_probed()
    if not _DAEMON_READY or _SVC_CLIENT is None:
        logger.info("ANet daemon not ready — skipping service registration")
        return []

    results: list[dict[str, Any]] = []
    for svc_def in ANET_SERVICE_DEFINITIONS:
        try:
            resp = _SVC_CLIENT.register(
                name=svc_def["name"],
                endpoint=svc_def["endpoint"],
                paths=svc_def["paths"],
                modes=["rr"],
                free=True,
                tags=svc_def["tags"],
                description=svc_def.get("description"),
            )
            results.append(resp if isinstance(resp, dict) else {"ok": True})
            logger.info("✅ Registered ANet service: %s", svc_def["name"])
        except Exception as exc:
            logger.warning(
                "Failed to register ANet service %s: %s",
                svc_def["name"],
                exc,
            )
            results.append({"error": str(exc)})
    return results


async def unregister_anet_services() -> None:
    """Tear down registered services on shutdown."""
    _ensure_probed()
    if not _DAEMON_READY or _SVC_CLIENT is None:
        return
    for svc_def in ANET_SERVICE_DEFINITIONS:
        try:
            _SVC_CLIENT.unregister(name=svc_def["name"])
            logger.info("Unregistered ANet service: %s", svc_def["name"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Core invocation
# ---------------------------------------------------------------------------


async def call_service(
    service_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Invoke a service through the three-tier fallback.

    Parameters
    ----------
    service_name :
        Name of the service to call (e.g. ``"autogen.discussion"``).
    payload :
        JSON-serialisable request body.

    Returns
    -------
    dict
        Response from the first tier that succeeded, or a ``mocked`` envelope.
    """
    # ── Tier 1: local AutoGen dispatch ──
    try:
        return await dispatch_autogen_service(service_name, payload)
    except Exception as exc:
        logger.debug("Local autogen dispatch failed: %s", exc)

    # ── Tier 2: ANet P2P mesh ──
    _ensure_probed()
    if _DAEMON_READY and _SVC_CLIENT is not None:
        try:
            peers = _SVC_CLIENT.discover(skill=service_name, limit=1)
            if peers:
                # peers can be list[dict] or a single dict depending on version
                peer_list = peers if isinstance(peers, list) else [peers]
                if peer_list:
                    peer = peer_list[0]
                    peer_id = peer.get("peer_id") or peer.get("id") or ""
                    if peer_id:
                        resp = _SVC_CLIENT.call(
                            peer_id=peer_id,
                            service=service_name,
                            path="/generate",
                            method="POST",
                            body=payload,
                        )
                        if resp:
                            return resp if isinstance(resp, dict) else {"result": resp}
        except Exception as exc:
            logger.warning("ANet P2P call failed: %s", exc)

    # ── Tier 3: mocked fallback ──
    return {
        "service": service_name,
        "status": "mocked",
        "payload_summary": {k: type(v).__name__ for k, v in payload.items()},
        "message": "No local handler and no ANet peer available.",
    }


# ---------------------------------------------------------------------------
# Backward-compatible singleton & alias
# ---------------------------------------------------------------------------

anet_gateway = call_service  # function, not class instance — simpler API

# Expose the class for anyone who prefers it
ANetGateway = type("ANetGateway", (), {"call_service": staticmethod(call_service)})
