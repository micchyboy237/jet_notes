#!/bin/bash
# =============================================================================
# Mac Network Monitor - Real-Time High Frequency
# Usage: ./network-monitor.sh
# =============================================================================

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m'

# Config
WIFI_DEVICE=$(networksetup -listallhardwareports | grep -A1 "Wi-Fi" | grep "Device:" | awk '{print $2}')
WIFI_SERVICE="Wi-Fi"
REFRESH_RATE=2 # Seconds between updates (Lower = more real-time)

if [ -z "$WIFI_DEVICE" ]; then
    echo -e "${RED}Error: Wi-Fi device not found!${NC}"
    exit 1
fi

echo -e "${YELLOW}Real-Time Network Monitor${NC}"
echo -e "${GRAY}Press Ctrl+C to stop${NC}"
echo ""

# Helper: Get Latency in ms
get_latency() {
    local target=$1
    # Ping once, extract time, remove 'ms'
    local ping_result=$(ping -c 1 -W 1 "$target" 2>/dev/null | grep "time=" | sed -E 's/.*time=([0-9.]+).*/\1/')
    
    if [ -n "$ping_result" ]; then
        # Round to integer for cleaner display
        printf "%.0f" "$ping_result"
    else
        echo "-1"
    fi
}

# Helper: Colorize Latency
colorize_latency() {
    local ms=$1
    if [ "$ms" -eq -1 ]; then
        echo "${RED}Timeout"
    elif [ "$ms" -lt 20 ]; then
        echo "${GREEN}${ms}ms"
    elif [ "$ms" -lt 50 ]; then
        echo "${CYAN}${ms}ms"
    elif [ "$ms" -lt 100 ]; then
        echo "${YELLOW}${ms}ms"
    else
        echo "${RED}${ms}ms"
    fi
}

while true; do
    clear
    
    # Header with precise timestamp
    echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
    printf "${YELLOW}║  REAL-TIME STATUS (%s)   ║${NC}\n" "$(date '+%H:%M:%S')"
    echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
    echo ""

    # --- 1. Connection Quality (Latency) ---
    echo -e "${WHITE}━━━ Connection Quality ━━━${NC}"
    
    # Ping Gateway (Local Network Health)
    GATEWAY=$(netstat -rn 2>/dev/null | grep "default" | grep "$WIFI_DEVICE" | awk '{print $2}' | head -1)
    if [ -n "$GATEWAY" ]; then
        GW_LATENCY=$(get_latency "$GATEWAY")
        echo -e "Gateway ($GATEWAY): $(colorize_latency $GW_LATENCY)"
    else
        echo -e "Gateway: ${GRAY}Not Found${NC}"
    fi

    # Ping Internet (External Health)
    INET_LATENCY=$(get_latency "8.8.8.8")
    echo -e "Internet (8.8.8.8): $(colorize_latency $INET_LATENCY)"
    
    # DNS Latency
    DNS_LATENCY=$(get_latency "1.1.1.1") # Using Cloudflare for DNS speed check
    echo -e "DNS (1.1.1.1):      $(colorize_latency $DNS_LATENCY)"

    echo ""

    # --- 2. Basic Info (Updates less frequently visually, but data is fresh) ---
    echo -e "${WHITE}━━━ Configuration ━━━${NC}"
    
    IP_ADDR=$(ifconfig "$WIFI_DEVICE" 2>/dev/null | awk '/inet / && !/inet6/ {print $2}')
    CURRENT_NET=$(networksetup -getairportnetwork "$WIFI_DEVICE" 2>/dev/null | sed 's/Current Wi-Fi Network: //')
    
    echo -e "Network: ${GREEN}$CURRENT_NET${NC}"
    echo -e "IP:      ${CYAN}${IP_ADDR:-None}${NC}"
    
    # Signal Strength (Quick check)
    AIRPORT_CMD=$(which airport 2>/dev/null || find /System/Library -name "airport" -type f 2>/dev/null | head -1)
    if [ -n "$AIRPORT_CMD" ]; then
        RSSI=$("$AIRPORT_CMD" -I 2>/dev/null | grep "agrCtlRSSI" | awk '{print $2}')
        if [ -n "$RSSI" ] && [ "$RSSI" != "-1" ]; then
            if [ "$RSSI" -gt -50 ]; then SIG_COL="$GREEN"; SIG_TXT="Excellent"
            elif [ "$RSSI" -gt -60 ]; then SIG_COL="$GREEN"; SIG_TXT="Good"
            elif [ "$RSSI" -gt -70 ]; then SIG_COL="$YELLOW"; SIG_TXT="Fair"
            else SIG_COL="$RED"; SIG_TXT="Poor"
            fi
            echo -e "Signal:  ${SIG_COL}${RSSI} dBm ($SIG_TXT)${NC}"
        fi
    fi

    echo ""
    echo -e "${GRAY}Refresh Rate: ${REFRESH_RATE}s | Press Ctrl+C to exit${NC}"
    
    sleep $REFRESH_RATE
done
