#!/bin/bash
# =============================================================================
# Mac Network Diagnostic Tool
# Usage: sudo ./network-diagnose.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Mac Network Diagnostic Tool${NC}"
echo -e "${BLUE}  Date: $(date)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to print section headers
print_header() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

# Function to run command and display result
run_cmd() {
    local desc="$1"
    shift
    echo -e "${BLUE}$desc:${NC}"
    "$@" 2>&1 || echo -e "${RED}Command failed${NC}"
    echo ""
}

# =============================================================================
# SECTION 1: Basic System Info
# =============================================================================
print_header "SYSTEM INFORMATION"
run_cmd "Computer Name" networksetup -getcomputername
run_cmd "Current Location" networksetup -getcurrentlocation
run_cmd "macOS Version" sw_vers -productVersion
run_cmd "Hardware Model" sysctl -n hw.model

# =============================================================================
# SECTION 2: Network Services Overview
# =============================================================================
print_header "NETWORK SERVICES"
run_cmd "All Network Services" networksetup -listallnetworkservices
run_cmd "Service Order" networksetup -listnetworkserviceorder
run_cmd "Hardware Ports" networksetup -listallhardwareports

# =============================================================================
# SECTION 3: Wi-Fi Status (assuming en0 is Wi-Fi)
# =============================================================================
print_header "WI-FI STATUS"

# Detect Wi-Fi device
WIFI_DEVICE=$(networksetup -listallhardwareports | grep -A1 "Wi-Fi" | grep "Device:" | awk '{print $2}')

if [ -z "$WIFI_DEVICE" ]; then
    echo -e "${RED}Wi-Fi device not found!${NC}"
else
    echo -e "${GREEN}Wi-Fi Device: $WIFI_DEVICE${NC}"
    echo ""
    
    run_cmd "Wi-Fi Power" networksetup -getairportpower "$WIFI_DEVICE"
    run_cmd "Current Network" networksetup -getairportnetwork "$WIFI_DEVICE"
    run_cmd "Preferred Networks" networksetup -listpreferredwirelessnetworks "$WIFI_DEVICE"
fi

# =============================================================================
# SECTION 4: IP Configuration
# =============================================================================
print_header "IP CONFIGURATION"

# Get Wi-Fi service name
WIFI_SERVICE="Wi-Fi"

run_cmd "IP Information" networksetup -getinfo "$WIFI_SERVICE"
run_cmd "IPv6 Configuration" networksetup -getv6additionalroutes "$WIFI_SERVICE" 2>/dev/null || echo "IPv6 info not available"

# Check actual IP from ifconfig
run_cmd "Interface Details ($WIFI_DEVICE)" ifconfig "$WIFI_DEVICE" 2>/dev/null | grep -E "inet |status"

# =============================================================================
# SECTION 5: DNS Configuration
# =============================================================================
print_header "DNS CONFIGURATION"
run_cmd "DNS Servers" networksetup -getdnsservers "$WIFI_SERVICE"
run_cmd "Search Domains" networksetup -getsearchdomains "$WIFI_SERVICE"

# Test DNS resolution
echo -e "${BLUE}DNS Resolution Test:${NC}"
echo "Testing google.com..."
nslookup google.com 2>&1 | head -10 || echo -e "${RED}DNS resolution failed${NC}"
echo ""

# =============================================================================
# SECTION 6: Proxy Settings
# =============================================================================
print_header "PROXY SETTINGS"
run_cmd "Web Proxy (HTTP)" networksetup -getwebproxy "$WIFI_SERVICE"
run_cmd "Secure Web Proxy (HTTPS)" networksetup -getsecurewebproxy "$WIFI_SERVICE"
run_cmd "SOCKS Proxy" networksetup -getsocksfirewallproxy "$WIFI_SERVICE"
run_cmd "Auto Proxy Discovery" networksetup -getproxyautodiscovery "$WIFI_SERVICE"
run_cmd "Auto Proxy URL" networksetup -getautoproxyurl "$WIFI_SERVICE"
run_cmd "Proxy Bypass Domains" networksetup -getproxybypassdomains "$WIFI_SERVICE"

