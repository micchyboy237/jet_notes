"""
Comparison between class-based and decorator-based context managers.
Shows when to use each approach.
"""

import time
from contextlib import contextmanager

# ============================================================================
# APPROACH 1: Class-Based Context Manager
# ============================================================================


class FileProcessor:
    """
    Class-based context manager for processing files.
    Better for complex state management and reusable logic.
    """

    def __init__(self, filepath, mode="r"):
        self.filepath = filepath
        self.mode = mode
        self.file_obj = None
        self.lines_processed = 0
        self.start_time = None

    def __enter__(self):
        """Setup: Open file and initialize counters."""
        print(f"[Class] Opening file: {self.filepath}")
        self.file_obj = open(self.filepath, self.mode)
        self.start_time = time.time()
        return self  # Return self so we can access attributes

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Teardown: Close file and report statistics."""
        elapsed = time.time() - self.start_time

        if self.file_obj:
            self.file_obj.close()
            print(
                f"[Class] File closed. Processed {self.lines_processed} lines in {elapsed:.4f}s"
            )

        # Don't suppress exceptions
        return False

    def process_lines(self):
        """Process all lines in the file."""
        for line in self.file_obj:
            self.lines_processed += 1
            # Simulate processing
            pass
        return self.lines_processed


# ============================================================================
# APPROACH 2: Decorator-Based Context Manager
# ============================================================================


@contextmanager
def file_processor(filepath, mode="r"):
    """
    Decorator-based context manager for processing files.
    Simpler but less flexible for complex state.
    """
    print(f"[Decorator] Opening file: {filepath}")
    file_obj = open(filepath, mode)
    start_time = time.time()
    lines_processed = 0

    try:
        # Yield both file object and a mutable dict for tracking
        stats = {"lines_processed": 0}
        yield file_obj, stats
    finally:
        elapsed = time.time() - start_time
        file_obj.close()
        print(
            f"[Decorator] File closed. Processed {stats['lines_processed']} lines in {elapsed:.4f}s"
        )


# ============================================================================
# APPROACH 3: Hybrid - Using contextmanager with a class
# ============================================================================


class DatabaseSession:
    """
    Complex class that benefits from @contextmanager for simplicity.
    Shows how you can combine both approaches.
    """

    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.connected = False
        self.queries_executed = 0

    def connect(self):
        """Establish connection."""
        print(f"[Hybrid] Connecting to {self.connection_string}")
        self.connected = True

    def disconnect(self):
        """Close connection."""
        print(f"[Hybrid] Disconnecting from {self.connection_string}")
        self.connected = False

    def execute_query(self, query):
        """Execute a query."""
        if not self.connected:
            raise RuntimeError("Not connected")
        self.queries_executed += 1
        print(f"[Hybrid] Executing query: {query[:50]}...")


@contextmanager
def managed_db_session(connection_string):
    """
    Use @contextmanager to wrap a complex class.
    Best of both worlds: simple interface, complex implementation.
    """
    session = DatabaseSession(connection_string)
    try:
        session.connect()
        yield session
    finally:
        session.disconnect()


# ============================================================================
# Demo and Comparison
# ============================================================================

if __name__ == "__main__":
    # Create a test file
    test_file = "comparison_test.txt"
    with open(test_file, "w") as f:
        for i in range(100):
            f.write(f"Line {i + 1}: Sample data for testing\n")

    print("=" * 70)
    print("COMPARISON: Class-Based vs Decorator-Based Context Managers")
    print("=" * 70)

    print("\n--- Class-Based Approach ---")
    with FileProcessor(test_file, "r") as processor:
        lines = processor.process_lines()
        print(f"  • Lines processed: {lines}")
        print(
            f"  • Can access attributes: processor.lines_processed = {processor.lines_processed}"
        )

    print("\n--- Decorator-Based Approach ---")
    with file_processor(test_file, "r") as (file_obj, stats):
        for line in file_obj:
            stats["lines_processed"] += 1
        print(f"  • Lines processed: {stats['lines_processed']}")
        print(f"  • Note: Need to track state manually via dict")

    print("\n--- Hybrid Approach (Best of Both) ---")
    with managed_db_session("postgresql://localhost/mydb") as session:
        session.execute_query("SELECT * FROM users")
        session.execute_query("INSERT INTO logs VALUES (...)")
        print(f"  • Queries executed: {session.queries_executed}")
        print(f"  • Connected: {session.connected}")

    # Cleanup
    import os

    if os.path.exists(test_file):
        os.remove(test_file)

    print("\n" + "=" * 70)
    print("WHEN TO USE EACH APPROACH:")
    print("=" * 70)
    print("""
    Use CLASS-BASED when:
    ✓ You need to maintain complex state
    ✓ You want to expose methods/attributes
    ✓ The logic is reusable across multiple contexts
    ✓ You need fine-grained control over enter/exit
    
    Use DECORATOR-BASED (@contextmanager) when:
    ✓ The logic is simple and linear
    ✓ You want minimal boilerplate code
    ✓ The setup/teardown is straightforward
    ✓ You're creating one-off context managers
    
    Use HYBRID when:
    ✓ You have a complex class but want simple context management
    ✓ You want to separate concerns (class handles logic, decorator handles lifecycle)
    """)
