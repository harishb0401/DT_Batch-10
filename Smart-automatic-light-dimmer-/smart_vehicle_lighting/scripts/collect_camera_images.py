"""
Image Collection Script for ESP32-CAM
Saves timestamped frames from the live camera stream for:
1. Ground truth calibration (tuning brightness and area thresholds)
2. Expanding the obstacle detection training dataset
3. Expanding the light classification dataset
"""

import os
import sys
import time
import argparse
import logging
import cv2
import yaml

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.camera_stream import CameraStream

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("ImageCollector")

def main():
    parser = argparse.ArgumentParser(description="Collect images from ESP32-CAM for dataset and calibration")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--output_dir", default="datasets/collected_raw", help="Folder to save frames")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between auto-capture frames")
    parser.add_argument("--mode", choices=["manual", "auto"], default="manual",
                        help="'manual' captures on Spacebar, 'auto' captures every N seconds")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    cam = CameraStream(cfg.get("camera", {}))
    cam.start()

    logger.info("Connecting to camera stream...")
    logger.info("Controls:")
    logger.info("  [SPACE] - Capture single frame (in manual mode)")
    logger.info("  [Q/ESC] - Quit collection")

    last_auto_capture = time.time()
    count = 0

    try:
        while True:
            ret, frame, is_connected, is_mock = cam.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            preview = frame.copy()
            status_text = "CAM: LIVE" if is_connected else ("CAM: MOCK" if is_mock else "CAM: OFFLINE")
            cv2.putText(preview, f"{status_text} | Saved: {count}", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(preview, "Press SPACE to save, Q to quit", (15, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("ESP32-CAM Image Collector", preview)
            key = cv2.waitKey(20) & 0xFF

            now = time.time()
            should_save = False

            if args.mode == "manual" and key == 32:  # Spacebar
                should_save = True
            elif args.mode == "auto" and (now - last_auto_capture >= args.interval):
                should_save = True
                last_auto_capture = now

            if should_save:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(args.output_dir, f"frame_{timestamp}_{count:04d}.jpg")
                cv2.imwrite(filename, frame)
                count += 1
                logger.info(f"Captured: {filename}")

            if key == ord('q') or key == 27:
                break

    finally:
        cam.stop()
        cv2.destroyAllWindows()
        logger.info(f"Session finished. Total {count} images saved to {args.output_dir}")

if __name__ == "__main__":
    main()
