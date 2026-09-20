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
    Decorator-based retry mechanism.

    Note: Retry logic is better implemented as a decorator rather than
    a context manager, since retries need to re-execute code multiple times.
    Context managers are for resource lifecycle (setup → use → cleanup),
    not for repeating operations.
    """
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt}/{max_retries} failed: {e}")
                    if attempt < max_retries:
                        logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
            raise last_exception

        return wrapper

    return decorator


class RetryManager:
    """
    A manager class that helps with retry logic.
    Usage: Call execute() with a callable.

    This is an alternative to the decorator approach when you need
    more flexibility or want to reuse retry configuration.
    """

    def __init__(self, max_retries=3, delay=1):
        self.max_retries = max_retries
        self.delay = delay

    def execute(self, func, *args, **kwargs):
        """Execute a function with retry logic."""
        import time

        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.delay} seconds...")
                    time.sleep(self.delay)

        raise last_exception


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

    # Approach 1: Using decorator
    print("  --- Approach 1: Decorator-based Retry ---")
    attempt_counter = {"count": 0}

    @retry_on_failure(max_retries=3, delay=0.1)
    def flaky_operation_decorated():
        attempt_counter["count"] += 1
        print(f"  • Attempting operation (attempt {attempt_counter['count']})")
        if attempt_counter["count"] < 3:
            raise ConnectionError(
                f"Connection failed (attempt {attempt_counter['count']})"
            )
        return "Success!"

    try:
        result = flaky_operation_decorated()
        print(f"  • Result: {result}")
    except Exception as e:
        print(f"  • All retries failed: {e}")

    # Approach 2: Using RetryManager
    print("\n  --- Approach 2: RetryManager Class ---")
    attempt_counter2 = {"count": 0}

    def another_flaky_operation():
        attempt_counter2["count"] += 1
        print(f"  • Attempting operation (attempt {attempt_counter2['count']})")
        if attempt_counter2["count"] < 2:
            raise TimeoutError(f"Timeout (attempt {attempt_counter2['count']})")
        return "Completed!"

    retry_mgr = RetryManager(max_retries=3, delay=0.1)
    try:
        result = retry_mgr.execute(another_flaky_operation)
        print(f"  • Result: {result}")
    except Exception as e:
        print(f"  • All retries failed: {e}")

    print("\n  💡 Key Insight: Retry logic is NOT a good fit for context managers!")
    print("     Context managers handle resource lifecycle (setup → use → cleanup)")
    print("     Retries need to re-execute code, which requires decorators or loops")

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
