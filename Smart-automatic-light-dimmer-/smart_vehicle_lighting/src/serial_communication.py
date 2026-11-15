"""
Serial Communication Module for ESP32 DevKit Lighting Controller
Handles:
- Robust single-instance USB Serial connection (COM14 @ 115200)
- Automatic thread-safe background read/write loops
- Telemetry parsing (LDR, Ultrasonic distance, current hardware beam state)
- Command dispatch (SET:LOW, SET:NORMAL, PING)
- Acknowledgment verification (ACK:LOW, ACK:NORMAL)
- Periodic heartbeat refresh (prevents ESP32 3.0s watchdog fallback)
- Safe mock mode when hardware is disconnected
"""

import time
import threading
import logging
from typing import Optional, Dict, Any

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

logger = logging.getLogger(__name__)

class SerialCommunicator:
    def __init__(self, config: dict):
        self.cfg = config.get("serial", {})
        self.port = self.cfg.get("port", "COM14")
        self.baudrate = self.cfg.get("baudrate", 115200)
        self.timeout = self.cfg.get("timeout_sec", 1.0)
        self.heartbeat_interval = self.cfg.get("heartbeat_interval_sec", 0.25)
        self.allow_mock = self.cfg.get("mock_serial_on_failure", True)

        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._is_connected = False
        self._is_mock = False

        self._lock = threading.Lock()
        self._rx_thread = None
        self._heartbeat_thread = None

        # Telemetry cache
        self.latest_ldr_state = "DARK"
        self.latest_distance_cm = -1.0
        self.latest_hardware_beam = "NORMAL"
        self.latest_control_source = "LOCAL"
        self.last_telemetry_time = 0.0
        self.last_ack = ""

        self.current_desired_beam = "NORMAL"

    def start(self):
        """Starts serial background monitoring and heartbeat threads."""
        if self._running:
            return
        self._running = True

        self._connect()

        self._rx_thread = threading.Thread(target=self._read_worker, daemon=True, name="SerialRxWorker")
        self._rx_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True, name="SerialHeartbeatWorker")
        self._heartbeat_thread.start()

        logger.info(f"SerialCommunicator initialized (target: {self.port} @ {self.baudrate})")

    def stop(self):
        """Gracefully disconnects and stops threads."""
        self._running = False
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._is_connected = False
        logger.info("SerialCommunicator stopped")

    def set_beam(self, beam_state: str) -> bool:
        """Sets desired beam state ('LOW' or 'NORMAL'). Dispatches command to ESP32 on state transition."""
        state = beam_state.upper()
        if state not in ["LOW", "NORMAL"]:
            logger.error(f"Invalid beam state requested: {beam_state}")
            return False

        changed = False
        with self._lock:
            if self.current_desired_beam != state:
                self.current_desired_beam = state
                changed = True

        if changed:
            cmd = f"CMD:{state}\n"
            return self._send_raw(cmd)
        return True

    def send_display_telemetry(self, light_intensity: int, distance_str: str, beam_str: str) -> bool:
        """Sends real-time light intensity & distance metrics to ESP32 for 16x2 LCD display (rate-limited)."""
        now = time.time()
        if hasattr(self, "_last_disp_time") and (now - self._last_disp_time < 0.15):
            return True
        self._last_disp_time = now

        cmd = f"DISP:L={int(light_intensity)},D={distance_str},B={beam_str}\n"
        return self._send_raw(cmd)

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns latest status received from ESP32 DevKit."""
        with self._lock:
            return {
                "hardware_beam": self.latest_hardware_beam,
                "control_source": self.latest_control_source,
                "is_connected": self._is_connected,
                "is_mock": self._is_mock,
                "last_update": self.last_telemetry_time
            }

    def _connect(self) -> bool:
        """Attempts connection to the physical serial port."""
        if not SERIAL_AVAILABLE:
            logger.warning("pyserial is not installed. Falling back to mock serial mode.")
            self._is_mock = True
            self._is_connected = False
            return False

        try:
            # Check available system ports
            available_ports = [p.device for p in serial.tools.list_ports.comports()]
            logger.info(f"Available COM ports: {available_ports}")

            if self.port not in available_ports:
                logger.warning(f"Configured port {self.port} not found in available ports: {available_ports}")
                if self.allow_mock:
                    logger.info("Enabling mock serial mode (hardware disconnected)")
                    self._is_mock = True
                    self._is_connected = False
                    return False

            self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(1.5)  # Allow ESP32 reboot / DTR stabilization
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
            self._is_connected = True
            self._is_mock = False
            logger.info(f"Successfully opened serial port {self.port}")
            return True
        except Exception as e:
            logger.warning(f"Could not connect to {self.port}: {e}")
            self._is_connected = False
            if self.allow_mock:
                self._is_mock = True
            return False

    def _send_raw(self, msg: str) -> bool:
        """Sends raw newline-terminated command string to ESP32."""
        if self._is_mock:
            # Simulate ACK in mock mode
            with self._lock:
                if "LOW" in msg:
                    self.latest_hardware_beam = "LOW"
                    self.last_ack = "ACK:LOW"
                elif "NORMAL" in msg:
                    self.latest_hardware_beam = "NORMAL"
                    self.last_ack = "ACK:NORMAL"
                self.latest_control_source = "REMOTE"
                self.last_telemetry_time = time.time()
            return True

        if not self._is_connected or not self._ser or not self._ser.is_open:
            return False

        try:
            self._ser.write(msg.encode("utf-8"))
            self._ser.flush()
            return True
        except Exception as e:
            logger.error(f"Serial transmission failed: {e}")
            self._is_connected = False
            return False

    def _read_worker(self):
        """Continuously reads telemetry from ESP32 DevKit."""
        while self._running:
            if not self._is_connected:
                if not self._is_mock:
                    time.sleep(2.0)
                    self._connect()
                else:
                    # Mock telemetry generator (simulates dark nighttime and safe distance)
                    time.sleep(0.1)
                    with self._lock:
                        self.latest_ldr_state = "DARK"
                        self.latest_distance_cm = 280.0
                        self.last_telemetry_time = time.time()
                continue

            try:
                line = self._ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    self._parse_line(line)
            except Exception as e:
                logger.warning(f"Serial read error: {e}. Reconnecting...")
                self._is_connected = False
                time.sleep(1.0)

    def _heartbeat_worker(self):
        """Periodically refreshes desired beam state to reset ESP32 3.0s communication watchdog."""
        while self._running:
            time.sleep(self.heartbeat_interval)
            with self._lock:
                desired = self.current_desired_beam
            # Periodically re-assert desired beam
            self._send_raw(f"CMD:{desired}\n")

    def _parse_line(self, line: str):
        """Parses ESP32 DevKit telemetry protocol strings."""
        now = time.time()
        # Telemetry: "DATA:LDR=DARK,DIST=124.5,BEAM=NORMAL,SRC=REMOTE"
        if line.startswith("DATA:"):
            payload = line[5:]
            parts = payload.split(",")
            with self._lock:
                for part in parts:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k = k.strip().upper()
                        v = v.strip().upper()
                        if k == "LDR":
                            self.latest_ldr_state = v
                        elif k == "DIST":
                            try:
                                self.latest_distance_cm = float(v)
                            except ValueError:
                                self.latest_distance_cm = -1.0
                        elif k == "BEAM":
                            self.latest_hardware_beam = v
                        elif k == "SRC":
                            self.latest_control_source = v
                self.last_telemetry_time = now

        elif line.startswith("ACK:"):
            with self._lock:
                self.last_ack = line
                logger.debug(f"Received ACK from ESP32: {line}")
        elif line.startswith("SYSTEM:"):
            logger.info(f"ESP32 Boot message: {line}")
        elif line.startswith("ERR:"):
            logger.warning(f"ESP32 reported error: {line}")
