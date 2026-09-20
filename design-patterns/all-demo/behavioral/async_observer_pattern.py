"""
Summary: Core async event bus using Python 3.12 generic class syntax.
Uses asyncio.TaskGroup for robust concurrent handler execution with
isolated error handling to prevent one failing handler from breaking others.

Industry-standard improvements over basic Observer pattern:
- Async/concurrent handler execution for better performance
- Type-safe generics (EventBus[T]) with TypedDict for strict payload validation
- Fault isolation: one failing handler doesn't break others
- Clean decorator-based registration syntax
- Comprehensive logging for debugging and monitoring
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, NotRequired

from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


# --- Type Definitions ---


class UserSignupPayload(TypedDict):
    user_id: int
    username: str
    email: str
    source: NotRequired[str]  # Optional field


class OrderCreatedPayload(TypedDict):
    order_id: str
    amount: float
    customer_email: str


# --- Core Event Bus Implementation ---


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


# --- Global Bus Instances ---
# We create these first so we can use them in decorators below.
user_bus = EventBus[UserSignupPayload]()
order_bus = EventBus[OrderCreatedPayload]()


# --- Global Handler Definitions with Decorators ---


@user_bus.on("user.signup")
def send_welcome_email(data: UserSignupPayload):
    """Simulate sending a welcome email"""
    print(f"📧 Sending welcome email to {data['username']} ({data['email']})")


@user_bus.on("user.signup")
async def update_analytics(data: UserSignupPayload):
    """Simulate async analytics tracking"""
    await asyncio.sleep(0.1)  # Simulate network delay
    source = data.get("source", "unknown")
    print(f"📊 Tracking signup: user_id={data['user_id']}, source={source}")


@user_bus.on("user.signup")
def notify_slack(data: UserSignupPayload):
    """Simulate Slack notification"""
    print(f"💬 Slack notification: New user {data['username']} signed up!")


@user_bus.on("user.signup")
def failing_handler(data: UserSignupPayload):
    """Simulate a handler that fails to test error isolation"""
    raise ValueError("This handler intentionally fails!")


@order_bus.on("order.created")
async def process_payment(data: OrderCreatedPayload):
    """Simulate async payment processing"""
    await asyncio.sleep(0.2)  # Simulate payment gateway delay
    print(f"💳 Processing payment: ${data['amount']:.2f} for order #{data['order_id']}")


@order_bus.on("order.created")
def send_confirmation(data: OrderCreatedPayload):
    """Simulate sending order confirmation"""
    print(f"📧 Order confirmation sent to {data['customer_email']}")


# --- Demo Execution ---

if __name__ == "__main__":
    # Configure logging to see the output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async def run_demo():
        print("=" * 60)
        print("Async Observer Pattern (Event Bus) Demo")
        print("=" * 60)

        # Test 1: User signup event with multiple handlers
        print("\n--- Test 1: User Signup Event ---")
        await user_bus.publish(
            "user.signup",
            {
                "user_id": 101,
                "username": "Jet",
                "email": "jet@example.com",
                "source": "referral",
            },
        )

        # Test 2: Order created event
        print("\n--- Test 2: Order Created Event ---")
        await order_bus.publish(
            "order.created",
            {
                "order_id": "ORD-2026-001",
                "amount": 150.50,
                "customer_email": "jet@example.com",
            },
        )

        # Test 3: Event with no handlers
        print("\n--- Test 3: Unknown Event (No Handlers) ---")
        await user_bus.publish("unknown.event", {"test": "data"})  # type: ignore

        print("\n" + "=" * 60)
        print("Demo completed successfully!")
        print("=" * 60)

    asyncio.run(run_demo())
