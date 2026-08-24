import logging
import os
import subprocess
import tempfile
import threading
import time

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

# --- Configuration ---
INTERFACE = "en1"
CHECK_IP = "8.8.8.8"
CHECK_INTERVAL = 5  # How often to run health check (seconds)
SPEED_CHECK_INTERVAL = 15  # Speed test every 15 seconds
COOLDOWN_PERIOD = 5  # Wait after applying a fix before re-checking
MAX_RETRIES = 3  # Fix attempts before pausing auto-fix
DEBUG_LOG_MIN_INTERVAL = 300  # Full debug dump at most every 5 minutes
LOG_DIR = "/Users/jethroestrada/Library/Logs"
LOG_FILE = os.path.join(LOG_DIR, "live_network_guardian.log")
SPEED_TEST_BYTES = 10_000_000  # 10MB download size
SPEED_TEST_PROGRESS_INTERVAL = 0.5  # How often to refresh live Mbps (seconds)
SPEED_TEST_URL = f"https://speed.cloudflare.com/__down?bytes={SPEED_TEST_BYTES}"

os.makedirs(LOG_DIR, exist_ok=True)

# --- Logging Setup ---
console = Console()
log = logging.getLogger("LiveNetworkGuardian")
log.setLevel(logging.DEBUG)

