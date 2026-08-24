#!/bin/bash
# =============================================================================
# Mac Network Monitor - Real-time monitoring (FINAL FIXED VERSION)
# Usage: ./network-monitor.sh
# =============================================================================

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

# Detect Wi-Fi device and service
WIFI_DEVICE=$(networksetup -listallhardwareports | grep -A1 "Wi-Fi" | grep "Device:" | awk '{print $2}')
WIFI_SERVICE="Wi-Fi"

if [ -z "$WIFI_DEVICE" ]; then
    echo -e "${RED}Error: Wi-Fi device not found!${NC}"
    exit 1
fi

echo -e "${YELLOW}Network Monitor - Press Ctrl+C to stop${NC}"
echo -e "${CYAN}Device: $WIFI_DEVICE | Service: $WIFI_SERVICE${NC}"
echo ""

# Function to get clean IP info using ifconfig (more reliable than networksetup)
get_ip_info() {
    local device="$1"
    ifconfig "$device" 2>/dev/null | awk '/inet / && !/inet6/ {
        ip=$2;
        # Get subnet mask
        for(i=1;i<=NF;i++) {
            if($i ~ /^mask/) {
                mask=$(strtonum("0x" substr($i,6)));
                break;
            }
        }
        print ip;
        print mask;
    }' | head -2
}

# Function to get gateway using netstat
get_gateway() {
    local device="$1"
    netstat -rn 2>/dev/null | grep "default" | grep "$device" | awk '{print $2}' | head -1
}

# Function to get DNS servers
get_dns_servers() {
    local service="$1"
    local dns_output
    dns_output=$(networksetup -getdnsservers "$service" 2>/dev/null)
    
    if [[ "$dns_output" == *"There aren't any DNS Servers"* ]]; then
        echo ""
    else
        # Extract only valid IPv4 addresses
        echo "$dns_output" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | tr '\n' ' ' | sed 's/ $//'
    fi
}

