#!/bin/bash

# Set the interval (in seconds) between tests
INTERVAL=1

echo "Live Network Quality Monitor"
echo "Press Ctrl+C to stop..."
echo "----------------------------------------"

while true; do
    # Run the test and capture the output
    OUTPUT=$(networkQuality -k -C https://localhost:1000/.well-known/nq 2>&1)

    # Extract Downlink and Uplink values using grep and awk
    DOWNLINK=$(echo "$OUTPUT" | grep "Downlink capacity:" | awk '{print $3}')
    DOWNLINK_RPM=$(echo "$OUTPUT" | grep "Responsiveness:" | awk '{print $3}' | tr -d '()')
    UPLINK=$(echo "$OUTPUT" | grep "Uplink capacity:" | awk '{print $3}')
    UPLINK_RPM=$(echo "$OUTPUT" | grep "Responsiveness:" | awk '{print $3}' | tr -d '()')

    # Extract RPM value (Responsiveness)
    RPM=$(echo "$OUTPUT" | grep "Responsiveness:" | awk '{print $2}' | tr -d '()')

    # Move cursor to the beginning of the line and overwrite
    printf "\rDownlink: %s, %s RPM - Uplink: %s, %s RPM" "$DOWNLINK" "$RPM" "$UPLINK" "$RPM"

    # Sleep for the specified interval
    sleep $INTERVAL
done