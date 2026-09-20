"""
Summary: Implements the Adapter pattern to make incompatible interfaces
work together. This is essential when integrating third-party libraries
or legacy code without modifying their source.
"""

from abc import ABC, abstractmethod


# Target Interface: What our application expects
class ModernPaymentProcessor(ABC):
    @abstractmethod
    def pay(self, amount: float, currency: str) -> bool: ...


# Legacy Service: An old library we can't change
class LegacyBankAPI:
    def transfer_funds(self, value: int, curr: str) -> str:
        print(f"Legacy API: Transferring {value} {curr}")
        return "SUCCESS"


# The Adapter: Bridges the gap between the two
class BankAPIAdapter(ModernPaymentProcessor):
    def __init__(self, legacy_api: LegacyBankAPI):
        self.legacy_api = legacy_api

    def pay(self, amount: float, currency: str) -> bool:
        # Convert float to int as required by the legacy API
        result = self.legacy_api.transfer_funds(int(amount), currency)
        return result == "SUCCESS"


if __name__ == "__main__":
    legacy_system = LegacyBankAPI()
    adapter = BankAPIAdapter(legacy_system)

    # Now we can use the modern interface with the old system
    success = adapter.pay(150.50, "USD")
    print(f"Transaction successful: {success}")
