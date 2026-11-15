# AI-Based Smart Vehicle Lighting System Using ESP32-CAM

An intelligent automotive headlight beam control system combining real-time computer vision, full-frame light intensity analysis, AI obstacle detection, and sensor fusion to maximize driver nighttime visibility while eliminating glare for oncoming vehicles.

---

## 1. System Architecture

```
+-------------------------------------------------------------+
|                     ESP32-CAM (Wi-Fi)                       |
|   IP: 10.77.169.249 | Stream: :81/stream | Capture: /capture |
+------------------------------+------------------------------+
                               | MJPEG Stream
                               v
+-------------------------------------------------------------+
|                Python Application (Host PC)                 |
|                                                             |
|  +--------------------+         +------------------------+  |
|  | Whole-Frame Light  |         |   Obstacle Detection   |  |
|  | Detection Engine   |         |      (YOLO11n)         |  |
|  | (HSV / Morphology/ |         | (Cars, Buses, Trucks,  |  |
|  | Connected Regions) |         | Pedestrians, Bicycles) |  |
|  +---------+----------+         +-----------+------------+  |
|            |                                |               |
|            +----------------+---------------+               |
|                             |                               |
|                             v                               |
|                 +-----------------------+                   |
|                 | Sensor Fusion Engine  |                   |
|                 |  & Beam State Machine |                   |
|                 | (NORMAL / LOW / UNCT) |                   |
|                 +-----------+-----------+                   |
|                             |                               |
+-----------------------------|-------------------------------+
                              | Serial USB (115200 Baud, COM14)
                              | Commands: "CMD:NORMAL", "CMD:LOW"
                              v
+-------------------------------------------------------------+
|                     ESP32 DevKit Controller                 |
|   Pins: LDR=27, RELAY=26, LCD=21(SDA)/22(SCL)               |
|   Relay: Active-LOW (LOW=Low Beam, HIGH=Normal Beam)        |
|   LCD: 16x2 I2C Display (0x27)                              |
|   Fallback: 3.0s Serial Watchdog -> Autonomous LDR Mode     |
+-------------------------------------------------------------+
```

---

## 2. Hardware Pin Assignments & Verified Wiring

| Component | Pin / Signal | ESP32 DevKit GPIO | Notes |
| :--- | :--- | :--- | :--- |
| **LDR Sensor** | Digital Output | **GPIO 27** | Active LOW when bright ambient light detected |
| **Relay Module** | Control IN | **GPIO 26** | **Active-LOW polarity**: `LOW` = Low Beam, `HIGH` = Normal/High Beam |
| **16×2 LCD (I2C)** | SDA | **GPIO 21** | Standard I2C Data (Address `0x27` or `0x3F`) |
| **16×2 LCD (I2C)** | SCL | **GPIO 22** | Standard I2C Clock |
| **USB Serial** | RX / TX | USB UART | 115200 baud, COM14 (Configurable in `config/config.yaml`) |

*(Ultrasonic sensor removed as per specification. All obstacle and vehicle detections are performed in real-time by the YOLO AI vision pipeline on the host computer).*

> [!IMPORTANT]
> **ESP32-CAM Firmware Unchanged**: The ESP32-CAM AI-Thinker module operates autonomously streaming at `http://10.77.169.249:81/stream`. Its firmware is preserved and accessed strictly over Wi-Fi.

---

## 3. Beam-Control Decision Logic & State Machine

The system implements a deterministic finite state machine with three states:
1. `NORMAL_BEAM` (High Beam): Active when ambient lighting is dark and no oncoming glare-producing vehicle is present.
2. `LOW_BEAM`: Activated immediately when oncoming headlights are confirmed or when an emergency close obstacle is detected.
3. `UNCERTAIN`: Applied when sensor readings conflict or camera disconnection occurs. Follows a **conservative safety policy** that maps to Low Beam to protect other motorists.

### Anti-Chatter & Persistence Rules
* **Activation Threshold**: Requires 4 consecutive frames (0.35s) of sustained headlight confidence $\ge 0.50$ before switching to `LOW_BEAM`. Brief flashlights and single noisy pixels are rejected.
* **Return Delay (Hysteresis)**: Requires light to remain clear for **2.5 seconds** before switching back to `NORMAL_BEAM`.
* **Stationary Obstacle Separation**: A stationary road obstacle ahead maintains `NORMAL_BEAM` so the driver can see and maneuver around it, unless oncoming headlights are detected on that vehicle.

---

## 4. Project Directory Structure

