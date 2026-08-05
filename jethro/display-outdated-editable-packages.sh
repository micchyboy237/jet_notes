pip list -o -e --format=columns
# pip list -o -e --format=columns | awk 'NR>2 {print $1}'