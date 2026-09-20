# Event Emissions Demo

> **Summary:** A demonstration of modern Python 3.12 event-driven patterns using only the standard library. Features generic type-safe buses, decorator-based subscriptions, and asyncio TaskGroups.

## 📂 Structure

- **patterns/**: Core implementations using Python 3.12 generics and async primitives.
- **use_cases/**: Real-world examples (E-commerce, Analytics).
- **utils/**: Helper classes for logging and error handling.

## 🚀 Industry Standard Use Cases

### 1. Decoupled Microservices

Using an **Async Event Bus** to separate business logic from side effects.

- _Why:_ Allows the core API to respond quickly while background tasks run concurrently.

### 2. Audit Trails & History

Using **Event Sourcing** principles where events are immutable records of state changes.

- _Why:_ Provides a complete history of "what happened" for debugging and compliance.

## 💡 Recommendations

| Pattern                      | Best For                               | Tooling                |
| :--------------------------- | :------------------------------------- | :--------------------- |
| **In-Memory Async**          | Single-process apps, modular monoliths | `asyncio`, Custom Bus  |
| **Threaded Fire-and-Forget** | I/O-heavy sync apps (Flask/Django)     | `ThreadPoolExecutor`   |
| **Message Broker**           | Multi-service/distributed systems      | Redis, RabbitMQ, Kafka |

## 🛠️ Getting Started

```bash
python use_cases/ecommerce_demo.py
```
