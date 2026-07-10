echo "=== IPv4 Network Info ===" && \
interface=$(route get default | grep interface | awk '{print $2}') && \
ip=$(ipconfig getifaddr $interface) && \
mask_hex=$(ifconfig $interface | grep netmask | awk '{print $4}') && \
mask=$(printf "%d.%d.%d.%d\n" \
  $((mask_hex >> 24 & 255)) \
  $((mask_hex >> 16 & 255)) \
  $((mask_hex >> 8 & 255)) \
  $((mask_hex & 255))) && \
gateway=$(route -n get default | grep gateway | awk '{print $2}')

echo "Interface   : $interface"
echo "IP Address  : $ip"
echo "Subnet Mask : $mask  (was $mask_hex)"
echo "Gateway     : $gateway"
