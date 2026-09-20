"""
Summary: Implements the Observer pattern using Class Inheritance.
Instead of a central bus, objects extend a base EventEmitter and
override specific hook methods to react to events.

This approach is useful when:
- You want to enforce a specific structure via Abstract Base Classes (ABC).
- You want to bundle state and behavior together in one object.
- You are working in a synchronous environment.
"""

import logging
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class EventEmitter:
    """Base class that provides the core event triggering logic."""

    def __init__(self):
        self._listeners = []

    def add_listener(self, listener: "EventListener"):
        """Register a listener to this emitter."""
        self._listeners.append(listener)
        logger.info(f"Listener {listener.__class__.__name__} added.")

    def notify(self, event_name: str, data: dict):
        """Notify all registered listeners about an event."""
        logger.info(f"Emitting event: {event_name}")
        for listener in self._listeners:
            # We use getattr to check if the listener has a handler for this event
            handler = getattr(listener, f"on_{event_name}", None)
            if handler and callable(handler):
                try:
                    handler(data)
                except Exception as e:
                    logger.error(f"Error in {listener.__class__.__name__}: {e}")


class EventListener(ABC):
    """Abstract base class for all listeners. Enforces structure."""

    @abstractmethod
    def on_error(self, data: dict):
        """Every listener must handle errors."""
        pass


class AnalyticsService(EventListener):
    """Concrete listener that overrides hooks to track specific events."""

    def on_user_login(self, data: dict):
        print(f"📊 [Analytics] User '{data['username']}' logged in from {data['ip']}.")

    def on_purchase(self, data: dict):
        print(
            f"💰 [Analytics] Recorded purchase of ${data['amount']} by user {data['username']}."
        )

    def on_error(self, data: dict):
        print(f"⚠️ [Analytics] Tracking system error: {data['message']}")


class NotificationService(EventListener):
    """Concrete listener focused on user communication."""

    def on_user_login(self, data: dict):
        print(f"🔔 [Notify] Welcome back, {data['username']}!")

    def on_purchase(self, data: dict):
        print(
            f"🧾 [Notify] Sending receipt to {data['email']} for order #{data['order_id']}."
        )

    def on_error(self, data: dict):
        print(f"🚨 [Notify] Alerting admin about system error: {data['message']}")


if __name__ == "__main__":
    # 1. Create the central emitter
    app_emitter = EventEmitter()

    # 2. Create concrete listeners (these could be complex services)
    analytics = AnalyticsService()
    notifications = NotificationService()

    # 3. Register listeners
    app_emitter.add_listener(analytics)
    app_emitter.add_listener(notifications)

    print("\n--- Simulating User Login ---")
    app_emitter.notify("user_login", {"username": "Jet", "ip": "192.168.1.50"})

    print("\n--- Simulating Purchase ---")
    app_emitter.notify(
        "purchase",
        {
            "username": "Jet",
            "email": "jet@example.com",
            "amount": 99.99,
            "order_id": "ORD-555",
        },
    )

    print("\n--- Simulating System Error ---")
    app_emitter.notify("error", {"message": "Database connection timeout"})
