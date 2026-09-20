"""
Summary: Demonstrates Dependency Injection (DI) to decouple services.
Instead of hardcoding dependencies, they are passed via constructors,
making the code modular and easy to unit test with mocks.
"""

from abc import ABC, abstractmethod


class DataStore(ABC):
    @abstractmethod
    def save(self, data: str) -> None: ...


class SQLStore(DataStore):
    def save(self, data: str):
        print(f"Saving '{data}' to SQL database.")


class NoSQLStore(DataStore):
    def save(self, data: str):
        print(f"Saving '{data}' to NoSQL document store.")


class UserService:
    def __init__(self, store: DataStore):
        self.store = store

    def register_user(self, username: str):
        self.store.save(f"user:{username}")


if __name__ == "__main__":
    # Production usage
    service = UserService(SQLStore())
    service.register_user("Jet")

    # Testing usage (easy to swap implementation)
    test_service = UserService(NoSQLStore())
    test_service.register_user("TestUser")
