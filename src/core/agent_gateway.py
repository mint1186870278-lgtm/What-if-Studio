"""Compatibility wrapper for legacy imports.

Prefer src.core.anet_gateway.ANetGateway and src.core.anet_gateway.anet_gateway.
"""

from src.core.anet_gateway import ANetGateway, anet_gateway


class AgentGateway(ANetGateway):
    async def call_agent(self, service_name, payload):
        return await self.call_service(service_name, payload)


agent_gateway = anet_gateway

