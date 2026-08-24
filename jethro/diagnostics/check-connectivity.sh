#!/bin/bash

# --- Configuration ---
# Apple's lightweight success page (returns a 200 OK with minimal data)
CHECK_URL="https://www.apple.com/library/test/success.html"
TIMEOUT=3 # Seconds to wait before giving up on a request

# --- Function: Hybrid Connectivity Check ---
check_connectivity() {
    # 1. Hardware/OS State Check (Fastest)
    # Uses scutil to see if the OS currently has an active network path.
    # This avoids sending packets if the Wi-Fi radio is literally off.
    local active_interface=$(scutil --nwi | grep "NetworkInterfaces" | head -n 1 | awk '{print $2}')
    
    if [ -z "$active_interface" ]; then
        echo "STATUS: DISCONNECTED (No active interface detected)"
        return 1
    fi

    # 2. Application Layer Check (Most Reliable)
    # Uses curl to perform a HEAD request. 
    # --fail: Ensures curl returns an error code on HTTP failures (4xx/5xx).
    # --max-time: Prevents the script from hanging if the network is slow.
    # -s: Silent mode to keep output clean.
    if curl -s --head --fail --max-time $TIMEOUT "$CHECK_URL" > /dev/null 2>&1; then
        echo "STATUS: CONNECTED (Interface: $active_interface)"
        return 0
    else
        echo "STATUS: DISCONNECTED (HTTP check failed on $active_interface)"
        return 1
    fi
}

# --- Execution ---
check_connectivity