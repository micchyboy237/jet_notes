# Python Design Patterns Demo

> **Summary:** A collection of industry-standard design patterns implemented in Python 3.12. Focuses on readability, testability, and modern syntax like generic classes and type aliases.

## 📂 Structure

- **creational/**: Patterns for object creation (Dependency Injection, Factory).
- **structural/**: Patterns for code organization (Adapter, Decorator).
- **behavioral/**: Patterns for communication and logic (Observer, Strategy).
- **resource/**: Patterns for lifecycle management (Context Manager).

## 💡 Why These Patterns?

| Pattern                  | Category      | Primary Use Case                                       | Why it's Popular                                                           |
| :----------------------- | :------------ | :----------------------------------------------------- | :------------------------------------------------------------------------- |
| **Dependency Injection** | Creational    | Sharing services/config between modules                | Makes code highly testable by removing hidden global state.                |
| **Factory Method**       | Creational    | Creating objects without specifying exact class        | Decouples object creation from usage; great for plugins.                   |
| **Adapter**              | Structural    | Integrating legacy or third-party APIs                 | Allows incompatible interfaces to work together seamlessly.                |
| **Decorator**            | Structural    | Adding logging, auth, or caching logic                 | Keeps business logic clean by separating cross-cutting concerns.           |
| **Observer (Event Bus)** | Behavioral    | Triggering side effects (emails, analytics)            | Enables loose coupling where producers don't need to know about consumers. |
| **Strategy**             | Behavioral    | Swapping algorithms at runtime (e.g., payment methods) | Avoids complex `if/else` chains by encapsulating different behaviors.      |
| **Context Manager**      | Resource Mgmt | Managing database connections or file I/O              | Ensures resources are cleaned up safely using the `with` statement.        |

## 🛠️ Getting Started

Each file is self-contained and includes a `__main__` block for easy testing.

```bash
# Test the Adapter pattern for legacy integration
python structural/adapter_pattern.py

# Test the Observer pattern for event-driven logic
python behavioral/observer_pattern.py

# Test Dependency Injection for modular services
python creational/dependency_injection.py
```
