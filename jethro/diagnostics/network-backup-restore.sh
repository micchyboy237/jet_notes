#!/bin/bash
# =============================================================================
# Mac Network Settings Backup & Restore
# Usage: sudo ./network-backup-restore.sh
# =============================================================================

set -e

BACKUP_DIR="$HOME/network-backups"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="$BACKUP_DIR/network_backup_$TIMESTAMP.txt"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Network Settings Backup/Restore${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Menu
echo "Select an option:"
echo "1) Backup current network settings"
echo "2) List available backups"
echo "3) Restore from backup"
echo "4) Compare current settings with backup"
echo "0) Exit"
echo ""

read -p "Enter choice [0-4]: " choice

case $choice in
    1)
        echo -e "${YELLOW}Backing up network settings...${NC}"
        
        {
            echo "# Network Backup - $(date)"
            echo "# Computer: $(networksetup -getcomputername)"
            echo ""
            
            echo "## Network Services"
            networksetup -listallnetworkservices
            echo ""
            
            echo "## Service Order"
            networksetup -listnetworkserviceorder
            echo ""
            
            echo "## Hardware Ports"
            networksetup -listallhardwareports
            echo ""
            
            # Backup each service
            for service in $(networksetup -listallnetworkservices | grep -v "\*"); do
                echo "## Service: $service"
                echo "### Info"
                networksetup -getinfo "$service"
                echo ""
                
                echo "### DNS"
                networksetup -getdnsservers "$service"
                echo ""
                
                echo "### Search Domains"
                networksetup -getsearchdomains "$service"
                echo ""
                
                echo "### Web Proxy"
                networksetup -getwebproxy "$service"
                echo ""
                
                echo "### Secure Web Proxy"
                networksetup -getsecurewebproxy "$service"
                echo ""
                
                echo "### SOCKS Proxy"
                networksetup -getsocksfirewallproxy "$service"
                echo ""
                
                echo "### Auto Proxy"
                networksetup -getautoproxyurl "$service"
                echo ""
                
                echo "---"
                echo ""
            done
            
        } > "$BACKUP_FILE"
        
        echo -e "${GREEN}✓ Backup saved to: $BACKUP_FILE${NC}"
        ;;
    
    2)
        echo -e "${YELLOW}Available backups:${NC}"
        if ls "$BACKUP_DIR"/network_backup_*.txt 1>/dev/null 2>&1; then
            ls -lh "$BACKUP_DIR"/network_backup_*.txt
        else
            echo -e "${RED}No backups found${NC}"
        fi
        ;;
    
    3)
        echo -e "${YELLOW}Available backups:${NC}"
        BACKUPS=($(ls "$BACKUP_DIR"/network_backup_*.txt 2>/dev/null))
        
        if [ ${#BACKUPS[@]} -eq 0 ]; then
            echo -e "${RED}No backups found${NC}"
            exit 1
        fi
        
        for i in "${!BACKUPS[@]}"; do
            echo "$((i+1))) $(basename "${BACKUPS[$i]}")"
        done
        
        echo ""
        read -p "Select backup number: " backup_num
        
        if [ -n "${BACKUPS[$((backup_num-1))]}" ]; then
            SELECTED_BACKUP="${BACKUPS[$((backup_num-1))]}"
            echo -e "${YELLOW}Selected: $(basename "$SELECTED_BACKUP")${NC}"
            echo ""
            echo -e "${RED}⚠️  This will overwrite current network settings!${NC}"
            read -p "Continue? (yes/no): " confirm
            
            if [ "$confirm" = "yes" ]; then
                echo -e "${YELLOW}Restoring settings...${NC}"
                echo -e "${RED}Note: Manual restoration required from backup file${NC}"
                echo -e "${YELLOW}Backup file: $SELECTED_BACKUP${NC}"
                echo ""
                echo "Open the backup file and manually apply settings using networksetup commands"
            fi
        else
            echo -e "${RED}Invalid selection${NC}"
        fi
        ;;
    
    4)
        echo -e "${YELLOW}Available backups:${NC}"
        BACKUPS=($(ls "$BACKUP_DIR"/network_backup_*.txt 2>/dev/null))
        
        if [ ${#BACKUPS[@]} -eq 0 ]; then
            echo -e "${RED}No backups found${NC}"
            exit 1
        fi
        
        for i in "${!BACKUPS[@]}"; do
            echo "$((i+1))) $(basename "${BACKUPS[$i]}")"
        done
        
        echo ""
        read -p "Select backup number to compare: " backup_num
        
        if [ -n "${BACKUPS[$((backup_num-1))]}" ]; then
            SELECTED_BACKUP="${BACKUPS[$((backup_num-1))]}"
            echo -e "${YELLOW}Comparing with: $(basename "$SELECTED_BACKUP")${NC}"
            echo ""
            
            # Simple comparison
            CURRENT_INFO=$(networksetup -getinfo "Wi-Fi")
            BACKUP_INFO=$(grep -A 10 "## Service: Wi-Fi" "$SELECTED_BACKUP" | grep -A 10 "### Info")
            
            echo "Current DNS:"
            networksetup -getdnsservers "Wi-Fi"
            echo ""
            echo "Backup DNS:"
            grep -A 3 "### DNS" "$SELECTED_BACKUP" | head -4
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
