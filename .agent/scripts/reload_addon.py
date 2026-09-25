import subprocess
import json
import urllib.request
import re
import sys

def get_blender_pids():
    pids = []
    try:
        # Run tasklist to get PIDs of blender.exe on Windows
        output = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq blender.exe" /FO CSV /NH',
            shell=True,
            stderr=subprocess.DEVNULL
        ).decode('utf-8', errors='ignore')
        
        for line in output.strip().split('\n'):
            parts = line.split(',')
            if len(parts) >= 2:
                pid_str = parts[1].strip('"')
                if pid_str.isdigit():
                    pids.append(int(pid_str))
    except Exception as e:
        print(f"Error getting Blender PIDs: {e}")
    return pids

def get_listening_ports(pids):
    ports = []
    if not pids:
        return ports
    try:
        # Run netstat to get listening ports of these PIDs
        output = subprocess.check_output('netstat -ano', shell=True).decode('utf-8', errors='ignore')
        # Format: TCP    127.0.0.1:50475        0.0.0.0:0              LISTENING       26420
        pattern = re.compile(r'TCP\s+(?:\[::1\]|127\.0\.0\.1|0\.0\.0\.0):(\d+)\s+.*\s+LISTENING\s+(\d+)')
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                port = int(match.group(1))
                pid = int(match.group(2))
                if pid in pids and port not in ports:
                    ports.append(port)
    except Exception as e:
        print(f"Error getting ports: {e}")
    return ports

def reload_addon():
    pids = get_blender_pids()
    if not pids:
        print("Blender is not running.")
        return False
        
    ports = get_listening_ports(pids)
    if not ports:
        print("No listening ports found for Blender.")
        return False

    success = False
    for port in ports:
        # 1. Ping to see if it's our Blender Flask server
        try:
            ping_url = f"http://127.0.0.1:{port}/ping"
            with urllib.request.urlopen(ping_url, timeout=1) as response:
                if response.read().decode().strip() == "OK":
                    print(f"Found Blender Flask server on port {port}")
                    
                    # 2. Send reload request
                    import os
                    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    addon_name = os.path.basename(root_dir)
                    reload_url = f"http://127.0.0.1:{port}/"
                    data = {
                        "type": "reload",
                        "names": [addon_name, "RexTools3", "RexToolsBlender"],
                        "dirs": [root_dir]
                    }
                    body = json.dumps(data).encode("utf-8")
                    req = urllib.request.Request(reload_url, data=body, method="POST")
                    req.add_header("Content-Type", "application/json")
                    with urllib.request.urlopen(req, timeout=2) as reload_resp:
                        if reload_resp.read().decode().strip() == "OK":
                            print("Add-on reload triggered successfully!")
                            success = True
                            break
        except Exception:
            # Silent fail for other ports (like debugpy, which will fail the HTTP request)
            continue
            
    if not success:
        print("Failed to trigger reload. Make sure Blender is running and connected via the VS Code Blender extension.")
        return False
    return True

if __name__ == '__main__':
    reload_addon()
