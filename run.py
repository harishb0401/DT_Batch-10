"""
Workspace Root entry point to launch the Smart Vehicle Lighting System.
"""
import os
import sys
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
target_dir = os.path.join(current_dir, "Smart-automatic-light-dimmer-", "smart_vehicle_lighting")

if __name__ == "__main__":
    python_exe = sys.executable
    cmd = [python_exe, "-m", "src.main"] + sys.argv[1:]
    result = subprocess.run(cmd, cwd=target_dir)
    sys.exit(result.returncode)

