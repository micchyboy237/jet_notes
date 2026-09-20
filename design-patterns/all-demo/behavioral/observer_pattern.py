"""
Summary: Implements the Observer pattern (Event Bus) to allow objects
to subscribe to events. This enables loose coupling where a producer
can notify multiple consumers without knowing who they are.
"""

from typing import Callable


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_name: str, callback: Callable):
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    def emit(self, event_name: str, data: any):
        for callback in self._subscribers.get(event_name, []):
            callback(data)


# --- Usage Example ---
def send_email(data: dict):
    print(f"📧 Sending email to {data['user']}")


def update_analytics(data: dict):
    print(f"📊 Tracking user: {data['user']}")


if __name__ == "__main__":
    bus = EventBus()

    # Multiple subscribers for the same event
    bus.subscribe("user.signup", send_email)
    bus.subscribe("user.signup", update_analytics)

    # Emitting the event triggers all subscribers
    bus.emit("user.signup", {"user": "Jet", "id": 101})
