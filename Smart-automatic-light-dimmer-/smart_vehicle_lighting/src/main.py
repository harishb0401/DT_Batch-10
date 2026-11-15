"""
Main Application for Smart Vehicle Lighting System
Integrates:
- ESP32-CAM Live Video Stream
- Whole-Frame Brightness & Headlight Detection
- Obstacle Detection (YOLO with heuristic fallback)
- ESP32 DevKit Hardware Serial Communication
- Sensor Fusion & Beam-Control State Machine
- Real-time Diagnostic HUD Overlay & Live Monitoring Window
- Dual Output: Native OpenCV Desktop GUI Window + Localhost Web Dashboard (http://localhost:5000)
- Automated CSV Test Decision Logging
"""

import os
import sys
import time
import csv
import logging
import threading
from datetime import datetime
import cv2
import numpy as np
import yaml

from .camera_stream import CameraStream
from .light_detection import LightDetector, LightDetectionResult
from .obstacle_detection import ObstacleDetector, DetectedObstacle
from .serial_communication import SerialCommunicator
from .sensor_fusion import SensorFusionEngine, FusedDecision

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SmartLightingMain")

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Smart Vehicle Lighting System</title>
    <style>
        :root {
            --bg-dark: #0e1117;
            --card-bg: #161b22;
            --card-border: #30363d;
            --accent-green: #238636;
            --accent-blue: #1f6feb;
            --accent-orange: #d29922;
            --accent-red: #da3633;
            --text-main: #f0f6fc;
            --text-muted: #8b949e;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background-color: var(--bg-dark); color: var(--text-main); min-height: 100vh; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 15px; margin-bottom: 20px; }
        .title { font-size: 24px; font-weight: 700; color: #58a6ff; }
        .subtitle { font-size: 14px; color: var(--text-muted); margin-top: 4px; }
        .status-pill { padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; text-transform: uppercase; }
        .pill-normal { background: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #238636; }
        .pill-low { background: rgba(218, 54, 51, 0.2); color: #f85149; border: 1px solid #da3633; }
        .pill-uncertain { background: rgba(210, 153, 34, 0.2); color: #e3b341; border: 1px solid #d29922; }
        
        .main-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
        @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }
        
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px; }
        .video-container { text-align: center; position: relative; border-radius: 8px; overflow: hidden; background: #000; }
        .video-feed { width: 100%; max-height: 520px; object-fit: contain; display: block; border-radius: 8px; }
        
        .controls-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }
        .btn { flex: 1; min-width: 130px; padding: 10px 14px; border-radius: 6px; border: 1px solid var(--card-border); background: #21262d; color: var(--text-main); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; display: flex; align-items: center; justify-content: center; gap: 6px; }
        .btn:hover { background: #30363d; border-color: #8b949e; }
        .btn-active { background: #1f6feb !important; border-color: #58a6ff !important; color: #fff; }
        .btn-danger { border-color: var(--accent-red); color: #f85149; }
        .btn-danger:hover { background: var(--accent-red); color: #fff; }

        .telemetry-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 15px; }
        .tele-box { background: #0d1117; border: 1px solid var(--card-border); border-radius: 8px; padding: 12px; }
        .tele-label { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; margin-bottom: 4px; }
        .tele-value { font-size: 18px; font-weight: 700; }
        
        .meter-container { height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; margin-top: 8px; }
        .meter-fill { height: 100%; width: 0%; background: #3fb950; transition: width 0.2s, background-color 0.2s; }
        .decision-box { margin-top: 15px; padding: 12px; border-radius: 8px; background: #0d1117; border-left: 4px solid #58a6ff; font-size: 13px; color: #c9d1d9; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">🚗 AI Smart Vehicle Lighting System</div>
            <div class="subtitle">Real-time Computer Vision Headlight Dimmer & Anti-Glare Controller</div>
        </div>
        <div id="beamPill" class="status-pill pill-normal">NORMAL BEAM</div>
    </div>

    <div class="main-grid">
        <div class="card">
            <h3 style="margin-bottom: 12px; font-size: 16px;">Live Augmented Camera Feed</h3>
            <div class="video-container">
                <img src="/video_feed" class="video-feed" alt="Live Camera HUD Stream" onerror="this.alt='Connecting to video stream...'" />
            </div>
            
            <div class="controls-row">
                <button class="btn" id="btnH" onclick="triggerAction('headlight')">🔦 [H] Headlight</button>
                <button class="btn" id="btnO" onclick="triggerAction('obstacle')">🚗 [O] Obstacle</button>
                <button class="btn" id="btnW" onclick="triggerAction('webcam')">📷 [W] Webcam</button>
                <button class="btn" id="btnE" onclick="triggerAction('esp32_cam')">📡 [E] ESP32-CAM</button>
                <button class="btn" id="btnM" onclick="triggerAction('mock')">🧪 [M] Mock Stream</button>
            </div>
        </div>

        <div class="card">
            <h3 style="margin-bottom: 12px; font-size: 16px;">System Telemetry</h3>
            
            <div class="telemetry-grid">
                <div class="tele-box">
                    <div class="tele-label">Beam State</div>
                    <div class="tele-value" id="valBeam">NORMAL_BEAM</div>
                </div>
                <div class="tele-box">
                    <div class="tele-label">Relay (GPIO 26)</div>
                    <div class="tele-value" id="valRelay">HIGH</div>
                </div>
                <div class="tele-box">
                    <div class="tele-label">Est. Distance</div>
                    <div class="tele-value" id="valDistance">-- m</div>
                </div>
                <div class="tele-box">
                    <div class="tele-label">Road Objects</div>
                    <div class="tele-value" id="valObstacles">0</div>
                </div>
                <div class="tele-box">
                    <div class="tele-label">Camera Source</div>
                    <div class="tele-value" id="valSource" style="font-size: 14px;">MOCK DEMO</div>
                </div>
                <div class="tele-box">
                    <div class="tele-label">Stream FPS</div>
                    <div class="tele-value" id="valFPS">0.0</div>
                </div>
            </div>

            <div style="margin-top: 15px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                    <span class="tele-label">Light Intensity</span>
                    <span id="valIntensity" style="font-weight: 700;">0 / 255</span>
                </div>
                <div class="meter-container">
                    <div id="intensityMeter" class="meter-fill"></div>
                </div>
            </div>

            <div class="decision-box">
                <div class="tele-label">Decision Reason</div>
                <div id="valReason" style="margin-top: 4px;">Initializing system components...</div>
            </div>

            <div style="margin-top: 18px; font-size: 12px; color: var(--text-muted); line-height: 1.5;">
                <p><strong>Note:</strong> Keyboard shortcuts [H], [O], [W], [E], [M], [Q] can also be used directly in the OpenCV desktop window.</p>
            </div>
        </div>
    </div>

    <script>
        async function triggerAction(action) {
            try {
                const res = await fetch(`/api/control/${action}`);
                const data = await res.json();
                updateUI();
            } catch(e) {
                console.error("Control error:", e);
            }
        }

        async function updateUI() {
            try {
                const res = await fetch('/api/status');
                const s = await res.json();
                
                document.getElementById('valBeam').innerText = s.beam_state || '--';
                document.getElementById('valRelay').innerText = s.hardware_command || '--';
                document.getElementById('valDistance').innerText = s.distance_m > 0 ? (s.distance_m + ' m') : '-- m (CLEAR)';
                document.getElementById('valObstacles').innerText = s.num_obstacles || '0';
                document.getElementById('valSource').innerText = s.cam_source || 'MOCK';
                document.getElementById('valFPS').innerText = s.fps || '0.0';
                document.getElementById('valIntensity').innerText = (s.light_intensity || 0) + ' / 255';
                document.getElementById('valReason').innerText = s.decision_reason || '--';

                const pct = Math.min(100, Math.round(((s.light_intensity || 0) / 255) * 100));
                const meter = document.getElementById('intensityMeter');
                meter.style.width = pct + '%';
                if (s.light_intensity >= 185) {
                    meter.style.backgroundColor = '#f85149';
                } else if (s.light_intensity >= 120) {
                    meter.style.backgroundColor = '#e3b341';
                } else {
                    meter.style.backgroundColor = '#3fb950';
                }

                const pill = document.getElementById('beamPill');
                if (s.beam_state === 'LOW_BEAM') {
                    pill.className = 'status-pill pill-low';
                    pill.innerText = 'LOW BEAM (DIPPED)';
                } else if (s.beam_state === 'UNCERTAIN') {
                    pill.className = 'status-pill pill-uncertain';
                    pill.innerText = 'UNCERTAIN (SAFE LOW)';
                } else {
                    pill.className = 'status-pill pill-normal';
                    pill.innerText = 'NORMAL BEAM (HIGH)';
                }

                // Button active highlights
                const btnH = document.getElementById('btnH');
                if (s.headlight_active) btnH.classList.add('btn-active');
                else btnH.classList.remove('btn-active');

                const btnO = document.getElementById('btnO');
                if (s.obstacle_active) btnO.classList.add('btn-active');
                else btnO.classList.remove('btn-active');

            } catch(e) {}
        }

        setInterval(updateUI, 400);
        updateUI();
    </script>
</body>
</html>
"""

def load_config(config_path: str = "config/config.yaml") -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

class SmartVehicleLightingApp:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        logger.info("Initializing Smart Vehicle Lighting System...")

        # Initialize sub-modules
        self.camera = CameraStream(self.config.get("camera", {}))
        self.light_detector = LightDetector(self.config)
        self.obstacle_detector = ObstacleDetector(self.config)
        self.serial_comm = SerialCommunicator(self.config)
        self.fusion_engine = SensorFusionEngine(self.config)

        # Logging configuration
        self.log_cfg = self.config.get("logging", {})
        self.csv_enabled = self.log_cfg.get("csv_logging", True)
        self.csv_path = self.log_cfg.get("log_path", "logs/system_decisions.csv")
        self._init_csv_log()

        self._running = False
        self._latest_jpeg = None
        self._latest_state = {
            "beam_state": "NORMAL_BEAM",
            "hardware_command": "NORMAL",
            "decision_reason": "System starting...",
            "confidence": 1.0,
            "light_intensity": 0,
            "distance_m": 0.0,
            "num_obstacles": 0,
            "fps": 0.0,
            "cam_source": "INITIALIZING",
            "serial_status": "DISCONNECTED",
            "headlight_active": False,
            "obstacle_active": False,
        }

    def _init_csv_log(self):
        """Prepares CSV file headers for experimental logging and validation."""
        if not self.csv_enabled:
            return
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "BeamState", "HardwareCommand", "DecisionReason",
                    "Confidence", "LDR", "NumObstacles", "BrightPixelPct",
                    "CameraStatus", "ControlSource"
                ])

    def log_decision_to_csv(self, d: FusedDecision, control_src: str):
        """Appends real-time decision telemetry to CSV."""
        if not self.csv_enabled:
            return
        try:
            with open(self.csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    d.beam_state.value,
                    d.hardware_command,
                    d.decision_reason,
                    f"{d.decision_confidence:.2f}",
                    d.ldr_raw,
                    d.num_obstacles_detected,
                    f"{d.bright_pixel_pct:.2f}",
                    "HEALTHY" if d.is_camera_healthy else "OFFLINE",
                    control_src
                ])
        except Exception as e:
            logger.debug(f"CSV log error: {e}")

    def render_hud(
        self,
        frame: np.ndarray,
        light_res: LightDetectionResult,
        obstacles: list,
        decision: FusedDecision,
        telemetry: dict,
        fps: float
    ) -> np.ndarray:
        """Renders comprehensive real-time augmented HUD overlay."""
        display = frame.copy()
        h, w = display.shape[:2]

        # 1. Draw Bright Regions & Headlight Outlines with Distance Tags
        for reg in light_res.regions:
            x, y, rw, rh = reg.bbox
            if reg.is_headlight_candidate:
                cv2.rectangle(display, (x, y), (x + rw, y + rh), (0, 255, 0), 2)
                cand_tag = f"HEADLIGHT ({int(reg.area)}px)"
                if light_res.estimated_distance_m > 0:
                    cand_tag += f" ~{light_res.estimated_distance_m:.1f}m"
                cv2.putText(display, cand_tag, (x, max(15, y - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            else:
                cv2.rectangle(display, (x, y), (x + rw, y + rh), (0, 140, 255), 1)

        # 2. Draw Detected Obstacles & Bounding Boxes with Distance Tags
        for obs in obstacles:
            bx1, by1, bx2, by2 = obs.bbox
            cv2.rectangle(display, (bx1, by1), (bx2, by2), (255, 100, 0), 2)
            obs_tag = f"{obs.label.upper()} {obs.confidence:.2f}"
            if light_res.estimated_distance_m > 0:
                obs_tag += f" [{light_res.estimated_distance_m:.1f}m]"
            cv2.putText(display, obs_tag, (bx1, max(20, by1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 0), 2)

        # 3. Top Status HUD Panel
        panel_h = 115
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (w, panel_h), (12, 14, 18), -1)
        cv2.addWeighted(overlay, 0.82, display, 0.18, 0, display)

        # Left Column: Beam State & Relay
        beam_color = (0, 255, 60) if decision.beam_state.value == "NORMAL_BEAM" else (0, 80, 255)
        if decision.beam_state.value == "UNCERTAIN":
            beam_color = (0, 220, 255)

        cv2.putText(display, f"BEAM: {decision.beam_state.value}", (15, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72, beam_color, 2)
        cv2.putText(display, f"RELAY (GPIO 26): {decision.hardware_command}", (15, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1)
        cv2.putText(display, f"CONFIDENCE: {decision.decision_confidence:.2f}", (15, 72),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)
        cv2.putText(display, "SENSOR: VISION-ONLY (NO LDR)", (15, 94),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 240, 180), 1)

        # Middle Column: Real-Time Light Intensity Demonstration Gauge
        gauge_x = int(w * 0.36)
        cv2.putText(display, f"LIGHT INTENSITY: {int(light_res.peak_brightness)}/255 (Mean: {light_res.frame_mean_brightness:.1f})",
                    (gauge_x, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1)

        # Intensity Progress Bar
        bar_w = 170
        bar_h = 10
        bar_y = 33
        cv2.rectangle(display, (gauge_x, bar_y), (gauge_x + bar_w, bar_y + bar_h), (60, 60, 60), 1)
        fill_w = int(min(1.0, light_res.peak_brightness / 255.0) * bar_w)

        if light_res.peak_brightness >= 220:
            bar_color = (0, 60, 255)
            light_badge = "[HEADLIGHT GLARE]"
            badge_color = (0, 80, 255)
        elif light_res.peak_brightness >= 140:
            bar_color = (0, 220, 255)
            light_badge = "[MODERATE LIGHT]"
            badge_color = (0, 220, 255)
        else:
            bar_color = (50, 200, 50)
            light_badge = "[AMBIENT NIGHT]"
            badge_color = (0, 220, 100)

        if fill_w > 0:
            cv2.rectangle(display, (gauge_x, bar_y), (gauge_x + fill_w, bar_y + bar_h), bar_color, -1)
        # Threshold marker at 185
        thresh_x = gauge_x + int((185.0 / 255.0) * bar_w)
        cv2.line(display, (thresh_x, bar_y - 2), (thresh_x, bar_y + bar_h + 2), (255, 255, 255), 2)
        cv2.putText(display, light_badge, (gauge_x, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.44, badge_color, 1)

        # Middle Column (Lower): Distance Detection
        dist_str = f"{light_res.estimated_distance_m:.1f} m" if light_res.estimated_distance_m > 0 else "-- m (CLEAR)"
        dist_color = (0, 255, 255) if light_res.estimated_distance_m > 0 else (180, 180, 180)
        cv2.putText(display, f"EST. DISTANCE: {dist_str}", (gauge_x, 82),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, dist_color, 2)
        cv2.putText(display, f"BRIGHT PIXELS: {light_res.bright_pixel_percent:.2f}%", (gauge_x, 102),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 200, 200), 1)

        # Right Column: Connectivity & FPS
        cam_src = "WEBCAM" if self.camera.is_webcam() else ("ESP32-CAM" if self.camera.is_connected() else "MOCK DEMO")
        cam_color = (0, 255, 0) if (self.camera.is_webcam() or self.camera.is_connected()) else (0, 200, 255)
        cv2.putText(display, f"SOURCE: {cam_src}", (int(w * 0.72), 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, cam_color, 1)

        ser_status = f"{telemetry.get('control_source', 'LOCAL')} ({self.serial_comm.port})"
        cv2.putText(display, f"SERIAL: {ser_status}", (int(w * 0.72), 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.putText(display, f"FPS: {fps:.1f}", (int(w * 0.72), 72),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.putText(display, f"ROAD OBJECTS: {len(obstacles)}", (int(w * 0.72), 94),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # Bottom Sub-Panel: Decision & Clickable On-Screen Control Buttons
        bot_h = 60
        cv2.rectangle(display, (0, h - bot_h), (w, h), (14, 16, 20), -1)
        reason_text = f"DECISION: {decision.decision_reason}"
        if len(reason_text) > 95:
            reason_text = reason_text[:92] + "..."
        cv2.putText(display, reason_text, (12, h - 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 240, 255), 1)

        # Render 5 interactive buttons (clickable with mouse or keyboard)
        by1, by2 = h - 28, h - 6
        # Button 1: Webcam
        webcam_active = self.camera.is_webcam()
        c1 = (0, 200, 100) if webcam_active else (50, 50, 50)
        cv2.rectangle(display, (10, by1), (120, by2), c1, -1 if webcam_active else 1)
        cv2.putText(display, "[W] WEBCAM", (16, by2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0) if webcam_active else (220, 220, 220), 1)

        # Button 2: Headlight Toggle
        hl_active = getattr(self.camera, "interactive_headlight", False)
        c2 = (0, 160, 255) if hl_active else (50, 50, 50)
        cv2.rectangle(display, (130, by1), (260, by2), c2, -1 if hl_active else 1)
        cv2.putText(display, "[H] HEADLIGHT", (136, by2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0) if hl_active else (220, 220, 220), 1)

        # Button 3: Obstacle Toggle
        obs_active = getattr(self.camera, "interactive_obstacle", False)
        c3 = (255, 180, 0) if obs_active else (50, 50, 50)
        cv2.rectangle(display, (270, by1), (395, by2), c3, -1 if obs_active else 1)
        cv2.putText(display, "[O] OBSTACLE", (278, by2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0) if obs_active else (220, 220, 220), 1)

        # Button 4: ESP32-CAM
        esp_active = self.camera.is_connected() and not self.camera.is_webcam()
        c4 = (0, 220, 255) if esp_active else (50, 50, 50)
        cv2.rectangle(display, (405, by1), (530, by2), c4, -1 if esp_active else 1)
        cv2.putText(display, "[E] ESP32-CAM", (412, by2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0) if esp_active else (220, 220, 220), 1)

        # Button 5: Exit
        cv2.rectangle(display, (540, by1), (630, by2), (60, 60, 180), 1)
        cv2.putText(display, "[Q] EXIT", (552, by2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 255), 1)

        return display

    def _start_web_server(self, host="0.0.0.0", port=5000):
        """Launches background Flask dashboard on http://localhost:5000."""
        try:
            from flask import Flask, Response, jsonify, render_template_string
            flask_app = Flask(__name__)
            logging.getLogger('werkzeug').setLevel(logging.WARNING)

            @flask_app.route('/')
            def index():
                return render_template_string(DASHBOARD_HTML)

            @flask_app.route('/video_feed')
            def video_feed():
                def generate():
                    while self._running:
                        if self._latest_jpeg is not None:
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + self._latest_jpeg + b'\r\n')
                        time.sleep(0.033)
                return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

            @flask_app.route('/api/status')
            def get_status():
                return jsonify(self._latest_state)

            @flask_app.route('/api/control/<action>', methods=['POST', 'GET'])
            def control(action):
                act = action.lower()
                res = {"action": act, "success": True}
                if act == "headlight":
                    res["active"] = self.camera.toggle_headlight()
                elif act == "obstacle":
                    res["active"] = self.camera.toggle_obstacle()
                elif act == "webcam":
                    self.camera.set_source("WEBCAM")
                elif act == "esp32_cam":
                    self.camera.set_source("ESP32_CAM")
                elif act == "mock":
                    self.camera.set_source("MOCK")
                else:
                    res["success"] = False
                    res["error"] = "Unknown action"
                return jsonify(res)

            web_thread = threading.Thread(
                target=lambda: flask_app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True),
                daemon=True,
                name="FlaskWebDashboard"
            )
            web_thread.start()
            logger.info(f"Localhost Web Dashboard running at http://localhost:{port}")
        except Exception as e:
            logger.warning(f"Could not start web dashboard server: {e}")

    def run(self):
        """Main application execution loop."""
        self._running = True
        logger.info("Starting Camera Stream and Serial Worker...")
        self.camera.start()
        self.serial_comm.start()

        # Start Localhost Web Dashboard
        self._start_web_server(host="0.0.0.0", port=5000)

        window_name = "AI Smart Vehicle Lighting System - ESP32-CAM"
        gui_available = True
        try:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 960, 680)

            def on_mouse_click(event, mx, my, flags, param):
                if event == cv2.EVENT_LBUTTONDOWN:
                    by1 = 452
                    if my >= by1:
                        if 10 <= mx <= 120:
                            self.camera.set_source("WEBCAM")
                            logger.info("Clicked [W] WEBCAM button")
                        elif 130 <= mx <= 260:
                            is_on = self.camera.toggle_headlight()
                            logger.info(f"Clicked [H] HEADLIGHT button: {'ON' if is_on else 'OFF'}")
                        elif 270 <= mx <= 395:
                            is_on = self.camera.toggle_obstacle()
                            logger.info(f"Clicked [O] OBSTACLE button: {'ON' if is_on else 'OFF'}")
                        elif 405 <= mx <= 530:
                            self.camera.set_source("ESP32_CAM")
                            logger.info("Clicked [E] ESP32-CAM button")
                        elif 540 <= mx <= 630:
                            logger.info("Clicked [Q] EXIT button")
                            self._running = False

            cv2.setMouseCallback(window_name, on_mouse_click)
        except Exception as e:
            logger.warning(f"Desktop GUI window unavailable ({e}); running with Localhost Web Dashboard.")
            gui_available = False

        fps_timer = time.time()
        frame_counter = 0
        current_fps = 0.0
        cached_obstacles = []

        try:
            while self._running:
                # 1. Ingest Video Frame
                ret, frame, is_connected, is_mock = self.camera.read()
                is_stream_healthy = ret and (frame is not None)

                if not is_stream_healthy:
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, "CONNECTING TO CAMERA STREAM...", (120, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

                # 2. Run Obstacle Detection (YOLO / Heuristic) every 2 frames for optimal UI responsiveness
                if frame_counter % 2 == 0 and is_stream_healthy:
                    cached_obstacles = self.obstacle_detector.detect(frame)
                obstacles = cached_obstacles

                # 3. Analyze Full-Frame Light Intensity & Optical Distance
                light_res = self.light_detector.analyze_frame(
                    frame,
                    obstacles=[{"label": o.label, "bbox": o.bbox} for o in obstacles]
                )

                # 4. Read Hardware Telemetry
                telemetry = self.serial_comm.get_telemetry()

                # 5. Fuse Inputs & Transition State Machine
                decision = self.fusion_engine.fuse(
                    light_result=light_res,
                    obstacles=obstacles,
                    telemetry=telemetry,
                    is_stream_healthy=is_stream_healthy
                )

                # 6. Dispatch Hardware Command to ESP32 DevKit
                self.serial_comm.set_beam(decision.hardware_command)

                # 7. Dispatch Real-Time Metrics to ESP32 16x2 LCD
                dist_str = f"{light_res.estimated_distance_m:.1f}m" if light_res.estimated_distance_m > 0 else "--m"
                self.serial_comm.send_display_telemetry(
                    int(light_res.peak_brightness),
                    dist_str,
                    decision.hardware_command
                )

                # 8. Record Telemetry to CSV
                self.log_decision_to_csv(decision, telemetry.get("control_source", "LOCAL"))

                # 9. Render HUD Display
                hud_frame = self.render_hud(frame, light_res, obstacles, decision, telemetry, current_fps)

                # Cache JPEG for Web Dashboard stream
                try:
                    _, jpeg_buf = cv2.imencode('.jpg', hud_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    self._latest_jpeg = jpeg_buf.tobytes()
                except Exception:
                    pass

                # Update state for Web Dashboard
                cam_src = "WEBCAM" if self.camera.is_webcam() else ("ESP32-CAM" if self.camera.is_connected() else "MOCK DEMO")
                ser_status = f"{telemetry.get('control_source', 'LOCAL')} ({self.serial_comm.port})"
                self._latest_state = {
                    "beam_state": decision.beam_state.value,
                    "hardware_command": decision.hardware_command,
                    "decision_reason": decision.decision_reason,
                    "confidence": round(float(decision.decision_confidence), 2),
                    "light_intensity": int(light_res.peak_brightness),
                    "mean_brightness": round(float(light_res.frame_mean_brightness), 1),
                    "distance_m": round(float(light_res.estimated_distance_m), 1),
                    "num_obstacles": len(obstacles),
                    "fps": round(float(current_fps), 1),
                    "cam_source": cam_src,
                    "serial_status": ser_status,
                    "headlight_active": getattr(self.camera, "interactive_headlight", False),
                    "obstacle_active": getattr(self.camera, "interactive_obstacle", False),
                }

                # 10. Display on Desktop GUI Window if available
                if gui_available:
                    try:
                        cv2.imshow(window_name, hud_frame)
                    except Exception as e:
                        logger.warning(f"cv2.imshow error: {e}")
                        gui_available = False

                # FPS Calculation
                frame_counter += 1
                if time.time() - fps_timer >= 1.0:
                    current_fps = frame_counter / (time.time() - fps_timer)
                    frame_counter = 0
                    fps_timer = time.time()

                # Interactive User Demonstration Inputs
                key = cv2.waitKey(20) & 0xFF if gui_available else 255
                if not gui_available:
                    time.sleep(0.02)

                if key in [ord('q'), ord('Q'), 27]:
                    logger.info("Exit key pressed by user.")
                    break
                elif key in [ord('h'), ord('H')]:
                    is_on = self.camera.toggle_headlight()
                    logger.info(f"Simulated Headlight: {'ACTIVATED' if is_on else 'DEACTIVATED'}")
                elif key in [ord('o'), ord('O')]:
                    is_on = self.camera.toggle_obstacle()
                    logger.info(f"Simulated Obstacle: {'ACTIVATED' if is_on else 'DEACTIVATED'}")
                elif key in [ord('w'), ord('W')]:
                    self.camera.set_source("WEBCAM")
                    logger.info("Switched to Laptop Webcam")
                elif key in [ord('e'), ord('E')]:
                    self.camera.set_source("ESP32_CAM")
                    logger.info("Switched to ESP32-CAM stream")
                elif key in [ord('m'), ord('M')]:
                    self.camera.set_source("MOCK")
                    logger.info("Switched to Mock Simulator")
                elif key == ord('c'):
                    cv2.imwrite(f"logs/snapshot_{int(time.time())}.jpg", frame)
                    logger.info("Calibration snapshot saved to logs/")

        except KeyboardInterrupt:
            logger.info("Application interrupted by Ctrl+C.")
        finally:
            self.stop()
            if gui_available:
                try:
                    cv2.destroyAllWindows()
                except Exception:
                    pass

    def stop(self):
        """Cleanup resources on exit."""
        self._running = False
        self.camera.stop()
        self.serial_comm.stop()
        logger.info("Smart Vehicle Lighting System shutdown complete.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Smart Vehicle Lighting System")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    app = SmartVehicleLightingApp(config_path=args.config)
    app.run()

if __name__ == "__main__":
    main()
