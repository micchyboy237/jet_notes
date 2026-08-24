import logging
import os
import subprocess
import sys
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
CHECK_INTERVAL = 5  # Health check every 5 seconds
SPEED_CHECK_INTERVAL = 15  # Speed test every 15 seconds
COOLDOWN_PERIOD = 15  # Wait after applying a fix before re-checking
MAX_RETRIES = 3  # Fix attempts before pausing auto-fix
DEBUG_LOG_MIN_INTERVAL = 300  # Full debug dump at most every 5 minutes
LOG_DIR = "/Users/jethroestrada/Library/Logs"
LOG_FILE = os.path.join(LOG_DIR, "live_network_guardian.log")

# Speed test configuration
SPEED_TEST_BYTES_NORMAL = 10_000_000  # 10MB for healthy connections
SPEED_TEST_BYTES_DEGRADED = 2_000_000  # 2MB for degraded connections (adaptive)
SPEED_DEGRADED_THRESHOLD = 2.0  # Mbps threshold to trigger degraded mode + fix
SPEED_TEST_PROGRESS_INTERVAL = 0.5
SPEED_TEST_URL_TEMPLATE = "https://speed.cloudflare.com/__down?bytes={}"

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


# --- Module-level state ---
_last_health_status = None
_last_debug_log_time = 0
_last_speed_mbps = None  # Tracks last speed result for degraded detection


def require_root():
    """Exit with error if not running as root."""
    if os.geteuid() != 0:
        console.print(
            "\n[bold red]✗ Network Guardian must be run as root.[/bold red]\n"
            "[yellow]Please re-run with sudo:[/yellow]\n"
            f"[cyan]sudo python3 {os.path.abspath(__file__)}[/cyan]\n"
        )
        sys.exit(1)
    log.info("Running as root; privilege check passed")


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
    """
    Instant health check using scutil with smart debug logging.
    Distinguishes between daemon hangs and genuine interface absence.
    """
    global _last_health_status, _last_debug_log_time

    nwi = run_cmd("scutil --nwi", timeout=3)

    # Distinguish timeout/daemon hang from genuine interface absence
    if nwi == "":
        log.warning("scutil --nwi timed out or returned empty; possible daemon hang")
        _last_health_status = "Scutil Timeout"
        return False, "Scutil Timeout"

    if f"{INTERFACE} :" not in nwi:
        log.warning(f"Interface {INTERFACE} not found in NWI output")
        _last_health_status = "Interface Missing"
        return False, "Interface Missing"

    reach = run_cmd(f"scutil -r {CHECK_IP}", timeout=3)
    if "Reachable" not in reach:
        log.warning(f"IP {CHECK_IP} not reachable")
        _last_health_status = "Not Reachable"
        return False, "Not Reachable"

    dns = run_cmd("scutil --dns", timeout=3)
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


