"""
Summary: Implements the Singleton pattern to ensure a class has only
one instance. This is critical for managing shared resources like
database connections or heavy ML models (e.g., llama.cpp).
"""

import threading


class ModelManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    print(
                        "🚀 Initializing Model Manager (Loading weights into VRAM)..."
                    )
                    cls._instance = super().__new__(cls)
                    cls._instance.model_loaded = True
        return cls._instance

    def query(self, prompt: str):
        if not self.model_loaded:
            raise RuntimeError("Model not initialized")
        return f"Response to: '{prompt}'"


if __name__ == "__main__":
    # First call initializes the resource
    manager1 = ModelManager()

    # Second call returns the same instance without re-initializing
    manager2 = ModelManager()

    print(f"Same instance? {manager1 is manager2}")
    print(manager1.query("What is Python?"))
