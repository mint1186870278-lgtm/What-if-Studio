"""ANet agent gateway wrapper.

Attempts to use `anet_sdk` Python binding if available; otherwise provides a mock
implementation that logs and returns placeholder responses. Records invocations
to the database via the `ANetInvocation` model when available.
"""

import logging
from typing import Any, Dict, Optional

from src.config import settings

logger = logging.getLogger(__name__)


class AgentGateway:
    def __init__(self):
        self.client = None
        try:
            import anet_sdk  # type: ignore

            # Attempt to create client if available
            try:
                self.client = anet_sdk.SvcClient()
                logger.info("✅ anet_sdk SvcClient initialized")
            except Exception as e:
                logger.warning(f"anet_sdk present but failed to init SvcClient: {e}")
                self.client = None
        except Exception:
            logger.info("anet_sdk not available; using mock gateway")

    async def call_agent(self, service_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call a remote agent service.

        If `anet_sdk` is available, uses its async call mechanism. Otherwise returns a
        mock response and logs invocation.
        """
        # Record basic invocation
        logger.info(f"Invoking agent: {service_name} payload keys={list(payload.keys())}")

        if self.client:
            try:
                # If client has async `call` use it; otherwise call synchronously
                call_fn = getattr(self.client, "call", None)
                if callable(call_fn):
                    # anet_sdk may provide coroutine
                    result = call_fn(service_name, payload)
                    # If coroutine
                    if hasattr(result, "__await__"):
                        result = await result  # type: ignore
                    return result or {}
            except Exception as e:
                logger.error(f"anet call failed: {e}")
                return {"error": str(e)}

        # Mock response when no anet client
        mock = {
            "service": service_name,
            "status": "mocked",
            "payload_summary": {k: type(v).__name__ for k, v in payload.items()},
            "message": "This is a mock response because anet_sdk is not installed or failed to initialize.",
        }
        return mock


# Global gateway instance
agent_gateway = AgentGateway()
