"""
Summary: Uses the Factory Method pattern to create objects without
specifying their exact class. Useful for handling multiple types of
inputs or plugins while keeping the client code clean.
"""

from abc import ABC, abstractmethod


class Notification(ABC):
    @abstractmethod
    def send(self, message: str) -> None: ...


class EmailNotification(Notification):
    def send(self, message: str):
        print(f"📧 Email sent: {message}")


class SMSNotification(Notification):
    def send(self, message: str):
        print(f"📱 SMS sent: {message}")


def notification_factory(channel: str) -> Notification:
    match channel:
        case "email":
            return EmailNotification()
        case "sms":
            return SMSNotification()
        case _:
            raise ValueError(f"Unsupported channel: {channel}")


if __name__ == "__main__":
    notifier = notification_factory("email")
    notifier.send("Your order has been shipped!")
