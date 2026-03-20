from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from .types import A2AMessage, A2AResponse


A2AHandler = Callable[[A2AMessage], A2AResponse]


class A2ABus:
    """In-process A2A router for structured agent-to-agent messages."""

    def __init__(self):
        self._handlers: dict[str, A2AHandler] = {}

    def register(self, agent_name: str, handler: A2AHandler) -> None:
        self._handlers[agent_name] = handler

    def send(self, msg: A2AMessage) -> A2AResponse:
        handler = self._handlers.get(msg.to_agent)
        if handler is None:
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="bus",
                to_agent=msg.from_agent,
                ok=False,
                payload={},
                error=f"No A2A handler registered for '{msg.to_agent}'",
            )

        response = handler(msg)

        # Defensive normalization for debugging and traceability.
        normalized = asdict(response)
        return A2AResponse(**normalized)
