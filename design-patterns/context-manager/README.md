# Context Manager Demos

Comprehensive examples demonstrating Python's `contextlib.contextmanager` decorator and related patterns.

## Files Overview

### 1. `context_manager_basics.py`

Basic examples showing:

- Simple context tracking
- Yielding values
- File management
- Timing operations
- Exception suppression

**Run:** `python context_manager_basics.py`

### 2. `advanced_context_managers.py`

Advanced patterns including:

- Database connections with transactions
- Retry logic on failures
- Dynamic resource management with `ExitStack`
- Conditional contexts

**Run:** `python advanced_context_managers.py`

### 3. `class_vs_decorator_comparison.py`

Side-by-side comparison of:

- Class-based context managers (`__enter__`/`__exit__`)
- Decorator-based (`@contextmanager`)
- Hybrid approaches

Includes guidelines on when to use each approach.

**Run:** `python class_vs_decorator_comparison.py`

### 4. `real_world_examples.py`

Practical use cases:

- Temporary directories with cleanup
- Atomic file writes
- Configuration loading
- Progress tracking
- Environment variable mocking
- Output capture for testing

**Run:** `python real_world_examples.py`

## Key Concepts

### What is `@contextmanager`?

A decorator that converts a generator function into a context manager, eliminating the need for class-based implementations.

### Pattern

```python
from contextlib import contextmanager

@contextmanager
def my_context():
    # Setup code (runs on __enter__)
    resource = acquire_resource()
    try:
        yield resource  # Value bound to 'as' variable
    finally:
        # Teardown code (runs on __exit__)
        release_resource(resource)
```

### When Introduced

- **Python 2.5**: Initial introduction alongside `with` statement
- **Python 3.2**: Enhanced with `ContextDecorator` support

### Better Alternatives

| Scenario                  | Alternative             | Why                                  |
| ------------------------- | ----------------------- | ------------------------------------ |
| Complex state             | Class-based             | More control, better organization    |
| Multiple dynamic contexts | `ExitStack`             | Handles variable numbers of contexts |
| Objects with `close()`    | `contextlib.closing`    | Simpler wrapper                      |
| Built-in support          | Native context managers | Optimized, less code                 |

## Requirements

- Python 3.6+ (for f-strings and modern features)
- No external dependencies (uses only standard library)

## Testing

All demos include `if __name__ == "__main__"` blocks for easy execution.

## Best Practices

1. Always use `try/finally` to ensure cleanup
2. Re-raise exceptions unless intentionally suppressing
3. Keep context managers focused on single responsibilities
4. Document what resources are managed
5. Test exception handling paths
