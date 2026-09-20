"""
Summary: Implements the Observer pattern (Event Bus) to allow objects
to subscribe to events. This enables loose coupling where a producer
can notify multiple consumers without knowing who they are.

Updated with complete typing using TypedDict and Generic-style type hints
for better IDE support and code safety.
"""

from typing import Any, Callable, Dict, List

from typing_extensions import TypedDict

# --- Type Definitions ---


class UserSignupPayload(TypedDict):
    user: str
    id: int


# --- Core Event Bus Implementation ---


class EventBus:
    def __init__(self):
        # Map event types to list of handlers
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event_name: str, callback: Callable[[Any], None]):
        """Register a handler for a specific event."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    def emit(self, event_name: str, data: Any):
        """Notify all registered handlers for an event."""
        for callback in self._subscribers.get(event_name, []):
            callback(data)


# --- Handler Definitions ---


def send_email(data: UserSignupPayload):
    """Simulate sending an email notification."""
    print(f"📧 Sending email to {data['user']}")


def update_analytics(data: UserSignupPayload):
    """Simulate tracking user analytics."""
    print(f"📊 Tracking user: {data['user']}")


# --- Usage Example ---

if __name__ == "__main__":
    bus = EventBus()

    # Multiple subscribers for the same event
    bus.subscribe("user.signup", send_email)
    bus.subscribe("user.signup", update_analytics)

    # Emitting the event triggers all subscribers
    bus.emit("user.signup", {"user": "Jet", "id": 101})
