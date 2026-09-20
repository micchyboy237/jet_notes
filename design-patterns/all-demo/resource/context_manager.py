"""
Summary: Demonstrates the Context Manager pattern for safe resource
management. Ensures resources like database connections or files are
properly opened and closed, even if errors occur during execution.
"""

import time


class DatabaseConnection:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        print(f"Opening resource: {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"Closing resource: {self.name}")
        if exc_type:
            print(f"An error occurred: {exc_val}")
        return False  # Don't suppress exceptions

    def do_work(self):
        print(f"Working with {self.name}...")


class Timer:
    """Context manager to measure execution time of a code block."""

    def __init__(self, label: str = "Execution"):
        self.label = label
        self.start_time = None
        self.elapsed_time = None

    def __enter__(self):
        self.start_time = time.time()
        print(f"[{self.label}] Starting timer...")
        return self  # Allows access to timer attributes

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed_time = time.time() - self.start_time
        print(f"[{self.label}] Completed in {self.elapsed_time:.4f} seconds")

        if exc_type:
            print(f"[{self.label}] Error occurred: {exc_type.__name__}: {exc_val}")

        return False  # Don't suppress exceptions


if __name__ == "__main__":
    print("\nExample 1: Database Connection")
    with DatabaseConnection("Database Connection") as conn:
        conn.do_work()

    print("\nExample 2: Timer Context Manager")
    with Timer("Data Processing") as timer:
        # Simulate some work
        total = sum(range(1_000_000))
        print(f"Computed sum: {total}")
