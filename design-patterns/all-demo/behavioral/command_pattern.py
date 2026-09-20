"""
Summary: Implements the Command pattern to encapsulate a request as an object.
This allows for queuing requests, logging them, or supporting undo operations.
Great for managing background tasks in a local server.
"""

from abc import ABC, abstractmethod


class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...


class IndexFolderCommand(Command):
    def __init__(self, path: str):
        self.path = path

    def execute(self):
        print(f"📂 Indexing folder: {self.path}...")


class ClearCacheCommand(Command):
    def execute(self):
        print("🧹 Clearing system cache...")


class TaskQueue:
    def __init__(self):
        self._queue = []

    def add_command(self, command: Command):
        self._queue.append(command)

    def run_all(self):
        for cmd in self._queue:
            cmd.execute()
        self._queue.clear()


if __name__ == "__main__":
    queue = TaskQueue()
    queue.add_command(IndexFolderCommand("/docs"))
    queue.add_command(ClearCacheCommand())
    queue.run_all()
