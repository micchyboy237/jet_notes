#!/bin/bash
# =============================================================================
# Mac Network Monitor - Real-time monitoring
# Usage: ./network-monitor.sh
# =============================================================================

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

WIFI_DEVICE=$(networksetup -listallhardwareports | grep -A1 "Wi-Fi" | grep "Device:" | awk '{print $2}')
WIFI_SERVICE="Wi-Fi"

echo -e "${YELLOW}Network Monitor - Press Ctrl+C to stop${NC}"
echo ""

while true; do
    clear
    echo -e "${YELLOW}=== Network Status ($(date '+%H:%M:%S')) ===${NC}"
    echo ""
    
    # Wi-Fi Status
    WIFI_POWER=$(networksetup -getairportpower "$WIFI_DEVICE" 2>/dev/null | grep -o "On\|Off")
    CURRENT_NET=$(networksetup -getairportnetwork "$WIFI_DEVICE" 2>/dev/null | sed 's/Current wireless network: //')
    
    echo -e "Wi-Fi: ${GREEN}$WIFI_POWER${NC}"
    echo -e "Network: $CURRENT_NET"
    
    # IP Address
    IP_ADDR=$(networksetup -getinfo "$WIFI_SERVICE" 2>/dev/null | grep "IP address:" | awk '{print $3}')
    echo -e "IP: ${GREEN}${IP_ADDR:-None}${NC}"
    
    # Gateway
    GATEWAY=$(networksetup -getinfo "$WIFI_SERVICE" 2>/dev/null | grep "Router:" | awk '{print $3}')
    echo -e "Gateway: ${GATEWAY:-None}"
    
    # Quick connectivity test
    echo ""
    echo -e "${YELLOW}Connectivity:${NC}"
    
    if ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; then
        echo -e "Internet: ${GREEN}✓ Connected${NC}"
    else
        echo -e "Internet: ${RED}✗ Disconnected${NC}"
    fi
    
    if ping -c 1 -W 1 "$GATEWAY" >/dev/null 2>&1; then
        echo -e "Gateway: ${GREEN}✓ Reachable${NC}"
    else
        echo -e "Gateway: ${RED}✗ Unreachable${NC}"
    fi
    
    # DNS test
    if nslookup google.com >/dev/null 2>&1; then
        echo -e "DNS: ${GREEN}✓ Working${NC}"
    else
        echo -e "DNS: ${RED}✗ Failed${NC}"
    fi
    
    # Signal strength (if available)
    if command -v /System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport >/dev/null; then
        SIGNAL=$(/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I | grep agrCtlRSSI | awk '{print $2}')
        if [ -n "$SIGNAL" ]; then
            echo ""
            echo -e "Signal Strength: ${SIGNAL} dBm"
        fi
    fi
    
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop monitoring${NC}"
    
    sleep 5
done
