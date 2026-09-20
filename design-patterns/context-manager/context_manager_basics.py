"""
Basic examples of @contextmanager decorator usage.
Demonstrates simple resource management patterns.
"""

from contextlib import contextmanager


@contextmanager
def simple_context():
    """Simplest context manager - just tracks entry and exit."""
    print("  → Entering context")
    yield
    print("  → Exiting context")


@contextmanager
def context_with_value():
    """Context manager that yields a value to the 'as' clause."""
    print("  → Setting up resource")
    resource = {"data": "important information", "status": "active"}
    try:
        yield resource
    finally:
        print("  → Cleaning up resource")
        resource["status"] = "closed"


@contextmanager
def managed_file(filepath, mode="r"):
    """Custom file context manager (for demonstration)."""
    print(f"  → Opening file: {filepath} in mode '{mode}'")
    file_obj = open(filepath, mode)
    try:
        yield file_obj
    finally:
        print(f"  → Closing file: {filepath}")
        file_obj.close()


@contextmanager
def timer(label="Operation"):
    """Simple timer context manager."""
    import time

    start = time.time()
    print(f"  → Starting '{label}'...")
    try:
        yield
    finally:
        elapsed = time.time() - start
        print(f"  → '{label}' completed in {elapsed:.4f} seconds")


@contextmanager
def suppress_and_log(*exceptions):
    """Context manager that suppresses specific exceptions and logs them."""
    try:
        yield
    except exceptions as e:
        print(f"  → Suppressed exception: {type(e).__name__}: {e}")


# --- Demo Usage ---
if __name__ == "__main__":
    print("=" * 60)
    print("DEMO 1: Simple Context Manager")
    print("=" * 60)
    with simple_context():
        print("  • Inside the context")

    print("\n" + "=" * 60)
    print("DEMO 2: Context Manager with Value")
    print("=" * 60)
    with context_with_value() as resource:
        print(f"  • Using resource: {resource}")

    print("\n" + "=" * 60)
    print("DEMO 3: Managed File")
    print("=" * 60)
    # Create a test file first
    with open("test_demo.txt", "w") as f:
        f.write("Test content for context manager demo")

    with managed_file("test_demo.txt", "r") as f:
        content = f.read()
        print(f"  • Read content: '{content}'")

    print("\n" + "=" * 60)
    print("DEMO 4: Timer Context Manager")
    print("=" * 60)
    with timer("Sample Operation"):
        import time

        time.sleep(0.5)  # Simulate work

    print("\n" + "=" * 60)
    print("DEMO 5: Exception Suppression")
    print("=" * 60)
    with suppress_and_log(ValueError, KeyError):
        print("  • About to raise ValueError...")
        raise ValueError("This will be suppressed")

    print("  • Execution continues after suppressed exception")

    # Clean up test file
    import os

    if os.path.exists("test_demo.txt"):
        os.remove("test_demo.txt")
