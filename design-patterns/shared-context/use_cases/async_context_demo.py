"""
Summary: Real-world example of using contextvars to track a 'User Session'
across multiple async calls. Shows how to use the custom AsyncContextManager
to ensure state is isolated even when tasks run concurrently.
"""

import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from patterns.context_manager import AsyncContextManager, current_request_id


async def fetch_profile():
    """Simulates an API call that needs the current request context."""
    req_id = current_request_id.get()
    await asyncio.sleep(0.1)
    return f"Profile for request {req_id}"


async def log_access():
    """Simulates logging that requires the same context."""
    req_id = current_request_id.get()
    print(f"[LOG] Accessing resource in context: {req_id}")


async def handle_concurrent_requests():
    """Runs multiple requests in parallel with isolated contexts."""

    async def process_request(req_id: str):
        async with AsyncContextManager(req_id):
            profile = await fetch_profile()
            await log_access()
            print(f"Result: {profile}")

    # Run two requests at the same time
    await asyncio.gather(process_request("USER-A"), process_request("USER-B"))


if __name__ == "__main__":
    asyncio.run(handle_concurrent_requests())
