#!/bin/bash

# Mac M1 Safe Cleanup Script
# Tailored for Jethro Estrada (Dreydeveloper) based on disk_diagnosis.txt

echo "🧹 Starting Safe Cleanup..."
echo "----------------------------------------"

# 1. Development Tool Caches
echo "[1/7] Cleaning Go module cache..."
if command -v go &> /dev/null; then
    go clean -modcache
fi

echo "[2/7] Cleaning npm and Yarn caches..."
if command -v npm &> /dev/null; then
    npm cache clean --force
fi
if command -v yarn &> /dev/null; then
    yarn cache clean
fi

echo "[3/7] Cleaning Python pip cache..."
if command -v pip &> /dev/null; then
    pip cache purge
elif command -v pip3 &> /dev/null; then
    pip3 cache purge
fi

echo "[4/7] Cleaning Homebrew cache..."
if command -v brew &> /dev/null; then
    brew cleanup
fi

# 2. Docker/Colima Cleanup
echo "[5/7] Pruning Docker/Colima unused data..."
if command -v docker &> /dev/null; then
    echo "   Removing stopped containers, unused networks, and dangling images..."
    docker system prune -f
    echo "   Removing all unused images (this may take a moment)..."
    docker image prune -a -f
fi

# 3. Specific App Cleanup (Based on Diagnosis)
echo "[6/7] Cleaning specific app data..."

# Clear the large error log identified in the report
if [ -f "$HOME/.summarize/logs/daemon.err.log" ]; then
    rm "$HOME/.summarize/logs/daemon.err.log"
    echo "   Removed .summarize daemon error log."
fi

# VS Code Cleanup (Only if you've moved to Cursor)
if [ -d "$HOME/Library/Application Support/Code" ]; then
    read -p "   Delete 1.7GB VS Code support data? (y/n): " confirm
    if [[ $confirm == [yY] ]]; then
        rm -rf "$HOME/Library/Application Support/Code"
        echo "   VS Code support data removed."
    else
        echo "   Skipped VS Code cleanup."
    fi
fi

# Opera Cleanup
if [ -d "$HOME/Library/Application Support/com.operasoftware.Opera" ]; then
    read -p "   Delete 1.4GB Opera support data? (y/n): " confirm
    if [[ $confirm == [yY] ]]; then
        rm -rf "$HOME/Library/Application Support/com.operasoftware.Opera"
        rm -rf "$HOME/Library/Caches/com.operasoftware.Opera"
        echo "   Opera data removed."
    else
        echo "   Skipped Opera cleanup."
    fi
fi

# 4. General User Caches
echo "[7/7] Clearing general user caches..."
rm -rf ~/Library/Caches/*

echo "----------------------------------------"
echo "✅ Cleanup Complete!"
echo "💡 Tip: Restart your Mac to ensure macOS releases any 'purgeable' space."
echo "💡 Tip: Manually check your Desktop folder (currently 58GB) for large files to move or delete."