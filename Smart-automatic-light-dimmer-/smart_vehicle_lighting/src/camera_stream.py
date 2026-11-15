"""
Camera Stream Module for ESP32-CAM AI-Thinker & Laptop Webcam
Supports:
- Robust MJPEG streaming over HTTP chunked multipart protocol (:81/stream)
- Automatic fallback to Laptop Webcam (cv2.VideoCapture(0)) or Synthetic Road
- Manual interactive controls:
    [H] - Toggle oncoming headlights ON / OFF (No automatic 2s switching!)
    [O] - Toggle road obstacle ON / OFF
    [W] - Switch to Laptop Webcam
    [E] - Switch to ESP32-CAM stream
"""

import time
import threading
import logging
import cv2
import numpy as np
import requests

logger = logging.getLogger(__name__)

class CameraStream:
    def __init__(self, config: dict):
        self.stream_url = config.get("stream_url", "http://10.77.169.249:81/stream")
        self.capture_url = config.get("capture_url", "http://10.77.169.249/capture")
        self.reconnect_delay = config.get("reconnect_delay_sec", 2.0)
        self.timeout = config.get("request_timeout_sec", 3.0)
        self.frame_width = config.get("frame_width", 640)
        self.frame_height = config.get("frame_height", 480)

        self._current_frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._is_connected = False
        self._is_mock_active = False
        self._is_webcam_active = False
        self._frame_count = 0
        self._fps_start_time = time.time()
        self._fps = 0.0

        # Interactive controls for demonstration (NO auto 2-second ghost switching)
        self.interactive_headlight = False
        self.interactive_obstacle = False
        self.preferred_source = "AUTO"  # "AUTO", "ESP32_CAM", "WEBCAM", "MOCK"
        self._sim_approach_step = 0
        self._current_frame = self._generate_controlled_night_frame()

    def start(self):
        """Starts background frame ingestion."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_worker, daemon=True, name="CameraWorker")
        self._thread.start()
        logger.info(f"CameraStream started (target: {self.stream_url})")

    def stop(self):
        """Stops background capture thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        logger.info("CameraStream stopped")

    def read(self):
        """Returns the most recent decoded frame (BGR np.ndarray) and connection status."""
        with self._lock:
            if self._current_frame is not None:
                return True, self._current_frame.copy(), self._is_connected, self._is_mock_active
            return False, None, self._is_connected, self._is_mock_active

    def is_connected(self) -> bool:
        return self._is_connected

    def is_mock(self) -> bool:
        return self._is_mock_active

    def is_webcam(self) -> bool:
        return self._is_webcam_active

    def get_fps(self) -> float:
        return self._fps

    def toggle_headlight(self) -> bool:
        if self.preferred_source != "MOCK":
            self.preferred_source = "MOCK"
            self._is_webcam_active = False
            self._is_mock_active = True
        self.interactive_headlight = not self.interactive_headlight
        logger.info(f"Interactive simulated headlight: {'ON' if self.interactive_headlight else 'OFF'}")
        return self.interactive_headlight

    def toggle_obstacle(self) -> bool:
        if self.preferred_source != "MOCK":
            self.preferred_source = "MOCK"
            self._is_webcam_active = False
            self._is_mock_active = True
        self.interactive_obstacle = not self.interactive_obstacle
        logger.info(f"Interactive simulated obstacle: {'ON' if self.interactive_obstacle else 'OFF'}")
        return self.interactive_obstacle

    def set_source(self, source_name: str):
        self.preferred_source = source_name.upper()
        logger.info(f"Switched preferred camera source to: {self.preferred_source}")

    def _capture_worker(self):
        """Captures from preferred source: ESP32-CAM -> Laptop Webcam -> Synthetic Road."""
        while self._running:
            if self.preferred_source == "WEBCAM":
                self._run_webcam_stream()
            elif self.preferred_source == "MOCK":
                self._run_mock_stream()
            else:
                # AUTO: Try physical ESP32-CAM first
                connected = self._try_stream()
                if not connected and self._running:
                    # If ESP32-CAM is offline, run steady synthetic mock until reconnected
                    self._run_mock_stream()

    def _try_stream(self) -> bool:
        """Attempts connection via standard OpenCV VideoCapture or HTTP requests."""
        # Fast probe to prevent 30s OpenCV network freeze if ESP32-CAM is offline
        try:
            r = requests.get(self.capture_url, timeout=0.8)
            if r.status_code != 200:
                return False
        except Exception:
            return False

        # 1. Standard OpenCV VideoCapture
        try:
            cap = cv2.VideoCapture(self.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if cap.isOpened():
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    logger.info("Connected to ESP32-CAM via OpenCV VideoCapture")
                    self._is_connected = True
                    self._is_mock_active = False
                    self._is_webcam_active = False

                    while self._running and self.preferred_source in ["AUTO", "ESP32_CAM"]:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break
                        self._store_frame(frame)
                    cap.release()
                    self._is_connected = False
                    return False
                cap.release()
        except Exception:
            pass

        # 2. Robust MJPEG Multipart Parser using requests
        try:
            with requests.get(self.stream_url, stream=True, timeout=self.timeout) as response:
                if response.status_code == 200:
                    self._is_connected = True
                    self._is_mock_active = False
                    self._is_webcam_active = False
                    logger.info("HTTP MJPEG stream established with ESP32-CAM")
                    bytes_data = bytes()

                    for chunk in response.iter_content(chunk_size=4096):
                        if not self._running or self.preferred_source not in ["AUTO", "ESP32_CAM"]:
                            break
                        bytes_data += chunk
                        a = bytes_data.find(b'\xff\xd8')
                        b = bytes_data.find(b'\xff\xd9')

                        if a != -1 and b != -1:
                            jpg = bytes_data[a:b+2]
                            bytes_data = bytes_data[b+2:]
                            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                self._store_frame(frame)
                    self._is_connected = False
                    return False
        except Exception:
            pass

        self._is_connected = False
        return False

    def _run_webcam_stream(self):
        """Streams directly from the host laptop's physical webcam (index 0)."""
        logger.info("Opening local laptop webcam (index 0)...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.warning("Could not open laptop webcam; falling back to mock stream")
            self.preferred_source = "MOCK"
            return

        self._is_webcam_active = True
        self._is_connected = True
        self._is_mock_active = False

        while self._running and self.preferred_source == "WEBCAM":
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue
            self._store_frame(frame)
            time.sleep(0.03)

        cap.release()
        self._is_webcam_active = False

    def _run_mock_stream(self):
        """
        Generates steady synthetic nighttime road frames.
        NO AUTOMATIC SWITCHING:
        - Calm, steady dark road by default.
        - Headlights appear ONLY when user presses 'H'.
        - Road obstacles appear ONLY when user presses 'O'.
        """
        self._is_mock_active = True
        self._is_connected = False
        self._is_webcam_active = False
        logger.info("Operating in Controlled Interactive Demonstration Mode (No auto-cycling)")

        last_check_time = time.time()

        while self._running and self.preferred_source in ["AUTO", "MOCK"]:
            if self.interactive_headlight:
                self._sim_approach_step += 1
            else:
                self._sim_approach_step = 0

            frame = self._generate_controlled_night_frame()
            self._store_frame(frame)
            time.sleep(0.04) # ~25 FPS

            # In AUTO mode, probe real camera periodically
            if self.preferred_source == "AUTO" and (time.time() - last_check_time > 6.0):
                last_check_time = time.time()
                try:
                    r = requests.get(self.capture_url, timeout=0.8)
                    if r.status_code == 200:
                        logger.info("ESP32-CAM reachable! Switching to live camera stream...")
                        self._is_mock_active = False
                        break
                except Exception:
                    pass

    def _generate_controlled_night_frame(self) -> np.ndarray:
        """Renders steady nighttime road with user-controlled interactive headlights/obstacles."""
        h, w = self.frame_height, self.frame_width
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Ambient dark road background
        frame[:] = (10, 10, 10)

        # Road boundaries and lane perspective
        pts_road = np.array([[w * 0.15, h], [w * 0.42, h * 0.45], [w * 0.58, h * 0.45], [w * 0.85, h]], np.int32)
        cv2.fillPoly(frame, [pts_road], (22, 22, 22))

        # Lane markings
        for y in range(int(h * 0.45), h, 35):
            scale = (y - h * 0.45) / (h * 0.55)
            cx = int(w * 0.5)
            line_w = max(1, int(4 * scale))
            cv2.line(frame, (cx, y), (cx, y + 15), (160, 160, 160), line_w)

        # Overhead streetlight (static, in upper 10% sky zone to verify rejection)
        cv2.circle(frame, (int(w * 0.82), int(h * 0.08)), 6, (180, 230, 255), -1)
        cv2.circle(frame, (int(w * 0.82), int(h * 0.08)), 16, (50, 70, 80), 1)

        # 1. Interactive Oncoming Headlights (Activated ONLY when user presses 'H')
        if self.interactive_headlight:
            # Gradually approaches based on simulation step
            progress = min(1.0, 0.35 + (self._sim_approach_step % 120) / 130.0)
            vy = int(h * 0.48 + (h * 0.30) * (progress ** 1.3))
            vx = int(w * 0.46 - (w * 0.12) * (progress ** 1.1))
            beam_radius = max(15, int(28 * progress))
            headlight_separation = max(28, int(56 * progress))

            # Left and right headlights
            for hx in [vx - headlight_separation // 2, vx + headlight_separation // 2]:
                cv2.circle(frame, (hx, vy), int(beam_radius * 1.8), (140, 180, 220), -1)
                cv2.circle(frame, (hx, vy), beam_radius, (255, 255, 255), -1)

            cv2.putText(frame, "[SIMULATED ONCOMING HEADLIGHT ACTIVE]", (15, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        # 2. Interactive Obstacle (Activated ONLY when user presses 'O')
        if self.interactive_obstacle:
            ox = int(w * 0.60)
            oy = int(h * 0.60)
            cv2.rectangle(frame, (ox, oy), (ox + 70, oy + 80), (60, 60, 160), -1)
            cv2.putText(frame, "[SIMULATED ROAD OBSTACLE ACTIVE]", (15, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

        # Watermark & Control Hints
        cv2.putText(frame, "[CAMERA STANDBY - PRESS 'H': HEADLIGHT | 'W': WEBCAM | 'E': ESP32-CAM]",
                    (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1)

        # Subtle noise
        noise = np.random.normal(0, 2, (h, w, 3)).astype(np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        return frame

    def _store_frame(self, frame: np.ndarray):
        with self._lock:
            self._current_frame = frame
            self._frame_count += 1
            now = time.time()
            elapsed = now - self._fps_start_time
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start_time = now