while true; do
    clear
    echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
    printf "${YELLOW}║  Network Status (%s)        ║${NC}\n" "$(date '+%H:%M:%S')"
    echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
    echo ""
    
    # Wi-Fi Status
    WIFI_POWER=$(networksetup -getairportpower "$WIFI_DEVICE" 2>/dev/null | awk -F': ' '{print $2}')
    CURRENT_NET=$(networksetup -getairportnetwork "$WIFI_DEVICE" 2>/dev/null | sed 's/Current Wi-Fi Network: //')
    
    if [ "$WIFI_POWER" = "On" ]; then
        echo -e "Wi-Fi: ${GREEN}● ON${NC}"
    else
        echo -e "Wi-Fi: ${RED}● OFF${NC}"
    fi
    
    if [[ "$CURRENT_NET" == *"Not Associated"* ]] || [ -z "$CURRENT_NET" ]; then
        echo -e "Network: ${RED}Not Connected${NC}"
    else
        echo -e "Network: ${GREEN}$CURRENT_NET${NC}"
    fi
    
    # IP Configuration - Using ifconfig (more reliable)
    IP_INFO=$(get_ip_info "$WIFI_DEVICE")
    IP_ADDR=$(echo "$IP_INFO" | sed -n '1p')
    SUBNET_HEX=$(echo "$IP_INFO" | sed -n '2p')
    
    if [ -n "$IP_ADDR" ] && [ "$IP_ADDR" != "0.0.0.0" ]; then
        echo -e "IP: ${GREEN}$IP_ADDR${NC}"
        
        # Convert hex subnet to dotted decimal if available
        if [ -n "$SUBNET_HEX" ]; then
            SUBNET_DEC=$(printf "%d.%d.%d.%d\n" \
                $(( (SUBNET_HEX >> 24) & 255 )) \
                $(( (SUBNET_HEX >> 16) & 255 )) \
                $(( (SUBNET_HEX >> 8) & 255 )) \
                $(( SUBNET_HEX & 255 )) 2>/dev/null || echo "255.255.255.0")
            echo -e "Subnet: $SUBNET_DEC"
        fi
    else
        echo -e "IP: ${RED}None${NC}"
    fi
    
    # Gateway - Using netstat (more reliable)
    GATEWAY=$(get_gateway "$WIFI_DEVICE")
    
    if [ -n "$GATEWAY" ]; then
        echo -e "Gateway: ${GREEN}$GATEWAY${NC}"
    else
        echo -e "Gateway: ${YELLOW}None detected${NC}"
        GATEWAY=""
    fi
    
    # DNS Servers
    DNS_LIST=$(get_dns_servers "$WIFI_SERVICE")
    if [ -n "$DNS_LIST" ]; then
        echo -e "DNS: ${GREEN}$DNS_LIST${NC}"
    else
        echo -e "DNS: ${YELLOW}Using router DNS${NC}"
    fi
    
    # Connectivity Tests
    echo ""
    echo -e "${CYAN}━━━ Connectivity Tests ━━━${NC}"
    
    # Internet test
    if ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; then
        echo -e "Internet (8.8.8.8): ${GREEN}✓ Connected${NC}"
    else
        echo -e "Internet (8.8.8.8): ${RED}✗ Disconnected${NC}"
    fi
    
    # Gateway test
    if [ -n "$GATEWAY" ]; then
        if ping -c 1 -W 1 "$GATEWAY" >/dev/null 2>&1; then
            echo -e "Gateway ($GATEWAY): ${GREEN}✓ Reachable${NC}"
        else
            echo -e "Gateway ($GATEWAY): ${RED}✗ Unreachable${NC}"
        fi
    else
        echo -e "Gateway: ${YELLOW}⊘ No gateway to test${NC}"
    fi
    
    # DNS test
    if nslookup google.com >/dev/null 2>&1; then
        echo -e "DNS Resolution: ${GREEN}✓ Working${NC}"
    else
        echo -e "DNS Resolution: ${RED}✗ Failed${NC}"
    fi
    
    # Signal Strength
    AIRPORT_CMD="/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    if command -v "$AIRPORT_CMD" >/dev/null 2>&1; then
        SIGNAL_INFO=$("$AIRPORT_CMD" -I 2>/dev/null)
        if [ -n "$SIGNAL_INFO" ]; then
            RSSI=$(echo "$SIGNAL_INFO" | grep "agrCtlRSSI" | awk '{print $2}')
            
            if [ -n "$RSSI" ] && [ "$RSSI" != "-1" ]; then
                if [ "$RSSI" -gt -50 ]; then
                    SIGNAL_COLOR="$GREEN"
                    SIGNAL_QUALITY="Excellent"
                elif [ "$RSSI" -gt -60 ]; then
                    SIGNAL_COLOR="$GREEN"
                    SIGNAL_QUALITY="Good"
                elif [ "$RSSI" -gt -70 ]; then
                    SIGNAL_COLOR="$YELLOW"
                    SIGNAL_QUALITY="Fair"
                else
                    SIGNAL_COLOR="$RED"
                    SIGNAL_QUALITY="Poor"
                fi
                
                echo ""
                echo -e "Signal: ${SIGNAL_COLOR}$RSSI dBm ($SIGNAL_QUALITY)${NC}"
            fi
        fi
    fi
    
    # Additional Info
    echo ""
    echo -e "${CYAN}━━━ Additional Info ━━━${NC}"
    
    # Proxy check
    PROXY_ENABLED=$(networksetup -getwebproxy "$WIFI_SERVICE" 2>/dev/null | grep "Enabled: Yes")
    if [ -n "$PROXY_ENABLED" ]; then
        echo -e "Proxy: ${YELLOW}⚠ Enabled${NC}"
    else
        echo -e "Proxy: ${GREEN}Disabled${NC}"
    fi
    
    # MTU
    MTU=$(networksetup -getMTU "$WIFI_DEVICE" 2>/dev/null | awk '{print $NF}')
    if [ -n "$MTU" ] && [[ "$MTU" =~ ^[0-9]+$ ]]; then
        echo -e "MTU: $MTU"
    fi
    
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop monitoring${NC}"
    
    sleep 5
done
