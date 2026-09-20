# Shared Context Demo

> **Summary:** Demonstrates modern techniques for sharing state in Python 3.12 using only the standard library. Focuses on Dependency Injection and Async-safe Context Variables.

## 📂 Structure

- **patterns/**: Implementations of DI containers and async context managers.
- **use_cases/**: Examples showing how to pass configuration and user sessions safely.

## 💡 Best Practices

| Technique                 | Use Case             | Why?                                                               |
| :------------------------ | :------------------- | :----------------------------------------------------------------- |
| **Constructor Injection** | Sync apps, testing   | Makes dependencies explicit and easy to mock.                      |
| **Context Variables**     | Async apps (asyncio) | Provides task-local isolation; safe for concurrency.               |
| **Type Aliases (`type`)** | Configuration        | Cleaner syntax for defining shared data structures (Python 3.12+). |

## 🛠️ Getting Started

```bash
python use_cases/di_demo.py
python use_cases/async_context_demo.py
```
