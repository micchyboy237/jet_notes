"""
Advanced context manager patterns including error handling,
nesting, and dynamic management.
"""

import logging
from contextlib import ExitStack, contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@contextmanager
def database_connection(db_config):
    """Simulated database connection context manager."""
    conn = None
    try:
        logger.info(f"Connecting to database: {db_config['host']}")
        # Simulate connection
        conn = {"host": db_config["host"], "connected": True, "transactions": []}
        yield conn
    except Exception as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn["connected"] = False
        raise
    finally:
        if conn and conn.get("connected"):
            logger.info(f"Closing connection to {db_config['host']}")
            conn["connected"] = False


@contextmanager
def transaction(conn):
    """Transaction context manager that commits or rolls back."""
    if not conn.get("connected"):
        raise RuntimeError("No active database connection")

    try:
        logger.info("Starting transaction")
        yield conn
        logger.info("Committing transaction")
        conn["transactions"].append("committed")
    except Exception as e:
        logger.warning(f"Rolling back transaction: {e}")
        conn["transactions"].append("rolled_back")
        raise


def retry_on_failure(max_retries=3, delay=1):
    """
    Factory function that returns a context manager for retrying operations.

    Note: This is NOT a @contextmanager decorator because retry logic
    doesn't fit the generator pattern well. Instead, we return a class-based
    context manager.
    """
    import time

    class RetryContext:
        def __init__(self, max_retries, delay):
            self.max_retries = max_retries
            self.delay = delay
            self.attempts = 0
            self.last_exception = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                # No exception occurred
                return False

            # An exception occurred - should we retry?
            self.attempts += 1
            self.last_exception = exc_val

            if self.attempts < self.max_retries:
                logger.warning(
                    f"Attempt {self.attempts}/{self.max_retries} failed: {exc_val}"
                )
                logger.info(f"Retrying in {self.delay} seconds...")
                time.sleep(self.delay)
                # Return True to suppress the exception and retry
                return True
            else:
                logger.warning(
                    f"Attempt {self.attempts}/{self.max_retries} failed: {exc_val}"
                )
                # Return False to propagate the exception
                return False

    return RetryContext(max_retries, delay)


@contextmanager
def nested_resources(resource_list):
    """Dynamically manage multiple resources using ExitStack."""
    with ExitStack() as stack:
        managed_resources = []
        for resource_info in resource_list:
            # Simulate opening each resource
            logger.info(f"Opening resource: {resource_info['name']}")
            resource = {"name": resource_info["name"], "open": True}
            stack.callback(lambda r=resource: close_resource(r))
            managed_resources.append(resource)

        yield managed_resources


def close_resource(resource):
    """Helper function to close a resource."""
    if resource.get("open"):
        logger.info(f"Closing resource: {resource['name']}")
        resource["open"] = False


@contextmanager
def conditional_context(condition):
    """Context manager that only activates based on a condition."""
    if condition:
        logger.info("Condition met - entering context")
        yield True
    else:
        logger.info("Condition not met - using null context")
        yield False


# --- Demo Usage ---
if __name__ == "__main__":
    print("=" * 60)
    print("DEMO 1: Database Connection with Transaction")
    print("=" * 60)

    db_config = {"host": "localhost:5432", "database": "mydb"}

    try:
        with database_connection(db_config) as conn:
            with transaction(conn):
                logger.info("Performing database operation")
                conn["transactions"].append("insert_user")
                logger.info("User inserted successfully")
    except Exception as e:
        logger.error(f"Operation failed: {e}")

    print("\n" + "=" * 60)
    print("DEMO 2: Retry on Failure")
    print("=" * 60)

    # Fixed: Use class-based approach for retry logic
    attempt_counter = {"count": 0}

    def flaky_operation():
        attempt_counter["count"] += 1
        print(f"  • Attempting operation (attempt {attempt_counter['count']})")
        if attempt_counter["count"] < 3:
            raise ConnectionError(
                f"Connection failed (attempt {attempt_counter['count']})"
            )
        return "Success!"

    try:
        with retry_on_failure(max_retries=3, delay=0.1) as retry_ctx:
            result = flaky_operation()
            print(f"  • Result: {result}")
    except Exception as e:
        print(f"  • All retries failed: {e}")

    print("\n" + "=" * 60)
    print("DEMO 3: Multiple Resources with ExitStack")
    print("=" * 60)

    resources = [{"name": "database"}, {"name": "cache"}, {"name": "message_queue"}]

    with nested_resources(resources) as managed:
        print(f"  • Active resources: {[r['name'] for r in managed]}")

    print("\n" + "=" * 60)
    print("DEMO 4: Conditional Context")
    print("=" * 60)

    with conditional_context(True) as active:
        if active:
            print("  • Running in active mode")

    with conditional_context(False) as active:
        if not active:
            print("  • Running in passive mode")
