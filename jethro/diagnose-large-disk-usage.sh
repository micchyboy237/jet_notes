#!/bin/bash
# save as: diagnose-large-disk-usage.sh && chmod +x diagnose-large-disk-usage.sh

echo "=== 1. Overall Filesystem Status ==="
df -h /
echo ""

echo "=== 2. APFS Volume Breakdown (Critical for macOS) ==="
# Shows actual usage per volume including purgeable space
diskutil apfs list | grep -E "Name:|Capacity|Used|Free|Purgeable|Role:"
echo ""

echo "=== 3. Top 15 Largest Directories in Home ==="
# -d 2 limits depth to avoid overwhelming output
# sort -hr sorts by size descending
du -sh ~/* ~/.* 2>/dev/null | sort -hr | head -15
echo ""

echo "=== 4. Developer-Specific Space Consumers ==="
declare -A DEV_DIRS=(
    ["Xcode DerivedData"]="$HOME/Library/Developer/Xcode/DerivedData"
    ["Xcode Archives"]="$HOME/Library/Developer/Xcode/Archives"
    ["iOS Simulators"]="$HOME/Library/Developer/CoreSimulator"
    ["Docker"]="$HOME/Library/Containers/com.docker.docker"
    ["OrbStack"]="$HOME/.orbstack"
    ["Homebrew Cache"]="$(brew --cache 2>/dev/null)"
    ["npm Cache"]="$HOME/.npm"
    ["yarn Cache"]="$HOME/Library/Caches/Yarn"
    ["pnpm Store"]="$HOME/Library/pnpm/store"
    ["iOS Backups"]="$HOME/Library/Application Support/MobileSync/Backup"
    ["Trash"]="$HOME/.Trash"
    ["System Caches"]="$HOME/Library/Caches"
    ["Logs"]="$HOME/Library/Logs"
)

for name in "${!DEV_DIRS[@]}"; do
    dir="${DEV_DIRS[$name]}"
    if [ -d "$dir" ]; then
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        printf "%-25s %10s  %s\n" "$name:" "$size" "$dir"
    fi
done | sort -t' ' -k2 -hr
echo ""

echo "=== 5. Large Files (>500MB) Modified >30 Days Ago ==="
find ~ -type f -size +500M -mtime +30 -exec ls -lh {} \; 2>/dev/null | \
    awk '{print $5, $9}' | sort -hr | head -20
echo ""

echo "=== 6. Time Machine Local Snapshots ==="
tmutil listlocalsnapshots / 2>/dev/null || echo "No local snapshots found"
echo ""

echo "=== 7. Docker/Container Disk Usage ==="
docker system df -v 2>/dev/null | head -30 || echo "Docker not running or not installed"
echo ""

echo "=== 8. Old Python Virtual Environments (Common Hidden Consumer) ==="
find ~ -maxdepth 4 -type d -name ".venv" -o -name "venv" -o -name ".env" 2>/dev/null | while read venv; do
    size=$(du -sh "$venv" 2>/dev/null | cut -f1)
    echo "$size  $venv"
done | sort -hr | head -10