def _watch_speed_progress(tmp_path, stop_event, progress, task_id, total_bytes):
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
            continue

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
    Adaptive download speed test via curl with dual progress display.
    Uses smaller payload when recent speeds indicate degradation.
    """
    global _last_speed_mbps

    # Adaptive test size based on last known speed
    if _last_speed_mbps is not None and _last_speed_mbps < SPEED_DEGRADED_THRESHOLD:
        test_bytes = SPEED_TEST_BYTES_DEGRADED
        log.info(
            f"Using reduced test size ({test_bytes // 1_000_000}MB) due to degraded speed"
        )
    else:
        test_bytes = SPEED_TEST_BYTES_NORMAL

    url = SPEED_TEST_URL_TEMPLATE.format(test_bytes)
    log.info(f"Running speed test ({test_bytes // 1_000_000}MB from Cloudflare)...")

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
            transient=True,
        ) as progress:
            task_id = progress.add_task(
                "[cyan]Connecting...[/cyan]",
                total=test_bytes,
            )

            watcher = threading.Thread(
                target=_watch_speed_progress,
                args=(tmp_path, stop_event, progress, task_id, test_bytes),
                daemon=True,
            )
            watcher.start()
            log.debug("Speed watcher thread started")

            start_time = time.time()
            subprocess.run(
                [
                    "curl",
                    "-#",
                    "-o",
                    tmp_path,
                    "--max-time",
                    "15",
                    url,
                ],
                capture_output=False,
                timeout=20,
            )
            elapsed_total = max(time.time() - start_time, 0.1)

            stop_event.set()
            watcher.join(timeout=2)
            log.debug(
                f"Speed watcher thread stopped. Elapsed: {round(elapsed_total, 2)}s"
            )

        final_bytes = os.path.getsize(tmp_path)
        mbps = round((final_bytes * 8) / (elapsed_total * 1_000_000), 3)

        # Store speed result for degraded detection in main loop
        _last_speed_mbps = mbps

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
        _last_speed_mbps = 0.0
        log.error("Speed test timed out after 20s")
    except Exception as e:
        stop_event.set()
        _last_speed_mbps = 0.0
        log.error(f"Speed test failed: {e}")
    finally:
        try:
            os.remove(tmp_path)
            log.debug(f"Temp file cleaned up: {tmp_path}")
        except OSError as e:
            log.warning(f"Could not remove temp file {tmp_path}: {e}")


def apply_fix(issue_type):
    """
    Targeted fix with proper timeouts and verification.
    Returns True if fix was applied successfully, False otherwise.
    Note: No 'sudo' prefix needed — process runs as root via require_root().
    """
    log.warning(f"Applying targeted fix for: {issue_type}")

    if issue_type == "Scutil Timeout":
        log.info("System daemon may be hung; waiting 5s before retry...")
        time.sleep(5)
        return False  # Signal: re-check health, don't count as hardware fix attempt

    elif issue_type == "Interface Missing":
        log.info(f"Cycling power on {INTERFACE}...")
        run_cmd(f"networksetup -setairportpower {INTERFACE} off", timeout=10)
        time.sleep(3)
        run_cmd(f"networksetup -setairportpower {INTERFACE} on", timeout=10)

        # Verify recovery before returning
        for i in range(15):
            time.sleep(1)
            nwi = run_cmd("scutil --nwi", timeout=3)
            if f"{INTERFACE} :" in nwi:
                log.info(f"Interface {INTERFACE} recovered after {i + 1}s")
                return True
        log.error(f"Power cycle failed to restore {INTERFACE} after 15s")
        return False

    elif issue_type == "Not Reachable":
        log.info(f"Renewing DHCP lease on {INTERFACE}...")
        run_cmd(f"ipconfig set {INTERFACE} DHCP", timeout=10)
        return True

    elif issue_type == "DNS Missing":
        log.info("Flushing DNS cache and restarting mDNSResponder...")
        run_cmd("dscacheutil -flushcache", timeout=5)
        run_cmd("killall -HUP mDNSResponder", timeout=5)
        return True

    elif issue_type == "Speed Degraded":
        log.info("Speed degraded; renewing DHCP as lightweight first step...")
        run_cmd(f"ipconfig set {INTERFACE} DHCP", timeout=10)
        return True

    else:
        log.error(f"No fix defined for issue type: {issue_type}")
        return False


def main():
    require_root()

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
        f"cooldown={COOLDOWN_PERIOD}s, speed_threshold={SPEED_DEGRADED_THRESHOLD}Mbps, "
        f"debug_dump_interval={DEBUG_LOG_MIN_INTERVAL}s"
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

        # Health check (L3/L4 layer)
        is_healthy, status = check_health_scutil()

        # Check for speed degradation even when L3/L4 is healthy
        if (
            is_healthy
            and _last_speed_mbps is not None
            and _last_speed_mbps < SPEED_DEGRADED_THRESHOLD
        ):
            is_healthy = False
            status = "Speed Degraded"
            log.warning(
                f"L3/L4 healthy but speed degraded: {_last_speed_mbps} Mbps < {SPEED_DEGRADED_THRESHOLD} Mbps"
            )

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

                # Honor apply_fix return value
                fix_succeeded = apply_fix(status)
                last_fix_time = time.time()

                if not fix_succeeded:
                    log.warning(
                        f"Fix for '{status}' reported failure. "
                        f"Counting as attempt {consecutive_failures}/{MAX_RETRIES}."
                    )
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
