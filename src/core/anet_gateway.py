"""ANet gateway wrapper.

Routes calls to local AutoGen services first and falls back to anet_sdk when available.
"""

import logging
from typing import Any, Dict

from src.agents import dispatch_autogen_service

logger = logging.getLogger(__name__)


class ANetGateway:
    def __init__(self):
        self.client = None
        try:
            import anet_sdk  # type: ignore

            try:
                self.client = anet_sdk.SvcClient()
                logger.info("✅ anet_sdk SvcClient initialized")
            except Exception as e:
                logger.warning(f"anet_sdk present but failed to init SvcClient: {e}")
                self.client = None
        except Exception:
            logger.info("anet_sdk not available; using local autogen dispatch first")

    async def call_service(self, service_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call an ANet-facing service name."""
        logger.info(f"Invoking service: {service_name} payload keys={list(payload.keys())}")

        try:
            return await dispatch_autogen_service(service_name, payload)
        except Exception as local_exc:
            logger.warning("Local autogen dispatch failed, trying anet_sdk fallback: %s", local_exc)

        if self.client:
            try:
                call_fn = getattr(self.client, "call", None)
                if callable(call_fn):
                    result = call_fn(service_name, payload)
                    if hasattr(result, "__await__"):
                        result = await result  # type: ignore
                    return result or {}
            except Exception as e:
                logger.error(f"anet call failed: {e}")
                return {"error": str(e)}

        return {
            "service": service_name,
            "status": "mocked",
            "payload_summary": {k: type(v).__name__ for k, v in payload.items()},
            "message": "No local autogen match and anet_sdk unavailable.",
        }


anet_gateway = ANetGateway()
