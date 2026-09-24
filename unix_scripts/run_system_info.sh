#!/bin/bash
# Run-SystemInfo.sh
# Continuously display GPU, system RAM, and disk information in aligned format with color-coded output
# Colors are usage-based: Green = low load/high remaining, Yellow = moderate, Red = high/critical/low remaining
# Compatible with Mac M1 (Apple Silicon) and Intel Macs

# Configuration
REFRESH_INTERVAL=0.5    # Change this value to adjust refresh rate (e.g., 0.5, 1, 2, 5)
YELLOW_THRESHOLD=50     # % at/above which a value turns Yellow
RED_THRESHOLD=80        # % at/above which a value turns Red

# Column width configuration for alignment
COL_INDEX_WIDTH=6
COL_NAME_WIDTH=25
COL_UTIL_WIDTH=18
COL_MEM_WIDTH=32
COL_REM_WIDTH=14

# ANSI Color codes
COLOR_RESET="\033[0m"
COLOR_RED="\033[0;31m"
COLOR_YELLOW="\033[0;33m"
COLOR_GREEN="\033[0;32m"
COLOR_CYAN="\033[0;36m"
COLOR_WHITE="\033[0;37m"
COLOR_GRAY="\033[0;90m"

# Function to get color based on usage percentage
get_usage_color() {
    local percent="$1"
    
    # Handle empty or invalid input
    if [ -z "$percent" ] || ! [[ "$percent" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        echo "$COLOR_GREEN"
        return
    fi
    
    if (( $(echo "$percent >= $RED_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        echo "$COLOR_RED"
    elif (( $(echo "$percent >= $YELLOW_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        echo "$COLOR_YELLOW"
    else
        echo "$COLOR_GREEN"
    fi
}

# Function to pad string to specific width
pad_string() {
    local str="$1"
    local width=$2
    printf "%-${width}s" "$str"
}

# Function to get CPU usage
get_cpu_usage() {
    # Get CPU usage from top command (one iteration)
    local cpu_line=$(top -l 1 | grep "CPU usage")
    if [ -z "$cpu_line" ]; then
        echo "0.00"
        return
    fi
    
    local cpu_idle=$(echo "$cpu_line" | awk '{for(i=1;i<=NF;i++) if($i ~ /idle/) print $(i-1)}' | sed 's/%//')
    if [ -z "$cpu_idle" ] || ! [[ "$cpu_idle" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        echo "0.00"
        return
    fi
    
    local cpu_usage=$(echo "100 - $cpu_idle" | bc -l 2>/dev/null)
    if [ -z "$cpu_usage" ]; then
        echo "0.00"
        return
    fi
    
    printf "%.2f" "$cpu_usage"
}

# Function to get system RAM info
get_system_ram_info() {
    # Get total physical memory in GB
    local total_mem_bytes=$(sysctl -n hw.memsize 2>/dev/null)
    if [ -z "$total_mem_bytes" ] || ! [[ "$total_mem_bytes" =~ ^[0-9]+$ ]]; then
        echo "0|System RAM|CPU: 0.00%|Mem: 0.00 GB  /  0.00 GB"
        return
    fi
    
    local total_mem_gb=$(echo "scale=2; $total_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$total_mem_gb" ]; then
        total_mem_gb="0.00"
    fi
    
    # Get used memory using vm_stat
    local vm_stat_output=$(vm_stat 2>/dev/null)
    if [ -z "$vm_stat_output" ]; then
        echo "0|System RAM|CPU: 0.00%|Mem: 0.00 GB  /  ${total_mem_gb} GB"
        return
    fi
    
    local pages_free=$(echo "$vm_stat_output" | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
    local pages_active=$(echo "$vm_stat_output" | grep "Pages active" | awk '{print $3}' | sed 's/\.//')
    local pages_wired=$(echo "$vm_stat_output" | grep "Pages wired down" | awk '{print $4}' | sed 's/\.//')
    
    # Validate numeric values
    pages_free=${pages_free:-0}
    pages_active=${pages_active:-0}
    pages_wired=${pages_wired:-0}
    
    local page_size=$(pagesize 2>/dev/null || echo "4096")
    
    # Calculate used memory (active + wired)
    local used_pages=$((pages_active + pages_wired))
    local used_mem_bytes=$((used_pages * page_size))
    local used_mem_gb=$(echo "scale=2; $used_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$used_mem_gb" ]; then
        used_mem_gb="0.00"
    fi
    
    # Get CPU usage
    local cpu_usage=$(get_cpu_usage)
    
    echo "0|System RAM|CPU: ${cpu_usage}%|Mem: ${used_mem_gb} GB  /  ${total_mem_gb} GB"
}

# Function to get disk info
get_disk_info() {
    # Get disk usage for root partition (/)
    local disk_info=$(df -h / 2>/dev/null | tail -1)
    if [ -z "$disk_info" ]; then
        echo "1|System Disk|Usage: 0%|Mem: 0 Gi  /  0 Gi"
        return
    fi
    
    local total_disk=$(echo "$disk_info" | awk '{print $2}')
    local used_disk=$(echo "$disk_info" | awk '{print $3}')
    local avail_disk=$(echo "$disk_info" | awk '{print $4}')
    local use_percent=$(echo "$disk_info" | awk '{print $5}' | sed 's/%//')
    
    # Validate
    total_disk=${total_disk:-"0 Gi"}
    used_disk=${used_disk:-"0 Gi"}
    use_percent=${use_percent:-0}
    
    echo "1|System Disk|Usage: ${use_percent}%|Mem: ${used_disk}  /  ${total_disk}"
}

# Function to get GPU info (Apple Silicon)
get_gpu_info() {
    local gpu_name=""
    local chip_type=$(sysctl -n machdep.cpu.brand_string 2>/dev/null)
    
    if [[ "$chip_type" == *"Apple"* ]]; then
        # Apple Silicon
        gpu_name="Apple GPU (Unified Memory)"
    else
        # Intel Mac with dedicated GPU
        gpu_name=$(system_profiler SPDisplaysDataType 2>/dev/null | grep "Chipset Model" | head -1 | awk -F': ' '{print $2}' | xargs)
        
        if [ -z "$gpu_name" ]; then
            gpu_name="Intel Integrated GPU"
        fi
    fi
    
    # Get unified memory stats (same as system RAM for Apple Silicon)
    local total_mem_bytes=$(sysctl -n hw.memsize 2>/dev/null)
    if [ -z "$total_mem_bytes" ] || ! [[ "$total_mem_bytes" =~ ^[0-9]+$ ]]; then
        echo "2|${gpu_name}|GPU: N/A|Mem: 0.00 GB  /  0.00 GB"
        return
    fi
    
    local total_mem_gb=$(echo "scale=2; $total_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$total_mem_gb" ]; then
        total_mem_gb="0.00"
    fi
    
    # Get used memory using vm_stat
    local vm_stat_output=$(vm_stat 2>/dev/null)
    if [ -z "$vm_stat_output" ]; then
        echo "2|${gpu_name}|GPU: N/A|Mem: 0.00 GB  /  ${total_mem_gb} GB"
        return
    fi
    
    local pages_active=$(echo "$vm_stat_output" | grep "Pages active" | awk '{print $3}' | sed 's/\.//')
    local pages_wired=$(echo "$vm_stat_output" | grep "Pages wired down" | awk '{print $4}' | sed 's/\.//')
    
    pages_active=${pages_active:-0}
    pages_wired=${pages_wired:-0}
    
    local page_size=$(pagesize 2>/dev/null || echo "4096")
    
    local used_pages=$((pages_active + pages_wired))
    local used_mem_bytes=$((used_pages * page_size))
    local used_mem_gb=$(echo "scale=2; $used_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$used_mem_gb" ]; then
        used_mem_gb="0.00"
    fi
    
    echo "2|${gpu_name}|GPU: N/A|Mem: ${used_mem_gb} GB  /  ${total_mem_gb} GB"
}

# Function to extract numeric value from percentage string
extract_percent() {
    local str="$1"
    local result=$(echo "$str" | grep -oE '[0-9]+(\.[0-9]+)?' | head -1)
    if [ -z "$result" ]; then
        echo "0"
    else
        echo "$result"
    fi
}

# Function to extract memory values and calculate remaining
parse_memory_info() {
    local mem_str="$1"
    
    # Format: "Mem: X.XX GB  /  Y.YY GB" or "Mem: X.XX Gi  /  Y.YY Gi"
    local numbers=($(echo "$mem_str" | grep -oE '[0-9]+(\.[0-9]+)?'))
    local unit=$(echo "$mem_str" | grep -oE '(GB|Gi|MB|Mi)' | head -1)
    
    if [ ${#numbers[@]} -lt 2 ]; then
        echo "0|0|${unit:-GB}"
        return
    fi
    
    local used="${numbers[0]}"
    local total="${numbers[1]}"
    unit=${unit:-GB}
    
    local remaining=$(echo "scale=2; $total - $used" | bc -l 2>/dev/null)
    if [ -z "$remaining" ]; then
        remaining="0"
    fi
    
    local percent="0"
    if (( $(echo "$total > 0" | bc -l 2>/dev/null || echo "0") )); then
        percent=$(echo "scale=2; ($used / $total) * 100" | bc -l 2>/dev/null)
        if [ -z "$percent" ]; then
            percent="0"
        fi
    fi
    
    echo "${percent}|${remaining}|${unit}"
}

# Function to display colored output with aligned columns
write_colored_output() {
    local line="$1"
    
    # Split by pipe delimiter
    IFS='|' read -r index name utilization memory <<< "$line"
    
    # Format index and name
    local index_fmt=$(pad_string "$index" $COL_INDEX_WIDTH)
    local name_fmt=$(pad_string "$name" $COL_NAME_WIDTH)
    
    # Parse utilization
    local util_label=$(echo "$utilization" | cut -d':' -f1 | xargs)
    local util_value=$(echo "$utilization" | cut -d':' -f2 | xargs)
    local util_percent=$(extract_percent "$util_value")
    local util_color=$(get_usage_color "$util_percent")
    local util_fmt=$(pad_string "${util_label}: ${util_value}" $COL_UTIL_WIDTH)
    
    # Parse memory
    local mem_parts=$(parse_memory_info "$memory")
    IFS='|' read -r mem_percent mem_remaining mem_unit <<< "$mem_parts"
    local mem_color=$(get_usage_color "$mem_percent")
    local mem_fmt=$(pad_string "$memory" $COL_MEM_WIDTH)
    
    # Format remaining
    local rem_text="Rem: ${mem_remaining} ${mem_unit}"
    local rem_color=$(get_usage_color "$mem_percent")
    local rem_fmt=$(pad_string "$rem_text" $COL_REM_WIDTH)
    
    # Write aligned colored output using echo -e for proper ANSI code interpretation
    echo -ne "${COLOR_WHITE}${index_fmt}${COLOR_RESET}"
    echo -ne "${COLOR_WHITE}${name_fmt}${COLOR_RESET}"
    echo -ne "${util_color}${util_fmt}${COLOR_RESET}"
    echo -ne "${mem_color}${mem_fmt}${COLOR_RESET}"
    echo -e "${rem_color}${rem_fmt}${COLOR_RESET}"
}

# Clear screen and output header + legend once
clear

# Print header using echo -e for ANSI codes
echo -e "${COLOR_CYAN}$(pad_string "index" $COL_INDEX_WIDTH)$(pad_string "name" $COL_NAME_WIDTH)$(pad_string "utilization" $COL_UTIL_WIDTH)$(pad_string "memory" $COL_MEM_WIDTH)$(pad_string "remaining" $COL_REM_WIDTH)${COLOR_RESET}"

# Print legend - escape the % signs properly
echo -ne "${COLOR_GRAY}Legend: ${COLOR_RESET}"
echo -ne "${COLOR_GREEN}Green${COLOR_RESET}"
echo -ne "${COLOR_GRAY} < ${YELLOW_THRESHOLD}%%   ${COLOR_RESET}"
echo -ne "${COLOR_YELLOW}Yellow${COLOR_RESET}"
echo -ne "${COLOR_GRAY} ${YELLOW_THRESHOLD}-$((RED_THRESHOLD-1))%%   ${COLOR_RESET}"
echo -ne "${COLOR_RED}Red${COLOR_RESET}"
echo -e "${COLOR_GRAY} >= ${RED_THRESHOLD}%%${COLOR_RESET}"
echo ""

# Main loop
while true; do
    gpu_info=$(get_gpu_info)
    ram_info=$(get_system_ram_info)
    disk_info=$(get_disk_info)
    
    write_colored_output "$gpu_info"
    write_colored_output "$ram_info"
    write_colored_output "$disk_info"
    echo ""
    
    sleep "$REFRESH_INTERVAL"
done