# USAGE: networkQuality [-C <configuration_url>] [-c] [-d] [-f <comma-separated list>] [-h] [-I <network interface name>] [-k] [-p] [-r host] [-S <port>] [-s] [-u] [-v]
#     -C: Override Configuration URL or path (with scheme file://)
#     -c: Produce computer-readable output
#     -d: Do not run a download test (implies -s)
#     -f: <comma-separated list>: Enforce Protocol selections. Available options:
#         h1: Force-enable HTTP/1.1
#         h2: Force-enable HTTP/2
#         h3: Force-enable HTTP/3 (QUIC)
#         L4S: Force-enable L4S
#         noL4S: Force-disable L4S
#     -h: Show help (this message)
#     -I: Bind test to interface (e.g., en0, pdp_ip0,...)
#     -k: Disable certificate validation
#     -p: Use iCloud Private Relay
#     -r: Connect to host or IP, overriding DNS for initial config request
#     -S: Start and run server on specified port. Other specified options ignored
#     -s: Run tests sequentially instead of parallel upload/download
#     -u: Do not run an upload test (implies -s)
#     -v: Verbose output

# Command to run
networkQuality -s
