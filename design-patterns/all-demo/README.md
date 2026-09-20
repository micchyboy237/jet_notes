# Python Industry-Standard Design Patterns Demo

> **Summary:** A collection of industry-standard design patterns implemented in Python 3.12. Focuses on readability, testability, and modern syntax like generic classes and type aliases.

## 📂 Structure

- **creational/**: Patterns for object creation (Dependency Injection, Factory, Singleton, Builder).
- **structural/**: Patterns for code organization (Adapter, Decorator, Facade, Observability).
- **behavioral/**: Patterns for communication and logic (Observer, Strategy, Chain of Responsibility, Command).
- **resource/**: Patterns for lifecycle management (Context Manager, Object Pool).

## 💡 Why These Patterns?

| Pattern                  | Category      | Primary Use Case                                       | Why it's Popular                                                              |
| :----------------------- | :------------ | :----------------------------------------------------- | :---------------------------------------------------------------------------- |
| **Dependency Injection** | Creational    | Sharing services/config between modules                | Makes code highly testable by removing hidden global state.                   |
| **Factory Method**       | Creational    | Creating objects without specifying exact class        | Decouples object creation from usage; great for plugins.                      |
| **Singleton**            | Creational    | Managing single instances (DB, LLM models)             | Ensures resource efficiency and consistent state across the app.              |
| **Builder**              | Creational    | Constructing complex configuration objects             | Improves readability over large constructors with many optional args.         |
| **Adapter**              | Structural    | Integrating legacy or third-party APIs                 | Allows incompatible interfaces to work together seamlessly.                   |
| **Decorator**            | Structural    | Adding logging, auth, or caching logic                 | Keeps business logic clean by separating cross-cutting concerns.              |
| **Observability Decor.** | Structural    | Tracing AI/LLM pipelines with OpenTelemetry            | Provides deep visibility into model calls and tool usage with auto-redaction. |
| **Facade**               | Structural    | Simplifying complex subsystems (Search + LLM)          | Provides a single, simple entry point for complicated logic.                  |
| **Observer (Event Bus)** | Behavioral    | Triggering side effects (emails, analytics)            | Enables loose coupling where producers don't need to know about consumers.    |
| **Strategy**             | Behavioral    | Swapping algorithms at runtime (e.g., payment methods) | Avoids complex `if/else` chains by encapsulating different behaviors.         |
| **Chain of Resp.**       | Behavioral    | Processing pipelines (filtering, validation)           | Allows dynamic composition of processing steps.                               |
| **Command**              | Behavioral    | Handling background jobs or user actions               | Encapsulates requests for queuing, logging, or undo support.                  |
| **Context Manager**      | Resource Mgmt | Managing database connections or file I/O              | Ensures resources are cleaned up safely using the `with` statement.           |
| **Object Pool**          | Resource Mgmt | Reusing expensive resources (Models, DB Connections)   | Prevents resource exhaustion and improves performance by recycling objects.   |

## 🛠️ Getting Started

Each file is self-contained and includes a `__main__` block for easy testing.

```bash
# Test the Singleton pattern for resource management
python creational/singleton_pattern.py
# Test the Observability Decorator for AI tracing
python structural/observability_decorator.py
# Test the Chain of Responsibility for data pipelines
python behavioral/chain_of_responsibility.py
# Test the Object Pool for efficient resource reuse
python resource/object_pool_pattern.py
```
