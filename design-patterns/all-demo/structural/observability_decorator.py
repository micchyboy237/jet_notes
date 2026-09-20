"""
Summary: Streamlined tracing decorators for AI/LLM applications.
Uses mock OpenTelemetry and OpenInference conventions to demonstrate
how to wrap functions for observability, including automatic input/output
capture, redaction, and rich attribute setting.
"""

import inspect
import json
from functools import wraps
from typing import Optional

# --- Mocks for OpenTelemetry and OpenInference ---


class MockSpan:
    def __init__(self, name: str):
        self.name = name
        self.attributes = {}
        self._recording = True

    def is_recording(self):
        return self._recording

    def set_attribute(self, key: str, value: str):
        self.attributes[key] = value
        print(f"  [SPAN '{self.name}'] Set attribute: {key}")


class MockTracer:
    def start_as_current_span(self, name: str, **kwargs):
        return _MockSpanContext(name)

    def llm(self, name: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_as_current_span(name) as span:
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def tool(self, name: str, **kwargs):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_as_current_span(name) as span:
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def chain(self, name: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_as_current_span(name) as span:
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def agent(self, name: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_as_current_span(name) as span:
                    return func(*args, **kwargs)

            return wrapper

        return decorator


class _MockSpanContext:
    def __init__(self, name: str):
        self.span = MockSpan(name)

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def get_tracer():
    return MockTracer()


# Mock Semantic Attributes
class SpanAttributes:
    LLM_MODEL_NAME = "llm.model_name"
    LLM_PROVIDER = "llm.provider"
    LLM_INPUT_MESSAGES = "llm.input.messages"
    LLM_INVOCATION_PARAMETERS = "llm.invocation_parameters"
    TOOL_PARAMETERS = "tool.parameters"


# --- Redaction Helper ---


def _redact(text: str) -> str:
    sensitive = ["ssn", "password", "api_key", "secret", "token"]
    lower = text.lower()
    for pattern in sensitive:
        if pattern in lower:
            return "[REDACTED]"
    return text


# --- Observability Decorators ---


def llm(func=None, *, model_name: str = "unknown", provider: str = "llama_cpp"):
    def decorator(f):
        tracer = get_tracer()
        decorated = tracer.llm(name=f.__name__)(f)

        @wraps(decorated)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f.__name__) as span:
                span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model_name)
                span.set_attribute(SpanAttributes.LLM_PROVIDER, provider)

                # Simulate message extraction
                if "messages" in kwargs:
                    msgs = kwargs["messages"]
                    safe_msgs = [
                        {
                            "role": m.get("role"),
                            "content": _redact(str(m.get("content", ""))),
                        }
                        for m in msgs
                    ]
                    span.set_attribute(
                        SpanAttributes.LLM_INPUT_MESSAGES, json.dumps(safe_msgs)
                    )

            return decorated(*args, **kwargs)

        if inspect.iscoroutinefunction(f):

            @wraps(decorated)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(f.__name__) as span:
                    span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model_name)
                    if "messages" in kwargs:
                        msgs = kwargs["messages"]
                        safe_msgs = [
                            {
                                "role": m.get("role"),
                                "content": _redact(str(m.get("content", ""))),
                            }
                            for m in msgs
                        ]
                        span.set_attribute(
                            SpanAttributes.LLM_INPUT_MESSAGES, json.dumps(safe_msgs)
                        )
                return await decorated(*args, **kwargs)

            return async_wrapper

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def tool(func=None, *, name: Optional[str] = None):
    def decorator(f):
        tracer = get_tracer()
        span_name = name or f.__name__
        decorated = tracer.tool(name=span_name)(f)

        @wraps(decorated)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if kwargs:
                    safe_params = {k: _redact(str(v)) for k, v in kwargs.items()}
                    span.set_attribute(
                        SpanAttributes.TOOL_PARAMETERS, json.dumps(safe_params)
                    )
            return decorated(*args, **kwargs)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def chain(func=None, *, name: Optional[str] = None):
    def decorator(f):
        tracer = get_tracer()
        span_name = name or f.__name__
        return tracer.chain(name=span_name)(f)

    if func is not None:
        return decorator(func)
    return decorator


# --- Demo Execution ---


@chain(name="RAG_Pipeline")
def process_query(query: str):
    print(f"Processing query: {query}")
    return retrieve_docs(query)


@tool(name="VectorDB_Search")
def retrieve_docs(query: str):
    print(f"Searching vector DB for: {query}")
    return ["Doc 1", "Doc 2"]


@llm(model_name="llama-3-8b", provider="local")
def generate_answer(context: str, messages: list):
    print(f"Generating answer using context: {context}")
    return "The answer is 42."


if __name__ == "__main__":
    print("--- Starting Observability Demo ---")

    # Test the chain
    result = process_query("What is the meaning of life?")

    # Test LLM with redaction
    final_answer = generate_answer(
        context=result[0],
        messages=[{"role": "user", "content": "My password is secret123"}],
    )

    print(f"\nFinal Result: {final_answer}")
    print("--- Demo Completed ---")