if not log.handlers:
    rich_handler = RichHandler(
        rich_tracebacks=True,
        console=console,
        show_time=False,
        markup=True,
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(rich_handler)

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    log.addHandler(file_handler)


# --- Module-level state for smart debug logging ---
_last_health_status = None
_last_debug_log_time = 0


def run_cmd(cmd, timeout=2):
    """Run a shell command safely. Returns stdout only; does NOT auto-log output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.stderr.strip():
            log.warning(f"Stderr from '{cmd}': {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.error(f"Command timed out after {timeout}s: {cmd}")
        return ""
    except Exception as e:
        log.error(f"Command failed: {cmd} | Exception: {e}")
        return ""


def check_health_scutil():
    """Instant health check using scutil with smart debug logging."""
    global _last_health_status, _last_debug_log_time

    nwi = run_cmd("scutil --nwi", timeout=1)
    if f"{INTERFACE} :" not in nwi:
        log.warning(f"Interface {INTERFACE} not found in NWI output")
        _last_health_status = "Interface Missing"
        return False, "Interface Missing"

    reach = run_cmd(f"scutil -r {CHECK_IP}", timeout=1)
    if "Reachable" not in reach:
        log.warning(f"IP {CHECK_IP} not reachable")
        _last_health_status = "Not Reachable"
        return False, "Not Reachable"

    dns = run_cmd("scutil --dns", timeout=1)
    if "resolver #1" in dns:
        resolver_block = dns.split("resolver #1")[1].split("resolver #2")[0]
        if "nameserver[0]" not in resolver_block:
            log.warning("Primary DNS resolver has no nameserver configured")
            _last_health_status = "DNS Missing"
            return False, "DNS Missing"
    else:
        log.warning("No DNS resolvers found in scutil output")
        _last_health_status = "DNS Missing"
        return False, "DNS Missing"

    current_status = "Healthy"
    now = time.time()

    # Only dump full debug on state change or periodic interval
    if current_status != _last_health_status or (
        now - _last_debug_log_time > DEBUG_LOG_MIN_INTERVAL
    ):
        log.debug("Running scutil health check...")
        log.debug(f"NWI Output:\n{nwi}")
        log.debug(f"Reachability ({CHECK_IP}): {reach}")
        log.debug(f"DNS Output:\n{dns}")
        log.debug("All scutil health checks passed")
        _last_debug_log_time = now

    _last_health_status = current_status
    return True, current_status


def _watch_speed_progress(tmp_path, stop_event, progress, task_id):
    """
    Background thread: polls temp file size every SPEED_TEST_PROGRESS_INTERVAL seconds,
    updates Rich Progress bar with live Mbps reading.
    """
    last_bytes = 0
    last_time = time.time()

    while not stop_event.is_set():
        time.sleep(SPEED_TEST_PROGRESS_INTERVAL)
        try:
            current_bytes = os.path.getsize(tmp_path)
        except OSError:
            continue  # File not ready yet, skip this tick

        now = time.time()
        elapsed = now - last_time
        delta_bytes = current_bytes - last_bytes

        if elapsed > 0 and delta_bytes >= 0:
            mbps = round((delta_bytes * 8) / (elapsed * 1_000_000), 2)
            progress.update(
                task_id,
                completed=current_bytes,
                description=f"[cyan]Downloading[/cyan] [green]{mbps} Mbps[/green]",
            )
            log.debug(
                f"Live speed snapshot: {mbps} Mbps ({current_bytes // 1000} KB downloaded)"
            )

        last_bytes = current_bytes
        last_time = now


def check_speed_live():
    """
    Run a download speed test via curl with two simultaneous progress displays:
      A) curl's built-in ASCII progress bar (-#) printed to terminal
      B) Rich Progress bar showing live Mbps updated by a background watcher thread
    Final result is shown in a Rich Table with accurate elapsed time.
    """
    log.info(
        f"Running speed test ({SPEED_TEST_BYTES // 1_000_000}MB from Cloudflare)..."
    )

    # Write to a temp file so the watcher thread can poll its growing size
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".speedtest")
    tmp_path = tmp_file.name
    tmp_file.close()

    stop_event = threading.Event()

    try:
        with Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,  # Clears the Rich bar after test completes
        ) as progress:
            task_id = progress.add_task(
                "[cyan]Connecting...[/cyan]",
                total=SPEED_TEST_BYTES,
            )

            # B: Start background thread to update Rich Progress with live Mbps
            watcher = threading.Thread(
                target=_watch_speed_progress,
                args=(tmp_path, stop_event, progress, task_id),
                daemon=True,
            )
            watcher.start()
            log.debug("Speed watcher thread started")

            # A: curl with -# ASCII progress bar; writes download to temp file
            start_time = time.time()
            subprocess.run(
                [
                    "curl",
                    "-#",  # A: ASCII progress bar in terminal
                    "-o",
                    tmp_path,  # Write to temp file (enables watcher polling)
                    "--max-time",
                    "15",
                    SPEED_TEST_URL,
                ],
                capture_output=False,  # Allow curl's -# bar to print to terminal
                timeout=20,
            )
            elapsed_total = max(time.time() - start_time, 0.1)  # Avoid divide-by-zero

            # Signal watcher to stop and wait for clean exit
            stop_event.set()
            watcher.join(timeout=2)
            log.debug(
                f"Speed watcher thread stopped. Elapsed: {round(elapsed_total, 2)}s"
            )

        # Calculate final average speed from actual elapsed time
        final_bytes = os.path.getsize(tmp_path)
        mbps = round((final_bytes * 8) / (elapsed_total * 1_000_000), 3)

        table = Table(title="Speed Test Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Downloaded", f"{round(final_bytes / 1_000_000, 2)} MB")
        table.add_row("Elapsed", f"{round(elapsed_total, 2)}s")
        table.add_row("Avg Download Speed", f"{mbps} Mbps")
        console.print(table)

        log.info(
            f"Speed Result: DL={mbps} Mbps | "
            f"{round(final_bytes / 1_000_000, 2)} MB in {round(elapsed_total, 2)}s"
        )

    except subprocess.TimeoutExpired:
        stop_event.set()
        log.error("Speed test timed out after 20s")
    except Exception as e:
        stop_event.set()
        log.error(f"Speed test failed: {e}")
    finally:
        # Always clean up temp file
        try:
            os.remove(tmp_path)
            log.debug(f"Temp file cleaned up: {tmp_path}")
        except OSError as e:
            log.warning(f"Could not remove temp file {tmp_path}: {e}")


def apply_fix(issue_type):
    """Apply corrective action for detected network issues."""
    log.warning(f"Applying fix for: {issue_type}")
    if issue_type == "Interface Missing":
        log.info(f"Cycling power on {INTERFACE}...")
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} off")
        time.sleep(3)
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} on")
    elif issue_type == "Not Reachable":
        log.info(f"Renewing DHCP lease on {INTERFACE}...")
        run_cmd(f"sudo ipconfig set {INTERFACE} DHCP")
    elif issue_type == "DNS Missing":
        log.info("Flushing DNS cache and restarting mDNSResponder...")
        run_cmd("sudo dscacheutil -flushcache")
        run_cmd("sudo killall -HUP mDNSResponder")
    else:
        log.error(f"No fix defined for issue type: {issue_type}")


def main():
    console.print(
        Panel.fit(
            "[bold blue]Network Guardian Fast[/bold blue]\nReal-time scutil monitoring",
            border_style="blue",
        )
    )
    log.info("Network Guardian started")
    log.debug(
        f"Config: interface={INTERFACE}, check_ip={CHECK_IP}, "
        f"interval={CHECK_INTERVAL}s, speed_interval={SPEED_CHECK_INTERVAL}s, "
        f"cooldown={COOLDOWN_PERIOD}s, debug_dump_interval={DEBUG_LOG_MIN_INTERVAL}s"
    )

    consecutive_failures = 0
    auto_fix_paused = False
    last_fix_time = 0
    last_speed_check = 0

    while True:
        current_time = time.time()

        # Cooldown period after applying a fix
        if current_time - last_fix_time < COOLDOWN_PERIOD:
            remaining = int(COOLDOWN_PERIOD - (current_time - last_fix_time))
            console.print(f"[dim]Stabilizing... {remaining}s[/dim]", end="\r")
            time.sleep(1)
            continue

        # Periodic speed test
        if current_time - last_speed_check > SPEED_CHECK_INTERVAL:
            check_speed_live()
            last_speed_check = current_time

        # Health check
        is_healthy, status = check_health_scutil()

        if is_healthy:
            console.print("[green]✓[/green] Network Healthy", end="\r")
            if consecutive_failures > 0 or auto_fix_paused:
                log.info(
                    f"Network recovered after {consecutive_failures} failure(s). "
                    "Resuming auto-fix."
                )
            consecutive_failures = 0
            auto_fix_paused = False
        else:
            console.print(f"\n[red]✗[/red] {status}")
            log.warning(f"Health check failed: {status}")
            consecutive_failures += 1

            if auto_fix_paused:
                log.error(
                    f"Auto-fix paused. Still seeing '{status}'. "
                    "Manual intervention required. Will resume once network recovers."
                )
            elif consecutive_failures <= MAX_RETRIES:
                log.info(
                    f"Attempt {consecutive_failures}/{MAX_RETRIES} to fix '{status}'"
                )
                apply_fix(status)
                last_fix_time = time.time()
            else:
                log.error(
                    f"Max retries ({MAX_RETRIES}) reached for '{status}'. "
                    "Pausing auto-fix until network recovers. Manual intervention required."
                )
                auto_fix_paused = True

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Guardian stopped by user.[/bold yellow]")
        log.info("Guardian stopped by user (KeyboardInterrupt)")
