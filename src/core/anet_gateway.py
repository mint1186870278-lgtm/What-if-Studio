"""ANet gateway wrapper.

Exposes backend capabilities through ANet-facing service names and delegates
service invocation to the local domain implementation or ANet transport.
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
            logger.info("anet_sdk not available; ANet transport services will be unavailable")

    async def call_service(self, service_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call a service by explicit responsibility boundary.

        - `autogen.*` services are handled by local AutoGen discussion domain.
        - other ANet-facing services require `anet_sdk` transport.
        """
        logger.info(f"Invoking service: {service_name} payload keys={list(payload.keys())}")

        if service_name.startswith("autogen.") or service_name in {
            "agent-director",
            "director",
            "agent-composer",
            "composer",
            "agent-editor",
            "editor",
        }:
            return await dispatch_autogen_service(service_name, payload)

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
            "status": "error",
            "payload_summary": {k: type(v).__name__ for k, v in payload.items()},
            "message": "anet_sdk unavailable: non-autogen ANet service cannot be invoked.",
        }


anet_gateway = ANetGateway()
