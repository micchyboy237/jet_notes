#!/bin/bash
# =============================================================================
# Mac Network Fix Tool - Common Issues
# Usage: sudo ./network-fix-common.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Mac Network Fix Tool${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Detect Wi-Fi device and service
WIFI_DEVICE=$(networksetup -listallhardwareports | grep -A1 "Wi-Fi" | grep "Device:" | awk '{print $2}')
WIFI_SERVICE="Wi-Fi"

if [ -z "$WIFI_DEVICE" ]; then
    echo -e "${RED}Error: Wi-Fi device not found!${NC}"
    exit 1
fi

echo -e "${GREEN}Detected Wi-Fi Device: $WIFI_DEVICE${NC}"
echo ""

# Menu
echo "Select a fix option:"
echo "1) Reset Wi-Fi (toggle off/on)"
echo "2) Renew DHCP lease"
echo "3) Flush DNS cache"
echo "4) Reset DNS to Google (8.8.8.8, 8.8.4.4)"
echo "5) Reset DNS to Cloudflare (1.1.1.1, 1.0.0.1)"
echo "6) Clear all DNS servers (use router DNS)"
echo "7) Disable all proxies"
echo "8) Reset MTU to automatic"
echo "9) Remove problematic Wi-Fi network"
echo "10) Reset network location to Automatic"
echo "11) Full network reset (nuclear option)"
echo "0) Exit"
echo ""

read -p "Enter choice [0-11]: " choice

case $choice in
    1)
        echo -e "${YELLOW}Toggling Wi-Fi...${NC}"
        networksetup -setairportpower "$WIFI_DEVICE" off
        sleep 2
        networksetup -setairportpower "$WIFI_DEVICE" on
        sleep 3
        echo -e "${GREEN}✓ Wi-Fi has been reset${NC}"
        ;;
    
    2)
        echo -e "${YELLOW}Renewing DHCP lease...${NC}"
        # Release and renew by toggling service
        networksetup -setnetworkserviceenabled "$WIFI_SERVICE" off
        sleep 2
        networksetup -setnetworkserviceenabled "$WIFI_SERVICE" on
        sleep 3
        echo -e "${GREEN}✓ DHCP lease renewed${NC}"
        ;;
    
    3)
        echo -e "${YELLOW}Flushing DNS cache...${NC}"
        dscacheutil -flushcache
        sudo killall -HUP mDNSResponder
        echo -e "${GREEN}✓ DNS cache flushed${NC}"
        ;;
    
    4)
        echo -e "${YELLOW}Setting DNS to Google...${NC}"
        networksetup -setdnsservers "$WIFI_SERVICE" 8.8.8.8 8.8.4.4
        echo -e "${GREEN}✓ DNS set to Google (8.8.8.8, 8.8.4.4)${NC}"
        ;;
    
    5)
        echo -e "${YELLOW}Setting DNS to Cloudflare...${NC}"
        networksetup -setdnsservers "$WIFI_SERVICE" 1.1.1.1 1.0.0.1
        echo -e "${GREEN}✓ DNS set to Cloudflare (1.1.1.1, 1.0.0.1)${NC}"
        ;;
    
    6)
        echo -e "${YELLOW}Clearing DNS servers...${NC}"
        networksetup -setdnsservers "$WIFI_SERVICE" Empty
        echo -e "${GREEN}✓ DNS servers cleared (will use router DNS)${NC}"
        ;;
    
    7)
        echo -e "${YELLOW}Disabling all proxies...${NC}"
        networksetup -setwebproxystate "$WIFI_SERVICE" off
        networksetup -setsecurewebproxystate "$WIFI_SERVICE" off
        networksetup -setsocksfirewallproxystate "$WIFI_SERVICE" off
        networksetup -setautoproxystate "$WIFI_SERVICE" off
        networksetup -setproxyautodiscovery "$WIFI_SERVICE" off
        echo -e "${GREEN}✓ All proxies disabled${NC}"
        ;;
    
    8)
        echo -e "${YELLOW}Resetting MTU to automatic...${NC}"
        networksetup -setMTUAndMediaAutomatically "$WIFI_DEVICE"
        echo -e "${GREEN}✓ MTU reset to automatic${NC}"
        ;;
    
    9)
        read -p "Enter Wi-Fi network name to remove: " SSID
        if [ -n "$SSID" ]; then
            networksetup -removepreferredwirelessnetwork "$WIFI_DEVICE" "$SSID"
            echo -e "${GREEN}✓ Removed '$SSID' from preferred networks${NC}"
        else
            echo -e "${RED}No SSID provided${NC}"
        fi
        ;;
    
    10)
        echo -e "${YELLOW}Switching to Automatic location...${NC}"
        networksetup -switchtolocation "Automatic"
        echo -e "${GREEN}✓ Switched to Automatic location${NC}"
        ;;
    
    11)
        echo -e "${RED}⚠️  WARNING: This will perform a full network reset!${NC}"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo -e "${YELLOW}Performing full reset...${NC}"
            
            # Remove all preferred networks
            networksetup -removeallpreferredwirelessnetworks "$WIFI_DEVICE"
            
            # Reset DNS
            networksetup -setdnsservers "$WIFI_SERVICE" Empty
            
            # Disable proxies
            networksetup -setwebproxystate "$WIFI_SERVICE" off
            networksetup -setsecurewebproxystate "$WIFI_SERVICE" off
            networksetup -setsocksfirewallproxystate "$WIFI_SERVICE" off
            networksetup -setautoproxystate "$WIFI_SERVICE" off
            
            # Reset MTU
            networksetup -setMTUAndMediaAutomatically "$WIFI_DEVICE"
            
            # Set to DHCP
            networksetup -setdhcp "$WIFI_SERVICE"
            
            # Toggle Wi-Fi
            networksetup -setairportpower "$WIFI_DEVICE" off
            sleep 2
            networksetup -setairportpower "$WIFI_DEVICE" on
            
            echo -e "${GREEN}✓ Full network reset complete${NC}"
            echo -e "${YELLOW}You will need to reconnect to your Wi-Fi network${NC}"
        else
            echo -e "${YELLOW}Reset cancelled${NC}"
        fi
        ;;
    
    0)
        echo "Exiting..."
        exit 0
        ;;
    
    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}Verifying current status...${NC}"
networksetup -getinfo "$WIFI_SERVICE"
networksetup -getdnsservers "$WIFI_SERVICE"
