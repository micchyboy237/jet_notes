# save_json.py
import json
import shutil
from pathlib import Path

from mitmproxy import http

# Setup output directory
OUTPUT_DIR = Path(__file__).parent / "generated" / "llamacpp_logs"
shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = OUTPUT_DIR / "llm_logs.jsonl"


def response(flow: http.HTTPFlow) -> None:
    """
    Log LLM-related requests and responses to a JSONL file.

    Note: flow.response can be None if there was a connection error
    or if the response hasn't been received yet.
    """
    # Safety check: response might be None
    if flow.response is None:
        return

    # Filter for your LLM endpoints
    if "/v1/chat/completions" not in flow.request.path:
        return

    # Calculate duration manually using timestamps
    # timestamp_start is when the request began
    # timestamp_end is when the response completed
    duration_ms = None
    if hasattr(flow.response, "timestamp_end") and flow.response.timestamp_end:
        duration_ms = (flow.response.timestamp_end - flow.timestamp_start) * 1000

    # Safely extract request data
    request_body = None
    if flow.request.content:
        try:
            request_body = flow.request.content.decode("utf-8", errors="ignore")
        except Exception:
            request_body = "<decode error>"

    # Safely extract response data
    response_body = None
    if flow.response.content:
        try:
            response_body = flow.response.content.decode("utf-8", errors="ignore")
        except Exception:
            response_body = "<decode error>"

    data = {
        "timestamp": flow.timestamp_start,
        "method": flow.request.method,
        "path": flow.request.path,
        "request_headers": dict(flow.request.headers),
        "request_body": request_body,
        "response_status": flow.response.status_code,
        "response_headers": dict(flow.response.headers),
        "response_body": response_body,
        "duration_ms": duration_ms,
    }

    # Append to JSONL file (one JSON object per line)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")

    print(
        f"✅ Logged: {flow.request.method} {flow.request.path} → {flow.response.status_code} ({duration_ms:.0f}ms)"
        if duration_ms
        else f"✅ Logged: {flow.request.method} {flow.request.path} → {flow.response.status_code}"
    )
