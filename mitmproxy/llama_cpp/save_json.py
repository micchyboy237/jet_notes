# save_json.py
import json
import shutil
from datetime import datetime
from pathlib import Path

from mitmproxy import http

# Setup output directory
OUTPUT_DIR = Path(__file__).parent / "generated" / "llamacpp_logs"
shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_json_loads(text: str | None):
    """Safely load JSON string, returning None if invalid."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def save_file(file_path: Path, content: str, mode="w"):
    """Generic file saver."""
    if not content:
        return
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, mode, encoding="utf-8") as f:
        f.write(content)


def save_json_file(file_path: Path, data: dict | list | None):
    """Save data to a JSON file."""
    if data is None:
        return
    save_file(file_path, json.dumps(data, indent=2, ensure_ascii=False))


def parse_sse_stream(resp_body_str: str):
    """
    Parses llama.cpp SSE stream to extract:
    1. Full content text
    2. Reasoning content text (if present)
    3. Structured tool calls
    4. Final usage/timings
    """
    full_content = []
    reasoning_content = []
    tool_calls_map = {}
    final_usage = None

    if not resp_body_str:
        return "", "", [], None

    lines = resp_body_str.strip().split("\n")
    for line in lines:
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break

        chunk = safe_json_loads(data_str)
        if not chunk:
            continue

        # Check for usage/timings FIRST, before accessing choices
        if "usage" in chunk:
            final_usage = chunk["usage"]
        if "timings" in chunk:
            if final_usage is None:
                final_usage = {}
            final_usage["timings"] = chunk["timings"]

        # Skip further processing if no choices
        if "choices" not in chunk or not chunk["choices"]:
            continue

        choice = chunk["choices"][0]
        delta = choice.get("delta", {})

        if "content" in delta and delta["content"] is not None:
            full_content.append(delta["content"])
        if "reasoning_content" in delta and delta["reasoning_content"] is not None:
            reasoning_content.append(delta["reasoning_content"])
        if "tool_calls" in delta and delta["tool_calls"]:
            for tc in delta["tool_calls"]:
                idx = tc.get("index", 0)
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {
                        "id": tc.get("id"),
                        "type": tc.get("type"),
                        "name": None,
                        "arguments": "",
                    }
                func_info = tc.get("function", {})
                if "name" in func_info:
                    tool_calls_map[idx]["name"] = func_info["name"]
                if "arguments" in func_info:
                    tool_calls_map[idx]["arguments"] += func_info["arguments"]

    structured_tool_calls = []
    for tc in tool_calls_map.values():
        try:
            tc["arguments"] = json.loads(tc["arguments"])
        except json.JSONDecodeError:
            pass
        structured_tool_calls.append(tc)

    return (
        "".join(full_content),
        "".join(reasoning_content),
        structured_tool_calls,
        final_usage,
    )


def process_chat_completion(flow: http.HTTPFlow, req_dir: Path):
    """
    Parse and save llama.cpp /v1/chat/completions specific structures.
    """
    req_body_str = flow.request.get_text() if flow.request.content else None
    req_data = safe_json_loads(req_body_str)

    # Save formatted JSON if valid, otherwise save raw string as fallback
    if req_data:
        save_json_file(req_dir / "request_body" / "raw.json", req_data)
    elif req_body_str:
        # Fallback: if it's not valid JSON, save the raw string anyway
        save_file(req_dir / "request_body" / "raw.json", req_body_str)

    if req_data:
        if "tools" in req_data:
            save_json_file(req_dir / "request_body" / "tools.json", req_data["tools"])
        if "messages" in req_data and isinstance(req_data["messages"], list):
            messages_dir = req_dir / "request_body" / "messages"
            messages_dir.mkdir(parents=True, exist_ok=True)
            for i, msg in enumerate(req_data["messages"]):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if role == "assistant" and "tool_calls" in msg:
                    tool_calls_str = (
                        "\n\n**Tool Calls:**\n```json\n"
                        + json.dumps(msg["tool_calls"], indent=2)
                        + "\n```"
                    )
                    if isinstance(content, str):
                        content += tool_calls_str
                    else:
                        content = tool_calls_str
                if role == "tool":
                    tool_id = msg.get("tool_call_id", "unknown")
                    header = f"**Tool Result ID:** `{tool_id}`\n\n"
                    content = header + (
                        content if isinstance(content, str) else json.dumps(content)
                    )
                filename = f"{i + 1:02d}_{role}.md"
                save_file(messages_dir / filename, str(content))

    # --- 2. Process Response Body (SSE Parsing) ---
    resp_body_str = flow.response.get_text() if flow.response.content else None

    resp_dir = req_dir / "response_body"
    resp_dir.mkdir(parents=True, exist_ok=True)

    # Save raw stream for debugging
    if resp_body_str:
        save_file(resp_dir / "raw_stream.md", resp_body_str)

    # Parse the stream
    content, reasoning, tool_calls, usage = parse_sse_stream(resp_body_str)

    # Save derived files
    if content:
        save_file(resp_dir / "content.md", content)

    if reasoning:
        save_file(resp_dir / "reasoning_content.md", reasoning)

    if tool_calls:
        save_json_file(resp_dir / "tool_calls.json", tool_calls)

    if usage:
        save_json_file(resp_dir / "usage.json", usage)


def response(flow: http.HTTPFlow) -> None:
    """
    Main entry point for logging flows.
    """
    if flow.response is None:
        return

    # Filter for LLM endpoints
    if "/v1/chat/completions" not in flow.request.path:
        return

    # Create unique directory for this flow based on timestamp
    ts = datetime.fromtimestamp(flow.timestamp_start)
    dir_name = ts.strftime("%Y%m%d_%H%M%S_%f")
    req_dir = OUTPUT_DIR / "lines" / dir_name
    req_dir.mkdir(parents=True, exist_ok=True)

    # Calculate duration
    duration_ms = None
    if hasattr(flow.response, "timestamp_end") and flow.response.timestamp_end:
        duration_ms = (flow.response.timestamp_end - flow.timestamp_start) * 1000

    # --- Save Headers Explicitly ---
    save_json_file(req_dir / "request_headers.json", dict(flow.request.headers))
    save_json_file(req_dir / "response_headers.json", dict(flow.response.headers))

    # --- Save Flow Metadata ---
    meta_data = {
        "timestamp": flow.timestamp_start,
        "iso_timestamp": ts.isoformat(),
        "method": flow.request.method,
        "path": flow.request.path,
        "url": str(flow.request.url),
        "response_status": flow.response.status_code,
        "duration_ms": duration_ms,
        "client_host": flow.client_conn.address[0]
        if flow.client_conn.address
        else None,
        "server_host": flow.server_conn.address[0]
        if flow.server_conn and flow.server_conn.address
        else None,
    }
    save_json_file(req_dir / "metadata.json", meta_data)

    # --- Process Specific Endpoint Logic ---
    if "/v1/chat/completions" in flow.request.path:
        process_chat_completion(flow, req_dir)

    print(f"✅ Saved: {req_dir.relative_to(OUTPUT_DIR)}")
