"""
Summary: Practical e-commerce demo showing decorator-based handler registration
and type-safe event emission. Demonstrates concurrent processing of user signup
(email + analytics) and order creation (warehouse notification).
"""

import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from patterns.async_event_bus import EventBus
from use_cases.events import OrderCreatedPayload, UserSignupPayload

# Initialize the bus with a specific payload type
bus = EventBus[UserSignupPayload | OrderCreatedPayload]()


@bus.on("user.signup")
async def send_welcome_email(payload: UserSignupPayload):
    print(f"[Email Service] Sending welcome email to {payload['email']}")
    await asyncio.sleep(0.5)


@bus.on("user.signup")
def update_analytics(payload: UserSignupPayload):
    print(f"[Analytics Service] Tracking user signup: {payload['user_id']}")


@bus.on("order.created")
async def notify_warehouse(payload: OrderCreatedPayload):
    print(f"[Warehouse Service] Preparing shipment for order {payload['order_id']}")


async def main():
    print("--- Triggering User Signup ---")
    await bus.publish(
        "user.signup",
        {"user_id": 101, "email": "jet@example.com", "signup_date": "2026-09-20"},
    )

    print("\n--- Triggering Order Creation ---")
    await bus.publish(
        "order.created",
        {"order_id": "ORD-999", "total_amount": 150.00, "items": ["Laptop"]},
    )


if __name__ == "__main__":
    asyncio.run(main())
