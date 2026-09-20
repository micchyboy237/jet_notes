"""
Summary: Demonstrates Constructor Injection, the preferred Pythonic pattern
for sharing state. Dependencies are passed explicitly, avoiding global
variables and making the code modular and testable without frameworks.
"""


class DatabaseConnection:
    def __init__(self, url: str):
        self.url = url

    def query(self, sql: str) -> str:
        return f"Executed '{sql}' on {self.url}"


class UserService:
    """Service that receives its dependency via constructor injection."""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_user(self, user_id: int) -> str:
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")


if __name__ == "__main__":
    # Composition root: wiring dependencies together at the top level
    db = DatabaseConnection("sqlite:///app.db")
    service = UserService(db)
    print(service.get_user(101))
