#!/bin/bash
# =============================================================================
# Mac Network Monitor - With Speed Test (FIXED)
# Usage: ./network-monitor.sh
# =============================================================================

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'

# Detect Wi-Fi device and service
WIFI_DEVICE=$(networksetup -listallhardwareports | grep -A1 "Wi-Fi" | grep "Device:" | awk '{print $2}')
WIFI_SERVICE="Wi-Fi"

if [ -z "$WIFI_DEVICE" ]; then
    echo -e "${RED}Error: Wi-Fi device not found!${NC}"
    exit 1
fi

# Speed test configuration
SPEED_TEST_URL="http://speedtest.tele2.net/1MB.zip"
SPEED_TEST_TIMEOUT=15

echo -e "${YELLOW}Network Monitor - Press Ctrl+C to stop${NC}"
echo -e "${CYAN}Device: $WIFI_DEVICE | Service: $WIFI_SERVICE${NC}"
echo ""

# Function to get clean IP info
get_ip_info() {
    local device="$1"
    ifconfig "$device" 2>/dev/null | awk '/inet / && !/inet6/ {print $2}' | head -1
}

# Function to get gateway
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
        echo "$dns_output" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | tr '\n' ' ' | sed 's/ $//'
    fi
}

# Function to categorize speed
categorize_speed() {
    local speed_mbps=$1
    
    # Use awk for floating point comparison
    local category=$(awk -v speed="$speed_mbps" 'BEGIN {
        if (speed < 1) print "Very Slow (< 1 Mbps)|RED"
        else if (speed < 5) print "Slow (1-5 Mbps)|YELLOW"
        else if (speed < 25) print "Moderate (5-25 Mbps)|CYAN"
        else if (speed < 100) print "Fast (25-100 Mbps)|GREEN"
        else if (speed < 500) print "Very Fast (100-500 Mbps)|GREEN"
        else print "Ultra Fast (> 500 Mbps)|MAGENTA"
    }')
    
    echo "$category"
}

# Function to test download speed
test_download_speed() {
    local url="$1"
    local temp_file="/tmp/speedtest_$$.tmp"
    
    # Use curl with built-in timing and size reporting
    local curl_output=$(curl -L -o "$temp_file" --max-time $SPEED_TEST_TIMEOUT -s -w "SIZE:%{size_download}\nTIME:%{time_total}" "$url" 2>/dev/null)
    
    # Parse curl output
    local bytes_downloaded=$(echo "$curl_output" | grep "SIZE:" | cut -d: -f2)
    local time_taken=$(echo "$curl_output" | grep "TIME:" | cut -d: -f2)
    
    # Cleanup
    rm -f "$temp_file"
    
    # Calculate speed in Mbps
    if [ -n "$bytes_downloaded" ] && [ "$bytes_downloaded" -gt 0 ] 2>/dev/null && [ -n "$time_taken" ]; then
        # Use awk for floating point math
        local speed_mbps=$(awk -v bytes="$bytes_downloaded" -v time="$time_taken" 'BEGIN {
            if (time > 0) {
                bits = bytes * 8
                mbps = bits / time / 1000000
                printf "%.2f", mbps
            } else {
                print "0"
            }
        }')
        echo "$speed_mbps"
    else
        echo "0"
    fi
}

