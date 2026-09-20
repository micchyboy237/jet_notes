"""
Summary: Core async event bus using Python 3.12 generic class syntax.
Uses asyncio.TaskGroup for robust concurrent handler execution with
isolated error handling to prevent one failing handler from breaking others.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


# Python 3.12 Generic Class Syntax
class EventBus[T]:
    def __init__(self):
        # Map event types to list of handlers
        self._handlers: Dict[str, List[Callable[[T], Any]]] = {}

    def on(self, event_type: str):
        """Decorator to register a handler for an event type"""

        def decorator(func: Callable[[T], Any]):
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(func)
            logger.info(
                f"Registered handler '{func.__name__}' for event '{event_type}'"
            )
            return func

        return decorator

    async def publish(self, event_type: str, payload: T):
        """Publish an event to all registered handlers concurrently using TaskGroup"""
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.warning(f"No handlers found for event: {event_type}")
            return

        # TaskGroup ensures all tasks are cancelled if one fails critically
        async with asyncio.TaskGroup() as tg:
            for handler in handlers:
                tg.create_task(self._safe_execute(handler, payload))

    async def _safe_execute(self, handler: Callable[[T], Any], payload: T):
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(payload)
            else:
                handler(payload)
        except Exception as e:
            logger.error(f"Handler {handler.__name__} failed: {e}", exc_info=True)


if __name__ == "__main__":
    bus = EventBus[dict]()

    @bus.on("test.event")
    def simple_handler(data):
        print(f"Received: {data}")

    async def run():
        await bus.publish("test.event", {"msg": "Hello World"})

    asyncio.run(run())
