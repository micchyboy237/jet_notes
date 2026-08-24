import logging
import os
import re
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
LOG_DIR = "/Users/jethroestrada/Library/Logs"
LOG_FILE = os.path.join(LOG_DIR, "live_network_guardian.log")

os.makedirs(LOG_DIR, exist_ok=True)

# --- Logging Setup ---
console = Console()
log = logging.getLogger("LiveNetworkGuardian")
log.setLevel(logging.DEBUG)  # Set to DEBUG to see all command outputs

rich_handler = RichHandler(rich_tracebacks=True, console=console, show_time=False)
rich_handler.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(rich_handler)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
log.addHandler(file_handler)


def run_cmd(cmd, timeout=2):
    """Run a shell command, log its output, and return stdout."""
    try:
        log.debug(f"Executing: {cmd}")
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )

        # Log the output if it exists
        if result.stdout:
            log.debug(f"Output: {result.stdout.strip()}")
        if result.stderr:
            log.warning(f"Error Output: {result.stderr.strip()}")

        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.error(f"Command timed out after {timeout}s: {cmd}")
        return ""
    except Exception as e:
        log.error(f"Command failed: {cmd} | Exception: {e}")
        return ""


def check_health_scutil():
    """Instant check using scutil."""
    # 1. Interface Check
    nwi = run_cmd("scutil --nwi", timeout=1)
    if f"{INTERFACE} :" not in nwi:
        return False, "Interface Missing"

    # 2. Reachability Check
    reach = run_cmd(f"scutil -r {CHECK_IP}", timeout=1)
    if "Reachable" not in reach:
        return False, "Not Reachable"

    # 3. DNS Check
    dns = run_cmd("scutil --dns", timeout=1)
    if "resolver #1" in dns:
        resolver_block = dns.split("resolver #1")[1].split("resolver #2")[0]
        if "nameserver[0]" not in resolver_block:
            return False, "DNS Missing"

    return True, "Healthy"


def check_speed_live():
    """Stream networkQuality -s in real-time and parse plain text summary."""
    log.info("Running live speed test...")

    cmd = "networkQuality -s"
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        last_line = ""
        # Read character-by-character or line chunks to handle \r live updates
        buffer = ""
        while True:
            char = process.stdout.read(1)
            if not char and process.poll() is not None:
                break
            if char in ("\r", "\n"):
                if buffer.strip():
                    last_line = buffer.strip()
                    # Print live updating line to stdout
                    print(f"\r{last_line}", end="", flush=True)
                buffer = ""
            else:
                buffer += char

        process.wait(timeout=5)
        print()  # Clear line ending after loop

        if not last_line:
            log.warning("Speed test returned no data.")
            return

        # Parse text format: Downlink: X Mbps, Y RPM - Uplink: Z Mbps, W RPM
        pattern = r"Downlink:\s*([\d\.]+)\s*Mbps,\s*([\d]+)\s*RPM\s*-\s*Uplink:\s*([\d\.]+)\s*Mbps,\s*([\d]+)\s*RPM"
        match = re.search(pattern, last_line)

        if match:
            dl, dl_rpm, ul, ul_rpm = match.groups()

            table = Table(title="Live Speed Test Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Download", f"{dl} Mbps ({dl_rpm} RPM)")
            table.add_row("Upload", f"{ul} Mbps ({ul_rpm} RPM)")
            console.print(table)

            log.info(
                f"Speed Results: DL={dl} Mbps, UL={ul} Mbps, DL_RPM={dl_rpm}, UL_RPM={ul_rpm}"
            )
        else:
            log.warning(f"Could not parse live output line: '{last_line}'")

    except subprocess.TimeoutExpired:
        process.kill()
        log.error("Speed test timed out.")
    except Exception as e:
        log.error(f"Failed to run live speed test: {e}")


def apply_fix(issue_type):
    log.warning(f"Applying fix for: {issue_type}")
    if issue_type == "Interface Missing":
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} off")
        time.sleep(3)
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} on")
    elif issue_type == "Not Reachable":
        run_cmd(f"sudo ipconfig set {INTERFACE} DHCP")
    elif issue_type == "DNS Missing":
        run_cmd("sudo dscacheutil -flushcache")
        run_cmd("sudo killall -HUP mDNSResponder")


def main():
    log.info(
        Panel.fit(
            "[bold blue]Network Guardian Fast[/bold blue]\nReal-time scutil monitoring",
            border_style="blue",
        )
    )

    consecutive_failures = 0
    last_fix_time = 0
    last_speed_check = 0

    while True:
        current_time = time.time()

        if current_time - last_fix_time < COOLDOWN_PERIOD:
            remaining = int(COOLDOWN_PERIOD - (current_time - last_fix_time))
            console.print(f"[dim]Stabilizing... {remaining}s[/dim]", end="\r")
            time.sleep(1)
            continue

        if current_time - last_speed_check > SPEED_CHECK_INTERVAL:
            check_speed_live()
            last_speed_check = current_time

        is_healthy, status = check_health_scutil()

        if is_healthy:
            console.print(f"[green]✓[/green] Network Healthy", end="\r")
            consecutive_failures = 0
        else:
            console.print(f"\n[red]✗[/red] {status}")
            consecutive_failures += 1

            if consecutive_failures <= MAX_RETRIES:
                apply_fix(status)
                last_fix_time = time.time()
            else:
                log.error("Max retries reached. Manual check required.")
                consecutive_failures = 0

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\n[bold]Guardian stopped.[/bold]")