# Track last speed test time
LAST_SPEED_TEST=0
SPEED_TEST_INTERVAL=30
CACHED_SPEED="N/A"
CACHED_CATEGORY=""
CACHED_COLOR=""

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
    
    # IP Configuration
    IP_ADDR=$(get_ip_info "$WIFI_DEVICE")
    
    if [ -n "$IP_ADDR" ] && [ "$IP_ADDR" != "0.0.0.0" ]; then
        echo -e "IP: ${GREEN}$IP_ADDR${NC}"
    else
        echo -e "IP: ${RED}None${NC}"
    fi
    
    # Gateway
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
    
    if ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; then
        echo -e "Internet (8.8.8.8): ${GREEN}✓ Connected${NC}"
    else
        echo -e "Internet (8.8.8.8): ${RED}✗ Disconnected${NC}"
    fi
    
    if [ -n "$GATEWAY" ]; then
        if ping -c 1 -W 1 "$GATEWAY" >/dev/null 2>&1; then
            echo -e "Gateway ($GATEWAY): ${GREEN}✓ Reachable${NC}"
        else
            echo -e "Gateway ($GATEWAY): ${RED}✗ Unreachable${NC}"
        fi
    else
        echo -e "Gateway: ${YELLOW}⊘ No gateway to test${NC}"
    fi
    
    if nslookup google.com >/dev/null 2>&1; then
        echo -e "DNS Resolution: ${GREEN}✓ Working${NC}"
    else
        echo -e "DNS Resolution: ${RED}✗ Failed${NC}"
    fi
    
    # Speed Test Section
    echo ""
    echo -e "${MAGENTA}━━━ Download Speed ━━━${NC}"
    
    CURRENT_TIME=$(date +%s)
    TIME_SINCE_LAST=$((CURRENT_TIME - LAST_SPEED_TEST))
    
    # Only test if enough time has passed or first run
    if [ "$LAST_SPEED_TEST" -eq 0 ] || [ "$TIME_SINCE_LAST" -ge $SPEED_TEST_INTERVAL ]; then
        echo -e "${YELLOW}Testing speed...${NC}"
        
        SPEED_MBPS=$(test_download_speed "$SPEED_TEST_URL")
        
        if [ "$SPEED_MBPS" != "0" ] && [ -n "$SPEED_MBPS" ]; then
            CACHED_SPEED="$SPEED_MBPS"
            
            # Get category and color
            CATEGORY_RESULT=$(categorize_speed "$SPEED_MBPS")
            CACHED_CATEGORY=$(echo "$CATEGORY_RESULT" | cut -d'|' -f1)
            COLOR_NAME=$(echo "$CATEGORY_RESULT" | cut -d'|' -f2)
            
            # Set color variable based on name
            case $COLOR_NAME in
                RED) CACHED_COLOR="$RED" ;;
                YELLOW) CACHED_COLOR="$YELLOW" ;;
                CYAN) CACHED_COLOR="$CYAN" ;;
                GREEN) CACHED_COLOR="$GREEN" ;;
                MAGENTA) CACHED_COLOR="$MAGENTA" ;;
                *) CACHED_COLOR="$WHITE" ;;
            esac
            
            LAST_SPEED_TEST=$CURRENT_TIME
            echo -e "Speed: ${WHITE}${SPEED_MBPS} Mbps${NC}"
            echo -e "Category: ${CACHED_COLOR}${CACHED_CATEGORY}${NC}"
        else
            echo -e "Speed: ${YELLOW}Test failed or timed out${NC}"
            CACHED_SPEED="N/A"
            CACHED_CATEGORY=""
            CACHED_COLOR=""
        fi
    else
        # Show cached results
        if [ "$CACHED_SPEED" != "N/A" ] && [ -n "$CACHED_CATEGORY" ]; then
            echo -e "Speed: ${WHITE}${CACHED_SPEED} Mbps${NC}"
            echo -e "Category: ${CACHED_COLOR}${CACHED_CATEGORY}${NC}"
        else
            echo -e "Speed: ${YELLOW}Waiting for next test...${NC}"
        fi
        
        REMAINING=$((SPEED_TEST_INTERVAL - TIME_SINCE_LAST))
        echo -e "${CYAN}(Next test in ${REMAINING}s)${NC}"
    fi
    
    # Signal Strength (if available)
    AIRPORT_CMD=$(which airport 2>/dev/null || find /System/Library -name "airport" -type f 2>/dev/null | head -1)
    if [ -n "$AIRPORT_CMD" ] && [ -x "$AIRPORT_CMD" ]; then
        SIGNAL_INFO=$("$AIRPORT_CMD" -I 2>/dev/null)
        if [ -n "$SIGNAL_INFO" ]; then
            RSSI=$(echo "$SIGNAL_INFO" | grep "agrCtlRSSI" | awk '{print $2}')
            
            if [ -n "$RSSI" ] && [ "$RSSI" != "-1" ]; then
                if [ "$RSSI" -gt -50 ]; then
                    SIGNAL_COLOR="$GREEN"; SIGNAL_QUALITY="Excellent"
                elif [ "$RSSI" -gt -60 ]; then
                    SIGNAL_COLOR="$GREEN"; SIGNAL_QUALITY="Good"
                elif [ "$RSSI" -gt -70 ]; then
                    SIGNAL_COLOR="$YELLOW"; SIGNAL_QUALITY="Fair"
                else
                    SIGNAL_COLOR="$RED"; SIGNAL_QUALITY="Poor"
                fi
                
                echo ""
                echo -e "Signal: ${SIGNAL_COLOR}$RSSI dBm ($SIGNAL_QUALITY)${NC}"
            fi
        fi
    fi
    
    # Additional Info
    echo ""
    echo -e "${CYAN}━━━ Additional Info ━━━${NC}"
    
    PROXY_ENABLED=$(networksetup -getwebproxy "$WIFI_SERVICE" 2>/dev/null | grep "Enabled: Yes")
    if [ -n "$PROXY_ENABLED" ]; then
        echo -e "Proxy: ${YELLOW}⚠ Enabled${NC}"
    else
        echo -e "Proxy: ${GREEN}Disabled${NC}"
    fi
    
    MTU=$(networksetup -getMTU "$WIFI_DEVICE" 2>/dev/null | awk '{print $NF}')
    if [ -n "$MTU" ] && [[ "$MTU" =~ ^[0-9]+$ ]]; then
        echo -e "MTU: $MTU"
    fi
    
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop monitoring${NC}"
    
    sleep 5
done
