#!/bin/bash
# diagnose-large-disk-usage.sh - Safe, fast disk usage analysis for macOS

set -euo pipefail

echo "=== DISK USAGE DIAGNOSIS ==="
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. Overall filesystem status
echo "--- FILESYSTEM OVERVIEW ---"
df -h / | awk 'NR==1 || NR==2 {print}'
echo ""

# 2. Top-level home directory breakdown (fast, no recursion into deep dirs)
echo "--- HOME DIRECTORY BREAKDOWN (Top 15) ---"
du -sh ~/Library/Developer \
       ~/Library/Caches \
       ~/Library/Application\ Support \
       ~/Library/Containers \
       ~/Library/Logs \
       ~/.Trash \
       ~/Downloads \
       ~/Documents \
       ~/Desktop \
       ~/.docker \
       ~/.orbstack \
       ~/.npm \
       ~/.yarn \
       ~/.pnpm-store \
       ~/Library/Application\ Support/MobileSync 2>/dev/null | \
    sort -rh | head -15
echo ""

# 3. Xcode-specific deep dive
echo "--- XCODE STORAGE DETAILS ---"
echo "DerivedData:"
du -sh ~/Library/Developer/Xcode/DerivedData 2>/dev/null || echo "  Not found"
echo "Archives:"
du -sh ~/Library/Developer/Xcode/Archives 2>/dev/null || echo "  Not found"
echo "Simulators:"
xcrun simctl list devices 2>/dev/null | grep -c "Shutdown\|Booted" || echo "  Unable to query"
du -sh ~/Library/Developer/CoreSimulator 2>/dev/null || echo "  Not found"
echo ""

# 4. Container runtime storage
echo "--- CONTAINER RUNTIMES ---"
echo "Docker:"
docker system df -v 2>/dev/null | tail -1 || echo "  Docker not running or not installed"
echo "OrbStack:"
orbctl status 2>/dev/null && du -sh ~/.orbstack 2>/dev/null || echo "  OrbStack not available"
echo ""

# 5. Node.js package manager caches
echo "--- NODE.JS CACHES ---"
echo "npm cache:"
du -sh ~/.npm/_cacache 2>/dev/null || echo "  Empty/not found"
echo "yarn cache:"
du -sh "$(yarn cache dir 2>/dev/null)" 2>/dev/null || echo "  Empty/not found"
echo "pnpm store:"
du -sh "$(pnpm store path 2>/dev/null)" 2>/dev/null || echo "  Empty/not found"
echo ""

# 6. Time Machine local snapshots
echo "--- TIME MACHINE LOCAL SNAPSHOTS ---"
tmutil listlocalsnapshots / 2>/dev/null || echo "  No local snapshots or TM disabled"
echo ""

# 7. Large individual files (>500MB) in user-writable areas
echo "--- LARGE FILES (>500MB) IN HOME ---"
find ~ -xdev -type f -size +500M \
    -not -path "*/Library/Mail/*" \
    -not -path "*/.Trash/*" \
    -not -path "*/node_modules/*" \
    -not -path "*/.git/*" \
    -exec ls -lh {} \; 2>/dev/null | \
    awk '{print $5, $9}' | sort -rh | head -20
echo ""

# 8. Purgeable space (APFS-specific)
echo "--- APFS PURGEABLE SPACE ---"
diskutil apfs list 2>/dev/null | grep -A2 "Purgeable" || echo "  Unable to query APFS info"
echo ""

echo "=== DIAGNOSIS COMPLETE ==="
echo "Review output above BEFORE running any cleanup commands."