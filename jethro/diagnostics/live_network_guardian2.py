import logging
import os
import random
import re
import select
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
from collections import deque

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
INTERFACE_RECOVERY_TIMEOUT = 15

LOG_DIR = "/Users/jethroestrada/Library/Logs"
LOG_FILE = os.path.join(LOG_DIR, "live_network_guardian.log")

# Speed test configuration
SPEED_TEST_BYTES_NORMAL = 2_000_000  # 2.0MB for healthy connections
SPEED_TEST_BYTES_DEGRADED = 500_000  # 0.5MB for degraded connections (adaptive)
SPEED_DEGRADED_THRESHOLD = 0.3  # Mbps threshold to trigger degraded mode + fix
SPEED_TEST_PROGRESS_INTERVAL = 0.5
SPEED_TEST_URL_TEMPLATE = "https://speed.cloudflare.com/__down?bytes={}"
SPEED_ROLLING_WINDOW = 3  # Number of recent speed samples to average
SPEED_TEST_MIN_VALID_ELAPSED = 0.5  # Min elapsed time to consider valid (seconds)
SPEED_TEST_MAX_DURATION_SEC = 15

# ✅ IMPROVEMENT: Lowered from 3 to 2 for faster reaction to blackholes
CONSECUTIVE_ZERO_THRESHOLD = 2

# DNS validation configuration
PRIMARY_DNS = "1.1.1.1"
FALLBACK_DNS = "8.8.8.8"
DNS_QUERY_TIMEOUT = 3
# ✅ IMPROVEMENT: Test the EXACT domain curl uses, not just cloudflare.com
DNS_TEST_DOMAIN = "speed.cloudflare.com"

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
_speed_history = deque(maxlen=SPEED_ROLLING_WINDOW)
_consecutive_zero_tests = 0

_manual_speed_test_requested = False


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


def is_valid_ip(text):
    """
    ✅ NEW: Validate that text is an actual IP address, not a dig error message.
    Prevents ';; connection timed out' from being treated as a valid IP.
    """
    if not text:
        return False
    # dig errors start with ';' or contain letters other than hex
    if text.startswith(";"):
        return False
    # Basic IPv4 validation
    ipv4_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    # Basic IPv6 validation (simplified)
    ipv6_pattern = r"^[0-9a-fA-F:]+$"
    return bool(re.match(ipv4_pattern, text)) or bool(re.match(ipv6_pattern, text))


def get_average_speed():
    """Returns rolling average of last N valid speed samples, or None if no data."""
    if not _speed_history:
        return None
    avg = round(sum(_speed_history) / len(_speed_history), 3)
    log.debug(
        f"Rolling avg speed: {avg} Mbps over {len(_speed_history)} sample(s) "
        f"| History: {list(_speed_history)}"
    )
    return avg


def check_health_scutil():
    """
    Instant health check using scutil with smart debug logging.
    Includes live DNS query validation targeting the exact speed test domain.
    """
    global _last_health_status, _last_debug_log_time

    nwi = run_cmd("scutil --nwi", timeout=3)

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

    # ✅ IMPROVEMENT: Force IPv4 (-4) and test exact speed test domain
    # This prevents AAAA timeout masking and catches domain-specific failures
    dns_test = run_cmd(
        f"dig +short -4 +time={DNS_QUERY_TIMEOUT} +tries=1 "
        f"{DNS_TEST_DOMAIN} @{PRIMARY_DNS}",
        timeout=5,
    )

    # ✅ IMPROVEMENT: Validate output is an actual IP, not an error string
    if not dns_test or not is_valid_ip(dns_test):
        log.warning(
            f"Primary DNS {PRIMARY_DNS} configured but cannot resolve "
            f"{DNS_TEST_DOMAIN} (output: '{dns_test[:60] if dns_test else 'empty'}')"
        )
        _last_health_status = "DNS Unresponsive"
        return False, "DNS Unresponsive"

    current_status = "Healthy"
    now = time.time()

    if current_status != _last_health_status or (
        now - _last_debug_log_time > DEBUG_LOG_MIN_INTERVAL
    ):
        log.debug("Running scutil health check...")
        log.debug(f"NWI Output:\n{nwi}")
        log.debug(f"Reachability ({CHECK_IP}): {reach}")
        log.debug(f"DNS Output:\n{dns}")
        log.debug(
            f"Live DNS query test ({DNS_TEST_DOMAIN}@{PRIMARY_DNS}): OK ({dns_test})"
        )
        log.debug("All scutil health checks passed")
        _last_debug_log_time = now

    _last_health_status = current_status
    return True, current_status


