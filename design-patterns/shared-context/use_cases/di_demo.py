"""
Summary: Demonstrates how to wire up a small application using Constructor
Injection. Shows how different modules can share a database connection
without relying on a global variable or a complex DI framework.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from patterns.di_injection import DatabaseConnection, UserService


def main():
    # 1. Create the shared dependency
    shared_db = DatabaseConnection("postgres://localhost/mydb")

    # 2. Inject it into services that need it
    user_service = UserService(shared_db)

    # 3. Use the service
    print(user_service.get_user(42))


if __name__ == "__main__":
    main()
