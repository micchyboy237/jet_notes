"""
Summary: Implements the Chain of Responsibility pattern to pass a request
through a chain of handlers. Useful for filtering, cleaning, or validating
data in a pipeline before it reaches the final destination.
"""

from abc import ABC, abstractmethod


class Handler(ABC):
    def __init__(self):
        self._next_handler = None

    def set_next(self, handler: "Handler") -> "Handler":
        self._next_handler = handler
        return handler

    @abstractmethod
    def handle(self, data: str) -> str: ...


class SpamFilter(Handler):
    def handle(self, data: str) -> str:
        if "spam" in data.lower():
            return "BLOCKED: Spam detected"
        print("✅ Passed Spam Filter")
        return self._next_handler.handle(data) if self._next_handler else data


class ProfanityFilter(Handler):
    def handle(self, data: str) -> str:
        if "badword" in data.lower():
            return "BLOCKED: Profanity detected"
        print("✅ Passed Profanity Filter")
        return self._next_handler.handle(data) if self._next_handler else data


if __name__ == "__main__":
    spam_filter = SpamFilter()
    profanity_filter = ProfanityFilter()

    # Build the chain
    spam_filter.set_next(profanity_filter)

    # Test clean data
    print(spam_filter.handle("This is a clean message"))

    # Test spam
    print(spam_filter.handle("This is spam content"))
