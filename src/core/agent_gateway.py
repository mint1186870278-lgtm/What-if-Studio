"""Compatibility wrapper for legacy imports.

Prefer importing from ``src.core.anet_gateway`` directly.
"""

from src.core.anet_gateway import ANetGateway, call_service

# Backward-compatible aliases
anet_gateway = call_service


class AgentGateway:
    """Legacy wrapper — delegates to the flat ``call_service`` function."""

    async def call_agent(self, service_name: str, payload: dict) -> dict:
        return await call_service(service_name, payload)

    async def call_service(self, service_name: str, payload: dict) -> dict:
        return await call_service(service_name, payload)


agent_gateway = call_service
