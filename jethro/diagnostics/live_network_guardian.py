import json
import logging
import os
import subprocess
import time

import httpx
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

# --- Configuration ---
INTERFACE = "en1"
CHECK_URL = "https://www.apple.com/library/test/success.html"
CHECK_INTERVAL = 30
SPEED_CHECK_INTERVAL = 300  # Check speed every 5 minutes
COOLDOWN_PERIOD = 120
MAX_RETRIES = 3
LOG_DIR = "/Users/jethroestrada/Library/Logs"
LOG_FILE = os.path.join(LOG_DIR, "live_network_guardian.log")

os.makedirs(LOG_DIR, exist_ok=True)

# --- Logging Setup ---
console = Console()
log = logging.getLogger("NetworkGuardian")
log.setLevel(logging.INFO)

rich_handler = RichHandler(rich_tracebacks=True, console=console, show_time=False)
rich_handler.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(rich_handler)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
log.addHandler(file_handler)


def run_cmd(cmd):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except Exception as e:
        log.error(f"Command failed: {cmd} | Error: {e}")
        return ""


def check_connectivity():
    """Modern check using httpx."""
    try:
        with httpx.Client(timeout=5) as client:
            response = client.head(CHECK_URL)
            return response.status_code == 200
    except Exception:
        return False


def check_speed():
    """Use macOS built-in networkQuality for accurate M1 metrics."""
    log.info("Running speed and responsiveness test...")
    output = run_cmd("networkQuality -c")
    try:
        data = json.loads(output)
        dl = data.get("download_capacity", "N/A")
        ul = data.get("upload_capacity", "N/A")
        resp = data.get("responsiveness", "N/A")

        table = Table(title="Network Quality Report")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Download", f"{dl} Mbps")
        table.add_row("Upload", f"{ul} Mbps")
        table.add_row("Responsiveness", resp)
        console.print(table)

        log.info(f"Speed Test - DL: {dl}, UL: {ul}, Resp: {resp}")
    except json.JSONDecodeError:
        log.warning("Could not parse networkQuality output.")


def apply_fix(issue_type):
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
        Panel.fit("[bold blue]Network Guardian Live[/bold blue]", border_style="blue")
    )

    consecutive_failures = 0
    last_fix_time = 0
    last_speed_check = 0

    while True:
        current_time = time.time()

        if current_time - last_fix_time < COOLDOWN_PERIOD:
            remaining = int(COOLDOWN_PERIOD - (current_time - last_fix_time))
            console.print(
                f"[dim]Cooldown active... resuming in {remaining}s[/dim]", end="\r"
            )
            time.sleep(1)
            continue

        # Periodic Speed Check
        if current_time - last_speed_check > SPEED_CHECK_INTERVAL:
            check_speed()
            last_speed_check = current_time

        if check_connectivity():
            console.print(f"[green]✓[/green] Network is Healthy", end="\r")
            consecutive_failures = 0
        else:
            console.print(f"\n[red]✗[/red] Connectivity Lost")
            consecutive_failures += 1

            if consecutive_failures <= MAX_RETRIES:
                apply_fix("Not Reachable")
                last_fix_time = time.time()
            else:
                log.error("Max retries reached.")
                consecutive_failures = 0

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\n[bold]Network Guardian stopped.[/bold]")
