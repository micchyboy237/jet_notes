"""
Summary: Uses the Strategy pattern to encapsulate different algorithms
(e.g., pricing models). Allows the behavior to be swapped at runtime
without changing the class that uses it.
"""

from abc import ABC, abstractmethod


class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, price: float) -> float: ...


class StandardPricing(PricingStrategy):
    def calculate(self, price: float) -> float:
        return price


class PremiumPricing(PricingStrategy):
    def calculate(self, price: float) -> float:
        return price * 1.2  # 20% markup


class Order:
    def __init__(self, strategy: PricingStrategy):
        self.strategy = strategy

    def get_final_price(self, base_price: float) -> float:
        return self.strategy.calculate(base_price)


if __name__ == "__main__":
    standard_order = Order(StandardPricing())
    print(f"Standard Price: ${standard_order.get_final_price(100)}")

    premium_order = Order(PremiumPricing())
    print(f"Premium Price: ${premium_order.get_final_price(100)}")
