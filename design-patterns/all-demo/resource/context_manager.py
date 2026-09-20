"""
Summary: Demonstrates the Context Manager pattern for safe resource
management. Ensures resources like database connections or files are
properly opened and closed, even if errors occur during execution.
"""


class ManagedResource:
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


if __name__ == "__main__":
    with ManagedResource("Database Connection") as res:
        res.do_work()
