"""
Hardware Detection & Connection Utility
Checks:
1. Active USB Serial COM ports (identifies ESP32 DevKit COM port)
2. ESP32-CAM Wi-Fi connectivity and stream reachability (10.77.169.249)
3. Automatically offers to update config/config.yaml with detected COM port
"""

import os
import sys
import time
import requests
import yaml

try:
    import serial.tools.list_ports
except ImportError:
    print("[ERROR] pyserial is not installed. Run: pip install pyserial")
    sys.exit(1)

def scan_com_ports():
    ports = list(serial.tools.list_ports.comports())
    return ports

def test_camera_connection(ip_url: str) -> bool:
    try:
        r = requests.get(ip_url, timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

def main():
    print("=" * 60)
    print("  SMART VEHICLE LIGHTING - HARDWARE INTEGRATION CHECK")
    print("=" * 60)

    # 1. Check Serial USB Ports
    print("\n[1] Scanning USB Serial Ports for ESP32 DevKit...")
    ports = scan_com_ports()
    detected_esp32_port = None

    if not ports:
        print("  [!] No USB Serial COM ports detected.")
        print("      -> Please plug the ESP32 DevKit into a USB port on this laptop.")
        print("      -> Ensure the micro-USB cable supports data (not charge-only).")
        print("      -> If needed, install the CH340 or CP2102 USB driver.")
    else:
        print(f"  [+] Found {len(ports)} connected serial port(s):")
        for p in ports:
            print(f"      - Port: {p.device} | Description: {p.description} | HWID: {p.hwid}")
            # Common ESP32 USB chip keywords
            desc_lower = (p.description + " " + p.hwid).lower()
            if any(k in desc_lower for k in ["cp210", "ch340", "ch341", "usb-serial", "uart", "silicon labs", "wch"]):
                detected_esp32_port = p.device

        if detected_esp32_port:
            print(f"  [OK] Likely ESP32 DevKit detected on: {detected_esp32_port}")
        else:
            detected_esp32_port = ports[0].device
            print(f"  [INFO] Defaulting to first available port: {detected_esp32_port}")

    # 2. Check ESP32-CAM Wi-Fi
    print("\n[2] Checking ESP32-CAM Network Stream...")
    cam_capture_url = "http://10.77.169.249/capture"
    cam_stream_url = "http://10.77.169.249:81/stream"
    print(f"  Probing {cam_capture_url}...")

    is_cam_online = test_camera_connection(cam_capture_url)
    if is_cam_online:
        print("  [OK] ESP32-CAM is ONLINE and streaming video!")
    else:
        print("  [!] ESP32-CAM is not reachable at 10.77.169.249.")
        print("      -> Ensure your laptop is connected to the same Wi-Fi network/hotspot as the ESP32-CAM.")
        print("      -> Verify the ESP32-CAM is powered with a stable 5V (>= 1.5A) power source.")
        print("      -> Check the serial monitor of ESP32-CAM to confirm its current assigned IP address.")

    # 3. Update config.yaml if a valid port was found
    if detected_esp32_port:
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))
        try:
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)

            current_port = cfg.get("serial", {}).get("port")
            if current_port != detected_esp32_port:
                cfg["serial"]["port"] = detected_esp32_port
                with open(config_path, "w") as f:
                    yaml.dump(cfg, f, sort_keys=False)
                print(f"\n[OK] Updated config/config.yaml serial.port from '{current_port}' to '{detected_esp32_port}'")
            else:
                print(f"\n[OK] config/config.yaml is already configured with {detected_esp32_port}.")
        except Exception as e:
            print(f"  [!] Note: Could not auto-update config.yaml ({config_path}): {e}")

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"  ESP32 DevKit USB Port : {detected_esp32_port or 'DISCONNECTED'}")
    print(f"  ESP32-CAM Camera      : {'CONNECTED' if is_cam_online else 'OFFLINE / DIFFERENT WI-FI'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
