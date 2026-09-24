#!/bin/bash
# Run-SystemInfo.sh
# Continuously display GPU, system RAM, and disk information in aligned format with color-coded output
# Colors are usage-based: Green = low load/high remaining, Yellow = moderate, Red = high/critical/low remaining
# Compatible with Mac M1 (Apple Silicon) and Intel Macs
# Supports optional GPU utilization via powermetrics (requires sudo)

# Configuration
REFRESH_INTERVAL=0.5    # Change this value to adjust refresh rate (e.g., 0.5, 1, 2, 5)
YELLOW_THRESHOLD=50     # % at/above which a value turns Yellow
RED_THRESHOLD=80        # % at/above which a value turns Red
USE_POWERMETRICS=true   # Set to false to disable powermetrics GPU monitoring
POWERMETRICS_CACHE_SEC=1 # How often to refresh powermetrics data (seconds)

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

# Global cache for powermetrics data
GPU_UTIL_CACHE="N/A"
GPU_UTIL_CACHE_TIME=0

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

# Function to get GPU utilization via powermetrics (cached)
get_gpu_utilization_powermetrics() {
    # Check if we should use powermetrics
    if [ "$USE_POWERMETRICS" != "true" ]; then
        echo "N/A"
        return
    fi
    
    # Check cache freshness
    local current_time=$(date +%s)
    local cache_age=$((current_time - GPU_UTIL_CACHE_TIME))
    
    if [ "$cache_age" -lt "$POWERMETRICS_CACHE_SEC" ] && [ "$GPU_UTIL_CACHE" != "N/A" ]; then
        echo "$GPU_UTIL_CACHE"
        return
    fi
    
    # Try to get GPU active residency from powermetrics
    # This requires sudo; if not available, returns N/A
    local gpu_output
    gpu_output=$(sudo powermetrics --samplers gpu_power -i 500 -n 1 2>/dev/null)
    
    if [ $? -ne 0 ] || [ -z "$gpu_output" ]; then
        # powermetrics failed or no sudo access
        GPU_UTIL_CACHE="N/A"
        GPU_UTIL_CACHE_TIME=$current_time
        echo "N/A"
        return
    fi
    
    # Parse GPU Active Residency percentage
    # Output format varies by macOS version, try multiple patterns
    local gpu_active=""
    
    # Pattern 1: "GPU Active residency: XX.XX%"
    gpu_active=$(echo "$gpu_output" | grep -i "GPU.*Active.*residency" | grep -oE '[0-9]+\.[0-9]+' | head -1)
    
    # Pattern 2: "GPU active residency: XX.XX%"
    if [ -z "$gpu_active" ]; then
        gpu_active=$(echo "$gpu_output" | grep -i "active residency" | grep -i "gpu" | grep -oE '[0-9]+\.[0-9]+' | head -1)
    fi
    
    # Pattern 3: Look for percentage after GPU section
    if [ -z "$gpu_active" ]; then
        gpu_active=$(echo "$gpu_output" | awk '/GPU/{found=1} found && /%/{gsub(/[^0-9.]/,"",$1); print $1; exit}')
    fi
    
    if [ -n "$gpu_active" ] && [[ "$gpu_active" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        GPU_UTIL_CACHE="$gpu_active"
    else
        GPU_UTIL_CACHE="N/A"
    fi
    
    GPU_UTIL_CACHE_TIME=$current_time
    echo "$GPU_UTIL_CACHE"
}

# Function to get system RAM info
get_system_ram_info() {
    local total_mem_bytes=$(sysctl -n hw.memsize 2>/dev/null)
    if [ -z "$total_mem_bytes" ] || ! [[ "$total_mem_bytes" =~ ^[0-9]+$ ]]; then
        echo "0|System RAM|CPU: 0.00%|Mem: 0.00 GB  /  0.00 GB"
        return
    fi
    
    local total_mem_gb=$(echo "scale=2; $total_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$total_mem_gb" ]; then
        total_mem_gb="0.00"
    fi
    
    local vm_stat_output=$(vm_stat 2>/dev/null)
    if [ -z "$vm_stat_output" ]; then
        echo "0|System RAM|CPU: 0.00%|Mem: 0.00 GB  /  ${total_mem_gb} GB"
        return
    fi
    
    local pages_free=$(echo "$vm_stat_output" | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
    local pages_active=$(echo "$vm_stat_output" | grep "Pages active" | awk '{print $3}' | sed 's/\.//')
    local pages_wired=$(echo "$vm_stat_output" | grep "Pages wired down" | awk '{print $4}' | sed 's/\.//')
    
    pages_free=${pages_free:-0}
    pages_active=${pages_active:-0}
    pages_wired=${pages_wired:-0}
    
    local page_size=$(pagesize 2>/dev/null || echo "4096")
    
    local used_pages=$((pages_active + pages_wired))
    local used_mem_bytes=$((used_pages * page_size))
    local used_mem_gb=$(echo "scale=2; $used_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$used_mem_gb" ]; then
        used_mem_gb="0.00"
    fi
    
    local cpu_usage=$(get_cpu_usage)
    
    echo "0|System RAM|CPU: ${cpu_usage}%|Mem: ${used_mem_gb} GB  /  ${total_mem_gb} GB"
}

# Function to get disk info
get_disk_info() {
    local disk_info=$(df -h / 2>/dev/null | tail -1)
    if [ -z "$disk_info" ]; then
        echo "1|System Disk|Usage: 0%|Mem: 0 Gi  /  0 Gi"
        return
    fi
    
    local total_disk=$(echo "$disk_info" | awk '{print $2}')
    local used_disk=$(echo "$disk_info" | awk '{print $3}')
    local avail_disk=$(echo "$disk_info" | awk '{print $4}')
    local use_percent=$(echo "$disk_info" | awk '{print $5}' | sed 's/%//')
    
    total_disk=${total_disk:-"0 Gi"}
    used_disk=${used_disk:-"0 Gi"}
    use_percent=${use_percent:-0}
    
    echo "1|System Disk|Usage: ${use_percent}%|Mem: ${used_disk}  /  ${total_disk}"
}

# Function to get GPU info (Apple Silicon with optional powermetrics)
get_gpu_info() {
    local gpu_name=""
    local chip_type=$(sysctl -n machdep.cpu.brand_string 2>/dev/null)
    
    if [[ "$chip_type" == *"Apple"* ]]; then
        gpu_name="Apple GPU (Unified Memory)"
    else
        gpu_name=$(system_profiler SPDisplaysDataType 2>/dev/null | grep "Chipset Model" | head -1 | awk -F': ' '{print $2}' | xargs)
        if [ -z "$gpu_name" ]; then
            gpu_name="Intel Integrated GPU"
        fi
    fi
    
    # Get GPU utilization from powermetrics (cached)
    local gpu_util=$(get_gpu_utilization_powermetrics)
    
    # Get unified memory stats
    local total_mem_bytes=$(sysctl -n hw.memsize 2>/dev/null)
    if [ -z "$total_mem_bytes" ] || ! [[ "$total_mem_bytes" =~ ^[0-9]+$ ]]; then
        echo "2|${gpu_name}|GPU: ${gpu_util}%|Mem: 0.00 GB  /  0.00 GB"
        return
    fi
    
    local total_mem_gb=$(echo "scale=2; $total_mem_bytes / 1073741824" | bc -l 2>/dev/null)
    if [ -z "$total_mem_gb" ]; then
        total_mem_gb="0.00"
    fi
    
    local vm_stat_output=$(vm_stat 2>/dev/null)
    if [ -z "$vm_stat_output" ]; then
        echo "2|${gpu_name}|GPU: ${gpu_util}%|Mem: 0.00 GB  /  ${total_mem_gb} GB"
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
    
    # Format GPU utilization display
    local gpu_display
    if [ "$gpu_util" = "N/A" ]; then
        gpu_display="GPU: N/A"
    else
        gpu_display="GPU: ${gpu_util}%"
    fi
    
    echo "2|${gpu_name}|${gpu_display}|Mem: ${used_mem_gb} GB  /  ${total_mem_gb} GB"
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
    
    local unit=$(echo "$mem_str" | grep -oE '(GB|Gi|MB|Mi)' | head -1)
    unit=${unit:-GB}
    
    # Extract numbers - handle both formats (with/without space before unit)
    local cleaned=$(echo "$mem_str" | sed 's/[^0-9. ]//g' | tr -s ' ' | sed 's/^ //;s/ $//')
    local numbers_array=($cleaned)
    
    if [ ${#numbers_array[@]} -lt 2 ]; then
        echo "0|0|${unit}"
        return
    fi
    
    local used="${numbers_array[0]}"
    local total="${numbers_array[1]}"
    
    if ! [[ "$used" =~ ^[0-9]+(\.[0-9]+)?$ ]] || ! [[ "$total" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        echo "0|0|${unit}"
        return
    fi
    
    local remaining=$(awk "BEGIN {printf \"%.2f\", $total - $used}")
    if [ -z "$remaining" ]; then
        remaining="0.00"
    fi
    
    local percent="0"
    if awk "BEGIN {exit !($total > 0)}" 2>/dev/null; then
        percent=$(awk "BEGIN {printf \"%.2f\", ($used / $total) * 100}")
        if [ -z "$percent" ]; then
            percent="0"
        fi
    fi
    
    printf "%s|%s|%s" "$percent" "$remaining" "$unit"
}

# Function to display colored output with aligned columns
write_colored_output() {
    local line="$1"
    
    IFS='|' read -r index name utilization memory <<< "$line"
    
    local index_fmt=$(pad_string "$index" $COL_INDEX_WIDTH)
    local name_fmt=$(pad_string "$name" $COL_NAME_WIDTH)
    
    local util_label=$(echo "$utilization" | cut -d':' -f1 | xargs)
    local util_value=$(echo "$utilization" | cut -d':' -f2 | xargs)
    local util_percent=$(extract_percent "$util_value")
    local util_color=$(get_usage_color "$util_percent")
    local util_fmt=$(pad_string "${util_label}: ${util_value}" $COL_UTIL_WIDTH)
    
    local mem_parts
    mem_parts=$(parse_memory_info "$memory")
    
    local mem_percent mem_remaining mem_unit
    IFS='|' read -r mem_percent mem_remaining mem_unit <<< "$mem_parts"
    
    mem_percent=${mem_percent:-0}
    mem_remaining=${mem_remaining:-0}
    mem_unit=${mem_unit:-GB}
    
    local mem_color=$(get_usage_color "$mem_percent")
    local mem_fmt=$(pad_string "$memory" $COL_MEM_WIDTH)
    
    local rem_text="Rem: ${mem_remaining} ${mem_unit}"
    local rem_color=$(get_usage_color "$mem_percent")
    local rem_fmt=$(pad_string "$rem_text" $COL_REM_WIDTH)
    
    echo -ne "${COLOR_WHITE}${index_fmt}${COLOR_RESET}"
    echo -ne "${COLOR_WHITE}${name_fmt}${COLOR_RESET}"
    echo -ne "${util_color}${util_fmt}${COLOR_RESET}"
    echo -ne "${mem_color}${mem_fmt}${COLOR_RESET}"
    echo -e "${rem_color}${rem_fmt}${COLOR_RESET}"
}

# Clear screen and output header + legend once
clear

echo -e "${COLOR_CYAN}$(pad_string "index" $COL_INDEX_WIDTH)$(pad_string "name" $COL_NAME_WIDTH)$(pad_string "utilization" $COL_UTIL_WIDTH)$(pad_string "memory" $COL_MEM_WIDTH)$(pad_string "remaining" $COL_REM_WIDTH)${COLOR_RESET}"

echo -ne "${COLOR_GRAY}Legend: ${COLOR_RESET}"
echo -ne "${COLOR_GREEN}Green${COLOR_RESET}"
echo -ne "${COLOR_GRAY} < ${YELLOW_THRESHOLD}%   ${COLOR_RESET}"
echo -ne "${COLOR_YELLOW}Yellow${COLOR_RESET}"
echo -ne "${COLOR_GRAY} ${YELLOW_THRESHOLD}-$((RED_THRESHOLD-1))%   ${COLOR_RESET}"
echo -ne "${COLOR_RED}Red${COLOR_RESET}"
echo -e "${COLOR_GRAY} >= ${RED_THRESHOLD}%${COLOR_RESET}"
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