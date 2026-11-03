SCRIPT_DIR="${0:A:h}"
mitmproxy --mode reverse:http://192.168.68.150:8080 --listen-port 8080 -s "${SCRIPT_DIR}/save_json.py"
