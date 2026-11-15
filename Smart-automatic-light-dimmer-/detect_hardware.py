"""
Proxy script to run detect_hardware.py from workspace root d:\DT
"""
import os
import sys
import subprocess

script_path = os.path.join(os.path.dirname(__file__), "smart_vehicle_lighting", "scripts", "detect_hardware.py")
python_exe = sys.executable

if __name__ == "__main__":
    result = subprocess.run([python_exe, script_path] + sys.argv[1:])
    sys.exit(result.returncode)
