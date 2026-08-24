import subprocess

import httpx
from ping3 import ping


def diagnose_and_fix():
    # Step 1: Check L7 connectivity first (no root needed)
    try:
        r = httpx.get("https://1.1.1.1/cdn-cgi/trace", timeout=5)
        if r.status_code == 200:
            return {"status": "ok", "action": None}
    except Exception:
        pass

    # Step 2: If HTTP fails, try ICMP (may need sudo)
    icmp_result = ping("1.1.1.1")

    # Step 3: Apply fixes based on diagnosis
    if icmp_result is None:
        # L3 failure → toggle Wi-Fi
        subprocess.run(["networksetup", "-setairportpower", "Wi-Fi", "off"])
        subprocess.run(["networksetup", "-setairportpower", "Wi-Fi", "on"])
        return {"status": "repaired", "action": "wifi_toggle"}
    else:
        # L3 ok but L7 failed → likely DNS issue
        subprocess.run(["sudo", "dscacheutil", "-flushcache"])
        subprocess.run(["sudo", "killall", "-HUP", "mDNSResponder"])
        return {"status": "repaired", "action": "dns_flush"}


if __name__ == "__main__":
    diagnose_and_fix()
