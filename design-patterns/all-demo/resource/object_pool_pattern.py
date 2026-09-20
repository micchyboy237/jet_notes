"""
Summary: Implements the Object Pool pattern to manage a fixed number of
expensive-to-create resources (like DB connections or ML models).
It recycles instances instead of creating/destroying them repeatedly,
which improves performance and prevents resource exhaustion.
"""

import logging
import queue

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Resource:
    """Simulates an expensive resource, like a DB connection or a Model instance."""

    def __init__(self, id: int):
        self.id = id
        logger.info(f"🏗️ Creating expensive resource #{self.id}")

    def use(self, task: str):
        print(f"⚙️ Resource #{self.id} is processing: {task}")

    def reset(self):
        logger.info(f"🔄 Resetting resource #{self.id} for reuse")


class ObjectPool:
    def __init__(self, max_size: int):
        self._pool = queue.Queue(maxsize=max_size)
        self._max_size = max_size
        self._created_count = 0

    def acquire(self) -> Resource:
        """Get a resource from the pool, or create a new one if under the limit."""
        try:
            # Try to get an existing resource (non-blocking)
            resource = self._pool.get_nowait()
            logger.info(f"♻️ Reusing existing resource #{resource.id}")
            return resource
        except queue.Empty:
            if self._created_count < self._max_size:
                self._created_count += 1
                return Resource(self._created_count)
            else:
                raise RuntimeError("Pool exhausted! Max resources reached.")

    def release(self, resource: Resource):
        """Return a resource to the pool for future reuse."""
        resource.reset()
        try:
            self._pool.put_nowait(resource)
        except queue.Full:
            logger.warning(f"Pool full. Discarding resource #{resource.id}")


if __name__ == "__main__":
    # Create a pool with a maximum of 2 resources (simulating limited VRAM/Connections)
    pool = ObjectPool(max_size=2)

    print("--- Phase 1: Initial Acquisitions ---")
    res1 = pool.acquire()
    res1.use("Task A")

    res2 = pool.acquire()
    res2.use("Task B")

    print("\n--- Phase 2: Releasing and Reusing ---")
    pool.release(res1)
    pool.release(res2)

    # These should reuse the previous instances instead of creating new ones
    res3 = pool.acquire()
    res3.use("Task C")

    res4 = pool.acquire()
    res4.use("Task D")

    print("\n--- Phase 3: Pool Exhaustion Test ---")
    try:
        res5 = pool.acquire()
    except RuntimeError as e:
        print(f"🛑 Error: {e}")
