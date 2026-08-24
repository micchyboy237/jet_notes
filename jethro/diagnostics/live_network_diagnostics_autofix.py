import logging
import subprocess
import time

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

# --- Configuration ---
INTERFACE = "en1"  # Based on your scutil output
CHECK_IP = "8.8.8.8"
CHECK_INTERVAL = 30  # Check every 30 seconds
COOLDOWN_PERIOD = 120  # Wait 2 minutes after a fix before checking again
MAX_RETRIES = 3  # Max fixes before giving up for a while

# --- Rich Logging Setup ---
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)],
)
log = logging.getLogger("NetworkGuardian")


def run_cmd(cmd):
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception as e:
        log.error(f"Command failed: {cmd} | Error: {e}")
        return ""


def check_health():
    """Perform the hybrid health check."""
    # 1. Interface Check
    nwi = run_cmd("scutil --nwi")
    if f"{INTERFACE} :" not in nwi:
        return False, "Interface Missing"

    # 2. Reachability Check
    reach = run_cmd(f"scutil -r {CHECK_IP}")
    if "Reachable" not in reach:
        return False, "Not Reachable"

    # 3. DNS Check
    dns = run_cmd("scutil --dns")
    resolver_1 = (
        dns.split("resolver #1")[1].split("resolver #2")[0]
        if "resolver #1" in dns
        else ""
    )
    if "nameserver[0]" not in resolver_1:
        return False, "DNS Missing"

    return True, "Healthy"


def apply_fix(issue_type):
    """Apply targeted fixes."""
    log.warning(f"Applying fix for: {issue_type}")

    if issue_type == "Interface Missing":
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} off")
        time.sleep(5)
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} on")
    elif issue_type == "Not Reachable":
        run_cmd(f"sudo ipconfig set {INTERFACE} DHCP")
    elif issue_type == "DNS Missing":
        run_cmd("sudo dscacheutil -flushcache")
        run_cmd("sudo killall -HUP mDNSResponder")


def main():
    log.info(
        Panel.fit(
            "[bold blue]Network Guardian Live[/bold blue]\nMonitoring interface: en1",
            border_style="blue",
        )
    )

    consecutive_failures = 0
    last_fix_time = 0

    while True:
        current_time = time.time()

        # Skip checks if we are in a cooldown period after a fix
        if current_time - last_fix_time < COOLDOWN_PERIOD:
            remaining = int(COOLDOWN_PERIOD - (current_time - last_fix_time))
            console.print(
                f"[dim]Cooldown active... resuming in {remaining}s[/dim]", end="\r"
            )
            time.sleep(1)
            continue

        is_healthy, status = check_health()

        if is_healthy:
            console.print(f"[green]✓[/green] Network is {status}", end="\r")
            consecutive_failures = 0
        else:
            console.print(f"\n[red]✗[/red] Issue detected: {status}")
            consecutive_failures += 1

            if consecutive_failures <= MAX_RETRIES:
                apply_fix(status)
                last_fix_time = time.time()
                log.info("Entering cooldown period to allow network to stabilize...")
            else:
                log.error("Max retries reached. Manual intervention may be required.")
                consecutive_failures = 0  # Reset to keep trying occasionally

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\n[bold]Network Guardian stopped by user.[/bold]")
