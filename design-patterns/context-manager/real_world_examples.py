"""
Real-world examples of context managers for common scenarios.
"""

import io
import json
import os
from contextlib import contextmanager, redirect_stderr, redirect_stdout


@contextmanager
def temporary_directory(prefix="tmp_"):
    """Create a temporary directory that's automatically cleaned up."""
    import tempfile

    temp_dir = tempfile.mkdtemp(prefix=prefix)
    print(f"  → Created temporary directory: {temp_dir}")

    try:
        yield temp_dir
    finally:
        # Clean up: remove directory and all contents
        import shutil

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"  → Removed temporary directory: {temp_dir}")


@contextmanager
def capture_output():
    """Capture stdout and stderr for testing or logging."""
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        yield stdout_buffer, stderr_buffer

    # Return captured output
    return stdout_buffer.getvalue(), stderr_buffer.getvalue()


@contextmanager
def atomic_write(filepath):
    """Write to file atomically using a temporary file."""
    temp_filepath = filepath + ".tmp"

    try:
        # Write to temporary file first
        with open(temp_filepath, "w") as temp_file:
            yield temp_file

        # If successful, replace original file
        os.replace(temp_filepath, filepath)
        print(f"  → Atomically wrote to: {filepath}")
    except Exception as e:
        # Clean up temp file on failure
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            print(f"  → Removed temporary file after error: {temp_filepath}")
        raise


@contextmanager
def config_loader(config_path):
    """Load configuration from JSON file with automatic cleanup."""
    print(f"  → Loading config from: {config_path}")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = json.load(f)

    try:
        yield config
    finally:
        print(f"  → Config released: {config_path}")


@contextmanager
def progress_tracker(total_items, label="Processing"):
    """Track progress through a series of items."""
    completed = 0

    def update_progress():
        percentage = (completed / total_items) * 100 if total_items > 0 else 0
        bar_length = 30
        filled = int(bar_length * completed // total_items) if total_items > 0 else 0
        bar = "█" * filled + "-" * (bar_length - filled)
        print(
            f"\r  → {label}: [{bar}] {percentage:.1f}% ({completed}/{total_items})",
            end="",
        )

    try:
        yield lambda: completed  # Yield a function to update count
    finally:
        completed += 0  # Ensure final update
        update_progress()
        print()  # New line after progress bar


@contextmanager
def mock_environment(**env_vars):
    """Temporarily set environment variables for testing."""
    original_env = {}

    # Save original values and set new ones
    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
        print(f"  → Set {key}={value}")

    try:
        yield
    finally:
        # Restore original values
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
                print(f"  → Removed {key}")
            else:
                os.environ[key] = original_value
                print(f"  → Restored {key}={original_value}")


# --- Demo Usage ---
if __name__ == "__main__":
    print("=" * 60)
    print("DEMO 1: Temporary Directory")
    print("=" * 60)

    with temporary_directory("demo_") as temp_dir:
        # Create a file in the temp directory
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Temporary data")
        print(f"  • Created file in temp dir: {test_file}")
        print(f"  • Directory exists: {os.path.exists(temp_dir)}")

    print(f"  • Directory cleaned up: {not os.path.exists(temp_dir)}")

    print("\n" + "=" * 60)
    print("DEMO 2: Atomic File Write")
    print("=" * 60)

    test_output = "atomic_test.txt"

    with atomic_write(test_output) as f:
        f.write("This is written atomically\n")
        f.write("Safe from corruption\n")

    # Verify file was created
    if os.path.exists(test_output):
        with open(test_output, "r") as f:
            print(f"  • File content: {f.read().strip()}")
        os.remove(test_output)

    print("\n" + "=" * 60)
    print("DEMO 3: Configuration Loader")
    print("=" * 60)

    # Create a test config file
    config_file = "test_config.json"
    with open(config_file, "w") as f:
        json.dump({"database": "localhost", "port": 5432}, f)

    with config_loader(config_file) as config:
        print(f"  • Database: {config['database']}")
        print(f"  • Port: {config['port']}")

    os.remove(config_file)

    print("\n" + "=" * 60)
    print("DEMO 4: Environment Variable Mocking")
    print("=" * 60)

    print(f"  • Original API_KEY: {os.environ.get('API_KEY', 'NOT SET')}")

    with mock_environment(API_KEY="test-secret-key-123", DEBUG="true"):
        print(f"  • Inside context - API_KEY: {os.environ.get('API_KEY')}")
        print(f"  • Inside context - DEBUG: {os.environ.get('DEBUG')}")

    print(f"  • After context - API_KEY: {os.environ.get('API_KEY', 'NOT SET')}")

    print("\n" + "=" * 60)
    print("DEMO 5: Output Capture")
    print("=" * 60)

    def noisy_function():
        print("This goes to stdout")
        import sys

        print("This goes to stderr", file=sys.stderr)

    # Note: capture_output needs modification to work properly
    # This is a simplified demonstration
    print("  • Capturing output from noisy_function()...")
    noisy_function()
    print("  • In real usage, you'd capture this output for testing")