def _watch_speed_progress(tmp_path, stop_event, progress, task_id, total_bytes):
    """Background thread: polls temp file size and updates Rich Progress bar."""
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
    Tracks consecutive zero-byte failures separately from rolling average.
    Includes validated IP-direct retry when DNS resolution fails.
    """
    global _consecutive_zero_tests

    avg_speed = get_average_speed()

    if avg_speed is not None and avg_speed < SPEED_DEGRADED_THRESHOLD:
        test_bytes = SPEED_TEST_BYTES_DEGRADED
        log.info(
            f"Using reduced test size ({test_bytes // 1_000_000}MB) "
            f"due to degraded rolling avg: {avg_speed} Mbps"
        )
    else:
        test_bytes = SPEED_TEST_BYTES_NORMAL

    nocache = random.randint(1, 999999)
    url = SPEED_TEST_URL_TEMPLATE.format(test_bytes) + f"&nocache={nocache}"
    log.info(f"Running speed test ({test_bytes // 1_000_000}MB from Cloudflare)...")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".speedtest")
    tmp_path = tmp_file.name
    tmp_file.close()

    stop_event = threading.Event()
    mbps = 0.0
    final_bytes = 0
    elapsed_total = 0.0
    test_valid = True
    curl_stderr = ""

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
            result = subprocess.run(
                [
                    "curl",
                    "-#",
                    "-o",
                    tmp_path,
                    "--max-time",
                    str(SPEED_TEST_MAX_DURATION_SEC),
                    "-H",
                    "Cache-Control: no-cache, no-store, must-revalidate",
                    "-H",
                    "Pragma: no-cache",
                    "--no-sessionid",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            curl_stderr = result.stderr
            elapsed_total = max(time.time() - start_time, 0.001)

            stop_event.set()
            watcher.join(timeout=2)
            log.debug(
                f"Speed watcher thread stopped. Elapsed: {round(elapsed_total, 2)}s"
            )

        final_bytes = os.path.getsize(tmp_path)

        if final_bytes == 0:
            log.warning(
                "Speed test completed but temp file is empty (0 bytes). "
                "Likely cached response or connection failure. Discarding sample."
            )
            _consecutive_zero_tests += 1
            test_valid = False

            # ✅ IMPROVEMENT: Validated IP-direct retry diagnostic
            if (
                "Resolving timed out" in curl_stderr
                or "Could not resolve host" in curl_stderr
            ):
                log.warning(
                    "DNS resolution failed; retrying with IP-direct to isolate issue..."
                )
                ip_resolve = run_cmd(
                    f"dig +short -4 +time={DNS_QUERY_TIMEOUT} +tries=1 "
                    f"speed.cloudflare.com @{FALLBACK_DNS}",
                    timeout=5,
                )

                # ✅ FIX: Only proceed if we got a VALID IP address
                if is_valid_ip(ip_resolve):
                    log.info(
                        f"Resolved via fallback DNS: {ip_resolve}; testing IP-direct"
                    )
                    ip_result = subprocess.run(
                        [
                            "curl",
                            "-s",
                            "-o",
                            "/dev/null",
                            "-w",
                            "%{http_code}",
                            "--max-time",
                            str(SPEED_TEST_MAX_DURATION_SEC),
                            "-H",
                            "Host: speed.cloudflare.com",
                            "--resolve",
                            f"speed.cloudflare.com:443:{ip_resolve}",
                            f"https://speed.cloudflare.com/__down?bytes=1000&nocache={nocache}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    if ip_result.returncode == 0 and ip_result.stdout.strip() == "200":
                        log.info(
                            "✅ IP-direct succeeded: Issue confirmed as DNS-only. "
                            "Primary resolver is non-functional."
                        )
                    else:
                        log.warning(
                            f"❌ IP-direct also failed (HTTP: {ip_result.stdout.strip()}, "
                            f"rc: {ip_result.returncode}): True connectivity blackhole."
                        )
                else:
                    log.warning(
                        f"Fallback DNS ({FALLBACK_DNS}) also failed to resolve "
                        f"(output: '{ip_resolve[:60] if ip_resolve else 'empty'}'); "
                        "likely full connectivity loss."
                    )

        elif elapsed_total < SPEED_TEST_MIN_VALID_ELAPSED:
            log.warning(
                f"Suspiciously fast completion ({elapsed_total:.3f}s for "
                f"{final_bytes} bytes). Likely cached response. Discarding sample."
            )
            _consecutive_zero_tests += 1
            test_valid = False
        else:
            _consecutive_zero_tests = 0
            mbps = round((final_bytes * 8) / (elapsed_total * 1_000_000), 3)

        if test_valid:
            _speed_history.append(mbps)
            log.debug(f"Speed history updated: {list(_speed_history)}")
        else:
            log.debug(
                f"Invalid speed test discarded. History unchanged: {list(_speed_history)} "
                f"| Consecutive zeros: {_consecutive_zero_tests}"
            )

        table = Table(title="Speed Test Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Downloaded", f"{round(final_bytes / 1_000_000, 2)} MB")
        table.add_row("Elapsed", f"{round(elapsed_total, 2)}s")
        if test_valid:
            table.add_row("Avg Download Speed", f"{mbps} Mbps")
        else:
            table.add_row("Avg Download Speed", "[red]DISCARDED (cached/invalid)[/red]")
        table.add_row(
            f"Rolling Avg (last {len(_speed_history)})",
            f"{get_average_speed()} Mbps",
        )
        table.add_row(
            "Consecutive Zeros",
            f"{_consecutive_zero_tests}/{CONSECUTIVE_ZERO_THRESHOLD}",
        )
        console.print(table)

        if test_valid:
            log.info(
                f"Speed Result: DL={mbps} Mbps | "
                f"{round(final_bytes / 1_000_000, 2)} MB in {round(elapsed_total, 2)}s | "
                f"Rolling avg={get_average_speed()} Mbps"
            )
        else:
            log.warning(
                f"Speed Result: DISCARDED | "
                f"{round(final_bytes / 1_000_000, 2)} MB in {round(elapsed_total, 2)}s | "
                f"Rolling avg={get_average_speed()} Mbps (unchanged) | "
                f"Consecutive zeros: {_consecutive_zero_tests}"
            )

    except subprocess.TimeoutExpired:
        stop_event.set()
        _consecutive_zero_tests += 1
        log.warning(
            f"Speed test timed out; consecutive zeros: {_consecutive_zero_tests}"
        )
    except Exception as e:
        stop_event.set()
        _consecutive_zero_tests += 1
        log.warning(
            f"Speed test failed: {e}; consecutive zeros: {_consecutive_zero_tests}"
        )
    finally:
        try:
            os.remove(tmp_path)
            log.debug(f"Temp file cleaned up: {tmp_path}")
        except OSError as e:
            log.warning(f"Could not remove temp file {tmp_path}: {e}")


def apply_fix(issue_type):
    """
    Targeted fix matching proven manual workflow:
    1. Flush DNS cache + restart mDNSResponder
    2. Renew DHCP (only if dynamic, skip if static)
    3. Power cycle WiFi on CORRECT interface
    4. Poll for recovery instead of blind sleep
    """
    global _consecutive_zero_tests

    log.warning(f"Applying targeted fix for: {issue_type}")

    # ✅ Step 1: Universal DNS flush (matches your manual killall -HUP mDNSResponder)
    log.info("Step 1/3: Flushing DNS cache and restarting mDNSResponder...")
    run_cmd("dscacheutil -flushcache", timeout=5)
    run_cmd("killall -HUP mDNSResponder", timeout=5)

    if issue_type == "Scutil Timeout":
        log.info("System daemon may be hung; waiting 5s before retry...")
        time.sleep(5)
        return False

    elif issue_type == "DNS Unresponsive":
        log.info(f"Testing fallback DNS ({FALLBACK_DNS})...")
        fallback_test = run_cmd(
            f"dig +short -4 +time={DNS_QUERY_TIMEOUT} +tries=1 "
            f"google.com @{FALLBACK_DNS}",
            timeout=5,
        )
        if fallback_test and is_valid_ip(fallback_test):
            log.info(
                f"Fallback DNS ({FALLBACK_DNS}) responding; "
                "re-flushing local cache to pick up changes"
            )
            run_cmd("dscacheutil -flushcache", timeout=5)
            run_cmd("killall -HUP mDNSResponder", timeout=5)
            return True
        else:
            log.warning(
                "Both primary and fallback DNS unresponsive; "
                "falling through to full interface reset"
            )
            # Fall through to interface power cycle below

    # ✅ Unified interface reset for all connectivity issues
    # This handles: Interface Missing, Speed Degraded, Connected No Data,
    # Not Reachable, DNS Unresponsive (fallback failed), DNS Missing
    if issue_type in (
        "Interface Missing",
        "Speed Degraded",
        "Connected No Data",
        "Not Reachable",
        "DNS Unresponsive",
        "DNS Missing",
    ):
        # ✅ Step 2: Safe DHCP renewal (skips if static IP)
        # Unlike your manual command that blindly ran on en0, this checks first
        dhcp_status = run_cmd(f"ipconfig getpacket {INTERFACE}", timeout=5)
        if dhcp_status:
            log.info(f"Step 2/3: Renewing DHCP lease on {INTERFACE}...")
            run_cmd(f"ipconfig set {INTERFACE} DHCP", timeout=10)
            time.sleep(2)
        else:
            log.info(
                f"Step 2/3: Static IP detected on {INTERFACE}; "
                "skipping DHCP renewal (would break connection)"
            )

        # ✅ Step 3: Power cycle on CORRECT interface with polling
        # Unlike your manual 'sleep 10', this recovers as soon as ready
        log.info(f"Step 3/3: Power cycling {INTERFACE}...")
        run_cmd(f"networksetup -setairportpower {INTERFACE} off", timeout=10)
        time.sleep(3)  # Brief pause for hardware to fully power down
        run_cmd(f"networksetup -setairportpower {INTERFACE} on", timeout=10)

        # ✅ Poll for recovery instead of blind sleep 10
        for i in range(INTERFACE_RECOVERY_TIMEOUT):
            time.sleep(1)
            nwi = run_cmd("scutil --nwi", timeout=3)
            if f"{INTERFACE} :" in nwi:
                log.info(f"Interface {INTERFACE} recovered after {i + 1}s")
                _consecutive_zero_tests = 0
                return True

        log.error(
            f"Power cycle failed to restore {INTERFACE} "
            f"after {INTERFACE_RECOVERY_TIMEOUT}s"
        )
        return False

    else:
        log.error(f"No fix defined for issue type: {issue_type}")
        return False


def _input_listener(stop_event):
    """Non-blocking keyboard listener thread for manual speed test trigger."""
    global _manual_speed_test_requested

    try:
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
    except (termios.error, ValueError):
        log.debug("Stdin is not a TTY; keyboard listener disabled")
        return

    try:
        while not stop_event.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
            if ready:
                try:
                    ch = sys.stdin.read(1)
                    if ch.lower() == "r":
                        _manual_speed_test_requested = True
                        console.print(
                            "\n[bold yellow]⌨ 'r' pressed — triggering manual speed test...[/bold yellow]"
                        )
                        log.info("Manual speed test requested via keyboard")
                except Exception:
                    pass
    finally:
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


def main():
    global _manual_speed_test_requested

    require_root()

    console.print(
        Panel.fit(
            "[bold blue]Network Guardian Fast[/bold blue]\nReal-time scutil monitoring\n[dim]Press 'r' for manual speed test[/dim]",
            border_style="blue",
        )
    )
    log.info("Network Guardian started")
    log.debug(
        f"Config: interface={INTERFACE}, check_ip={CHECK_IP}, "
        f"interval={CHECK_INTERVAL}s, speed_interval={SPEED_CHECK_INTERVAL}s, "
        f"cooldown={COOLDOWN_PERIOD}s, speed_threshold={SPEED_DEGRADED_THRESHOLD}Mbps, "
        f"speed_rolling_window={SPEED_ROLLING_WINDOW}, "
        f"min_valid_elapsed={SPEED_TEST_MIN_VALID_ELAPSED}s, "
        f"consecutive_zero_threshold={CONSECUTIVE_ZERO_THRESHOLD}, "
        f"primary_dns={PRIMARY_DNS}, fallback_dns={FALLBACK_DNS}, "
        f"dns_test_domain={DNS_TEST_DOMAIN}, "
        f"debug_dump_interval={DEBUG_LOG_MIN_INTERVAL}s"
    )

    input_stop_event = threading.Event()
    input_thread = threading.Thread(
        target=_input_listener,
        args=(input_stop_event,),
        daemon=True,
        name="KeyboardListener",
    )
    input_thread.start()
    log.debug("Keyboard listener thread started")

    consecutive_failures = 0
    auto_fix_paused = False
    last_fix_time = 0
    last_speed_check = 0

    try:
        while True:
            current_time = time.time()

            if current_time - last_fix_time < COOLDOWN_PERIOD:
                remaining = int(COOLDOWN_PERIOD - (current_time - last_fix_time))
                console.print(f"[dim]Stabilizing... {remaining}s[/dim]", end="\r")
                time.sleep(1)
                continue

            if _manual_speed_test_requested:
                _manual_speed_test_requested = False
                log.info("Executing manual speed test (triggered by 'r' key)")
                check_speed_live()
                last_speed_check = time.time()
            else:
                time_since_last_speed = current_time - last_speed_check
                if time_since_last_speed >= SPEED_CHECK_INTERVAL:
                    check_speed_live()
                    last_speed_check = time.time()
                else:
                    remaining = int(SPEED_CHECK_INTERVAL - time_since_last_speed)
                    console.print(
                        f"[dim]Next speed test in: {remaining}s | Press 'r' for manual[/dim]      ",
                        end="\r",
                    )

            # Health check (L3/L4 layer + live DNS validation)
            is_healthy, status = check_health_scutil()

            # ✅ Check for connectivity blackhole BEFORE speed degradation
            # Threshold lowered to 2 for faster reaction
            if is_healthy and _consecutive_zero_tests >= CONSECUTIVE_ZERO_THRESHOLD:
                is_healthy = False
                status = "Connected No Data"
                log.warning(
                    f"L3/L4 healthy but {_consecutive_zero_tests} consecutive speed tests "
                    f"returned 0 bytes. Connectivity blackhole detected."
                )

            elif is_healthy:
                avg_speed = get_average_speed()
                if avg_speed is not None and avg_speed < SPEED_DEGRADED_THRESHOLD:
                    is_healthy = False
                    status = "Speed Degraded"
                    log.warning(
                        f"L3/L4 healthy but rolling avg speed degraded: "
                        f"{avg_speed} Mbps (window={len(_speed_history)}) "
                        f"< {SPEED_DEGRADED_THRESHOLD} Mbps"
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

    finally:
        input_stop_event.set()
        input_thread.join(timeout=2)
        log.debug("Keyboard listener thread stopped")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Guardian stopped by user.[/bold yellow]")
        log.info("Guardian stopped by user (KeyboardInterrupt)")
