#!/bin/bash

# --- Configuration ---
LOG_FILE="$HOME/Library/Logs/smart_network_fix.log"
CHECK_URL="https://www.apple.com/library/test/success.html" # Apple's lightweight test page
TIMEOUT=3 # Seconds to wait for a response

# --- Logging Function ---
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# --- Step 1: Hybrid Connectivity Check ---
check_connectivity() {
    # 1. Check if any interface is physically active via scutil
    local active_interface=$(scutil --nwi | grep "NetworkInterfaces" | head -n 1 | awk '{print $2}')
    
    if [ -z "$active_interface" ]; then
        log "No active network interfaces detected."
        return 1
    fi

    # 2. Perform a lightweight HTTP check
    if curl -s --head --fail --max-time $TIMEOUT "$CHECK_URL" > /dev/null 2>&1; then
        return 0 # Success
    else
        return 1 # Failure
    fi
}

log "Running hybrid connectivity check..."
if check_connectivity; then
    log "Connection is healthy. No action needed."
    exit 0
fi

log "Connectivity check failed. Starting targeted repair sequence..."

# --- Step 2: Targeted Repair ---
# Identify the primary interface (usually en0 for Wi-Fi on M1)
PRIMARY_IF="en0"

# Flush DNS Cache
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
log "DNS cache flushed."

# Renew IP Address
sudo ipconfig set "$PRIMARY_IF" DHCP
log "DHCP lease renewed for $PRIMARY_IF."

# Power Cycle Wi-Fi Radio
sudo networksetup -setairportpower "$PRIMARY_IF" off
sleep 5
sudo networksetup -setairportpower "$PRIMARY_IF" on
log "Wi-Fi radio power-cycled."

# --- Step 3: Final Verification ---
sleep 10
if check_connectivity; then
    log "SUCCESS: Internet connection restored."
else
    log "FAILURE: Connection could not be restored automatically."
fi