"""
Summary: Uses Python 3.12 'type' alias and contextvars for async-safe,
task-local state management. Avoids external libraries by leveraging the
standard library's built-in isolation for concurrent tasks.
"""

import asyncio
from contextvars import ContextVar
from typing import Self

# Python 3.12 Type Alias for shared configuration
type AppConfig = dict[str, str | int]

# Context variable for task-local state (e.g., request ID or user session)
current_request_id: ContextVar[str] = ContextVar(
    "current_request_id", default="unknown"
)


class AsyncContextManager:
    """Manages the lifecycle of a context variable within an async block."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self._token = None

    async def __aenter__(self) -> Self:
        self._token = current_request_id.set(self.request_id)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            current_request_id.reset(self._token)


if __name__ == "__main__":

    async def demo():
        async with AsyncContextManager("REQ-001"):
            print(f"Inside context: {current_request_id.get()}")

        print(f"Outside context: {current_request_id.get()}")

    asyncio.run(demo())
