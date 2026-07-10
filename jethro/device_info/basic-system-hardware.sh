echo "System Hardware:"
system_profiler SPHardwareDataType | grep -E "Model Name|Chip|Total Number of Cores|Memory:"
echo "OS Version: $(sw_vers -productVersion)"

# System Hardware:
#       Model Name: MacBook Air
#       Chip: Apple M1
#       Total Number of Cores: 8 (4 performance and 4 efficiency)
#       Memory: 16 GB
# OS Version: 14.4.1