# =============================================================================
# SECTION 7: Connectivity Tests
# =============================================================================
print_header "CONNECTIVITY TESTS"

echo -e "${BLUE}Ping Tests:${NC}"
echo "Pinging gateway..."
GATEWAY=$(networksetup -getinfo "$WIFI_SERVICE" | grep "Router:" | awk '{print $2}')
if [ -n "$GATEWAY" ]; then
    ping -c 3 "$GATEWAY" 2>&1 | tail -3
else
    echo -e "${YELLOW}No gateway found${NC}"
fi
echo ""

echo "Pinging 8.8.8.8 (Google DNS)..."
ping -c 3 8.8.8.8 2>&1 | tail -3 || echo -e "${RED}Failed${NC}"
echo ""

echo "Pinging google.com..."
ping -c 3 google.com 2>&1 | tail -3 || echo -e "${RED}Failed${NC}"
echo ""

# =============================================================================
# SECTION 8: Advanced Settings
# =============================================================================
print_header "ADVANCED SETTINGS"

if [ -n "$WIFI_DEVICE" ]; then
    run_cmd "MTU Setting" networksetup -getMTU "$WIFI_DEVICE"
    run_cmd "Media Type" networksetup -getmedia "$WIFI_DEVICE"
fi

# =============================================================================
# SECTION 9: Routing Table
# =============================================================================
print_header "ROUTING TABLE"
run_cmd "Active Routes" netstat -rn | head -20

# =============================================================================
# SECTION 10: Recent Network Changes
# =============================================================================
print_header "RECENT NETWORK LOGS"
echo -e "${BLUE}Last 10 network-related log entries:${NC}"
log show --predicate 'subsystem == "com.apple.network"' --last 5m --info 2>/dev/null | tail -10 || echo "Could not retrieve logs"

# =============================================================================
# SUMMARY & RECOMMENDATIONS
# =============================================================================
print_header "DIAGNOSTIC SUMMARY"

echo -e "${YELLOW}Quick Checks:${NC}"

# Check if Wi-Fi is on
WIFI_POWER=$(networksetup -getairportpower "$WIFI_DEVICE" 2>/dev/null | grep -o "On\|Off")
if [ "$WIFI_POWER" = "Off" ]; then
    echo -e "${RED}⚠️  Wi-Fi is OFF${NC}"
else
    echo -e "${GREEN}✓ Wi-Fi is ON${NC}"
fi

# Check if connected to network
CURRENT_NET=$(networksetup -getairportnetwork "$WIFI_DEVICE" 2>/dev/null | grep "Current wireless network:")
if [[ "$CURRENT_NET" == *"Not Associated"* ]] || [[ -z "$CURRENT_NET" ]]; then
    echo -e "${RED}⚠️  Not connected to any Wi-Fi network${NC}"
else
    echo -e "${GREEN}✓ Connected to Wi-Fi${NC}"
fi

# Check IP address
IP_ADDR=$(networksetup -getinfo "$WIFI_SERVICE" | grep "IP address:" | awk '{print $3}')
if [ -z "$IP_ADDR" ] || [ "$IP_ADDR" = "0.0.0.0" ]; then
    echo -e "${RED}⚠️  No valid IP address assigned${NC}"
else
    echo -e "${GREEN}✓ IP Address: $IP_ADDR${NC}"
fi

# Check DNS
DNS_SERVERS=$(networksetup -getdnsservers "$WIFI_SERVICE")
if [[ "$DNS_SERVERS" == *"There aren't any DNS Servers"* ]]; then
    echo -e "${YELLOW}⚠️  No DNS servers configured (using router DNS)${NC}"
else
    echo -e "${GREEN}✓ DNS servers configured${NC}"
fi

# Check proxies
WEB_PROXY=$(networksetup -getwebproxy "$WIFI_SERVICE" | grep "Enabled: Yes")
if [ -n "$WEB_PROXY" ]; then
    echo -e "${YELLOW}⚠️  Web proxy is ENABLED${NC}"
else
    echo -e "${GREEN}✓ No web proxy enabled${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Diagnostic Complete${NC}"
echo -e "${BLUE}========================================${NC}"
