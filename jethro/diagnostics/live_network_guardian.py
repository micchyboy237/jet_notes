import json
import logging
import os
import subprocess
import time

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

# --- Configuration ---
INTERFACE = "en1"
CHECK_IP = "8.8.8.8"
CHECK_INTERVAL = 5
SPEED_CHECK_INTERVAL = 600
COOLDOWN_PERIOD = 60
MAX_RETRIES = 3
DEBUG_LOG_MIN_INTERVAL = 300  # Full debug dump at most every 5 minutes
LOG_DIR = "/Users/jethroestrada/Library/Logs"
LOG_FILE = os.path.join(LOG_DIR, "live_network_guardian.log")
APPLE_CDN_URL = "https://mensura.cdn-apple.com/.well-known/nq"
FALLBACK_TEST_URL = "https://speed.cloudflare.com/__down?bytes=10000000"

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


def _check_speed_apple():
    """Attempt speed test via networkQuality JSON mode. Returns True on success."""
    try:
        result = subprocess.run(
            ["networkQuality", "-s", "-c"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            log.warning(
                f"networkQuality failed: rc={result.returncode}, stderr={result.stderr.strip()[:200]}"
            )
            return False

        data = json.loads(result.stdout)
        dl_mbps = round(data.get("dl_throughput", 0) / 1_000_000, 3)
        ul_mbps = round(data.get("ul_throughput", 0) / 1_000_000, 3)
        dl_rpm = data.get("dl_responsiveness", {}).get("rpm", 0)
        ul_rpm = data.get("ul_responsiveness", {}).get("rpm", 0)

        table = Table(title="Speed Test Results (Apple)")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Download", f"{dl_mbps} Mbps ({dl_rpm} RPM)")
        table.add_row("Upload", f"{ul_mbps} Mbps ({ul_rpm} RPM)")
        console.print(table)

        log.info(
            f"Speed Results: DL={dl_mbps} Mbps, UL={ul_mbps} Mbps, "
            f"DL_RPM={dl_rpm}, UL_RPM={ul_rpm}"
        )
        return True

    except subprocess.TimeoutExpired:
        log.warning("networkQuality timed out after 30s")
        return False
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse failed: {e}")
        return False
    except Exception as e:
        log.warning(f"networkQuality exception: {e}")
        return False


def _check_speed_fallback():
    """Fallback download-only speed test via curl."""
    log.info(f"Running fallback download test from {FALLBACK_TEST_URL}")
    try:
        result = subprocess.run(
            [
                "curl",
                "-o",
                "/dev/null",
                "-s",
                "-w",
                "%{speed_download}",
                "--max-time",
                "15",
                FALLBACK_TEST_URL,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        speed_bytes = float(result.stdout.strip())
        mbps = round(speed_bytes * 8 / 1_000_000, 3)

        table = Table(title="Fallback Speed Test (Download Only)")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")
        table.add_row("Download", f"{mbps} Mbps")
        console.print(table)

        log.info(f"Fallback Speed Result: DL={mbps} Mbps")

    except ValueError:
        log.error(f"Could not parse fallback speed value: '{result.stdout.strip()}'")
    except subprocess.TimeoutExpired:
        log.error("Fallback speed test timed out")
    except Exception as e:
        log.error(f"Fallback speed test failed: {e}")


def _is_apple_cdn_reachable():
    """Quick pre-check for Apple CDN availability."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--max-time",
                "5",
                APPLE_CDN_URL,
            ],
            capture_output=True,
            text=True,
            timeout=7,
        )
        return result.returncode == 0 and result.stdout.strip() == "200"
    except Exception:
        return False


def check_speed_live():
    """Run speed test with CDN pre-check and guaranteed fallback."""
    log.info("Running live speed test...")

    if _is_apple_cdn_reachable():
        log.debug("Apple CDN reachable, using networkQuality")
        if _check_speed_apple():
            return  # Success, done
        log.warning("Apple CDN was reachable but networkQuality failed, falling back")
    else:
        log.info("Apple CDN unreachable (pre-check), skipping networkQuality")

    # Guaranteed fallback
    _check_speed_fallback()


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
        f"debug_dump_interval={DEBUG_LOG_MIN_INTERVAL}s"
    )

    consecutive_failures = 0
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
            consecutive_failures = 0
        else:
            console.print(f"\n[red]✗[/red] {status}")
            log.warning(f"Health check failed: {status}")
            consecutive_failures += 1

            if consecutive_failures <= MAX_RETRIES:
                log.info(
                    f"Attempt {consecutive_failures}/{MAX_RETRIES} to fix '{status}'"
                )
                apply_fix(status)
                last_fix_time = time.time()
            else:
                log.error(
                    f"Max retries ({MAX_RETRIES}) reached for '{status}'. "
                    "Manual intervention required."
                )
                consecutive_failures = 0

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Guardian stopped by user.[/bold yellow]")
        log.info("Guardian stopped by user (KeyboardInterrupt)")