```
smart_vehicle_lighting/
├── config/
│   └── config.yaml                     # Unified system thresholds and endpoints
├── datasets/
│   ├── obstacle_dataset/               # YOLO format images & labels (train/val/test)
│   └── light_dataset/                  # 5-class light intensity samples
├── models/
│   ├── obstacle_detector.pt            # Trained YOLO obstacle detection weights
│   └── light_classifier.pt             # Trained light classifier model
├── scripts/
│   ├── prepare_obstacle_dataset.py     # Generates & prepares YOLO dataset
│   ├── train_obstacle_model.py         # Trains YOLO11n obstacle model & outputs metrics
│   ├── prepare_light_dataset.py        # Generates & structures light dataset
│   ├── train_light_classifier.py       # Trains 5-class light classifier model
│   ├── evaluate_models.py              # Benchmarks models on test images
│   └── collect_camera_images.py        # Captures live calibration frames from ESP32-CAM
├── src/
│   ├── camera_stream.py                # Robust MJPEG parser & mock stream fallback
│   ├── light_detection.py              # Full-frame HSV & connected-component detector
│   ├── obstacle_detection.py           # YOLO inference module
│   ├── sensor_fusion.py                # Fuses Camera, AI, LDR, and Ultrasonic
│   ├── beam_controller.py              # Anti-chatter state machine
│   ├── serial_communication.py         # Serial protocol with ESP32 DevKit
│   └── main.py                         # Full system runner with HUD & CSV logger
├── esp32/
│   └── smart_lighting_controller.ino   # DevKit firmware with watchdog & telemetry
├── tests/
│   ├── test_light_detection.py         # 4 unit tests (noise, streetlights, pairs)
│   ├── test_beam_controller.py         # 5 unit tests (transitions, fallbacks)
│   └── test_serial_protocol.py         # 4 unit tests (telemetry, ACKs, mock)
├── requirements.txt                    # Python package dependencies
└── README.md                           # Documentation
```

---

## 5. Quickstart & Workflow Commands

### 1. Install Python Dependencies
```bash
python -m pip install -r requirements.txt
```

### 2. Run the Unit Test Suite
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### 3. Collect Calibration Frames from ESP32-CAM
```bash
# Manual capture mode (press Spacebar to save frame, Q to quit)
python scripts/collect_camera_images.py --mode manual

# Auto capture every 2 seconds
python scripts/collect_camera_images.py --mode auto --interval 2.0
```

### 4. Prepare Datasets
```bash
python scripts/prepare_obstacle_dataset.py
python scripts/prepare_light_dataset.py
```

### 5. Train the Models
```bash
# Train the light classification model
python scripts/train_light_classifier.py

# Train the YOLO obstacle detector (lightweight YOLO11n)
python scripts/train_obstacle_model.py --epochs 10 --batch 4
```

### 6. Evaluate Models on Test Data
```bash
python scripts/evaluate_models.py
```

### 7. Run the Full Live System
```bash
python -m src.main
```
*Note: If the physical ESP32 DevKit or ESP32-CAM is not connected, the application automatically activates the built-in synthetic night road stream and mock serial responder for offline verification.*

---

## 6. Calibration Guide for Nighttime Driving

If the system dims headlights too early or late:
1. Open [`config/config.yaml`](file:///d:/DT/smart_vehicle_lighting/config/config.yaml).
2. Adjust the whole-frame light detection parameters:
   * **`min_brightness_threshold`** (default `220`): Increase to `235` if weak street signs trigger low beam.
   * **`min_bright_region_area`** (default `250`): Increase to `400` to ignore small distant reflections.
   * **`confirm_frames`** (default `4`): Increase to `6` if sudden bumps cause momentary false triggers.
   * **`return_time_sec`** (default `2.5`): Adjust the hold duration before high beam returns.
   * **`ignore_top_fraction`** (default `0.15`): Increase to `0.20` on roads with high streetlights.

---

## 7. Status of System Components

| Component | Status | Verification |
| :--- | :--- | :--- |
| **ESP32 DevKit Firmware** | **COMPLETE** | Non-blocking telemetry, active-LOW relay, 3s watchdog, LCD display |
| **Whole-Frame Light Engine** | **TESTED** | 4 unit tests passing: noise rejection, spatial exclusion, pair detection |
| **Beam State Machine** | **TESTED** | 5 unit tests passing: hysteresis, anti-chatter, conservative fallback |
| **Serial Communication** | **TESTED** | 4 unit tests passing: protocol parsing, telemetry unpacking, ACK check |
| **Light Classifier Model** | **TRAINED** | Model saved to `models/light_classifier.pt` |
| **Obstacle Detection Model** | **INTEGRATED** | YOLO inference pipeline with heuristic fallback |
| **Live HUD & Application** | **COMPLETE** | Live streaming, bounding boxes, telemetry HUD, CSV test logging |
| **Physical Field Testing** | **PENDING** | To be performed on the physical vehicle test track |
