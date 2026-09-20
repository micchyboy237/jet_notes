"""
Summary: Python 3.12 Type Aliases for event payloads.
Provides a clean, self-documenting way to define contracts between
producers and consumers without external libraries like Pydantic.
"""

from datetime import datetime
from typing import TypedDict


# Using TypedDict for structured data validation hints
class UserSignupPayload(TypedDict):
    user_id: int
    email: str
    signup_date: str


class OrderCreatedPayload(TypedDict):
    order_id: str
    total_amount: float
    items: list[str]


if __name__ == "__main__":
    # Demo: Show how TypedDict provides structure
    sample: UserSignupPayload = {
        "user_id": 101,
        "email": "jet@example.com",
        "signup_date": datetime.utcnow().isoformat(),
    }
    print(f"Valid payload structure: {sample}")
