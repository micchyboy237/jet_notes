"""
Summary: Implements the Decorator pattern to add cross-cutting concerns
like logging or timing to functions. Keeps the core business logic
clean and focused on its primary task.
"""

import functools


def log_execution(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"[LOG] Starting {func.__name__}...")
        result = func(*args, **kwargs)
        print(f"[LOG] Finished {func.__name__}.")
        return result

    return wrapper


@log_execution
def process_payment(amount: float):
    print(f"Processing payment of ${amount:.2f}")
    return True


if __name__ == "__main__":
    process_payment(150.00)
