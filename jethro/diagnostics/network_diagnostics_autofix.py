import logging
import subprocess
import sys
import time

# --- Configuration ---
LOG_FILE = "/Users/jethroestrada/Library/Logs/network_diagnostics_autofix.log"
CHECK_IP = "8.8.8.8"
INTERFACE = "en1"  # Based on your scutil output, your active interface is en1

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def run_cmd(cmd):
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception as e:
        logging.error(f"Command failed: {cmd} | Error: {e}")
        return ""


def check_reachability():
    """Step 1 & 2: Check interface and path using scutil."""
    logging.info("Running scutil reachability check...")

    # Check if interface exists in NWI
    nwi_output = run_cmd("scutil --nwi")
    if f"{INTERFACE} :" not in nwi_output:
        logging.warning(f"Interface {INTERFACE} not found in NWI.")
        return False

    # Check reachability to Google DNS
    reach_output = run_cmd(f"scutil -r {CHECK_IP}")
    if "Reachable" in reach_output:
        logging.info("Connection is Reachable.")
        return True
    else:
        logging.warning("Connection is NOT Reachable.")
        return False


def check_dns():
    """Step 3: Verify DNS servers are present."""
    dns_output = run_cmd("scutil --dns")
    # Look for nameserver entries in resolver #1
    if "nameserver[0]" in dns_output.split("resolver #1")[1].split("resolver #2")[0]:
        logging.info("DNS configuration looks valid.")
        return True
    else:
        logging.warning("DNS nameservers missing or invalid.")
        return False


def apply_fix(step):
    """Apply targeted fixes based on the failure point."""
    logging.info(f"Applying fix for step: {step}")

    if step == "interface":
        logging.info("Power cycling Wi-Fi radio...")
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} off")
        time.sleep(5)
        run_cmd(f"sudo networksetup -setairportpower {INTERFACE} on")

    elif step == "path":
        logging.info("Renewing DHCP lease...")
        run_cmd(f"sudo ipconfig set {INTERFACE} DHCP")

    elif step == "dns":
        logging.info("Flushing DNS cache and restarting mDNSResponder...")
        run_cmd("sudo dscacheutil -flushcache")
        run_cmd("sudo killall -HUP mDNSResponder")


def main():
    logging.info("--- Starting Network Guardian Check ---")

    # 1. Check Path
    if not check_reachability():
        # Try fixing the path first (DHCP)
        apply_fix("path")
        time.sleep(5)
        if not check_reachability():
            # If still down, power cycle the hardware
            apply_fix("interface")
            time.sleep(10)
            if not check_reachability():
                logging.error(
                    "CRITICAL: Could not restore reachability after all attempts."
                )
                sys.exit(1)

    # 2. Check DNS (Even if reachable, DNS might be broken)
    if not check_dns():
        apply_fix("dns")
        time.sleep(2)
        if not check_dns():
            logging.error("CRITICAL: DNS issues persist after flush.")

    logging.info("Network checks completed successfully.")


if __name__ == "__main__":
    main()
