"""
Obstacle Detection Module
Detects road objects (cars, motorcycles, buses, trucks, bicycles, pedestrians)
using YOLO (YOLO11n / YOLOv8n) with fallback mode.
"""

import os
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class DetectedObstacle:
    bbox: List[int]      # [x1, y1, x2, y2]
    confidence: float
    class_id: int
    label: str

class ObstacleDetector:
    # Standard COCO / BDD100K class mappings
    CLASS_NAMES = {
        0: "pedestrian",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        5: "bus",
        7: "truck"
    }

    def __init__(self, config: dict):
        self.cfg = config.get("obstacle_detection", {})
        self.model_path = self.cfg.get("model_path", "models/yolo11n.pt")
        self.conf_threshold = self.cfg.get("confidence_threshold", 0.45)
        self.iou_threshold = self.cfg.get("iou_threshold", 0.45)
        self.device = self.cfg.get("device", "cpu")

        self.model = None
        self._is_yolo_loaded = False
        self._init_model()

    def _init_model(self):
        """Attempts to load YOLO model via ultralytics."""
        try:
            from ultralytics import YOLO
            # If specified model path exists or can be downloaded
            if os.path.exists(self.model_path):
                self.model = YOLO(self.model_path)
                self._is_yolo_loaded = True
                logger.info(f"Loaded custom obstacle detector model from {self.model_path}")
            else:
                logger.info(f"Custom model '{self.model_path}' not found on disk. Initializing lightweight YOLO11n...")
                self.model = YOLO("yolo11n.pt")
                self._is_yolo_loaded = True
                logger.info("YOLO11n loaded successfully")
        except Exception as e:
            logger.warning(f"Ultralytics YOLO not initialized ({e}). Using heuristic obstacle fallback.")
            self.model = None
            self._is_yolo_loaded = False

    def detect(self, frame: np.ndarray) -> List[DetectedObstacle]:
        """Runs detection on frame and returns list of DetectedObstacle."""
        if frame is None or frame.size == 0:
            return []

        if self._is_yolo_loaded and self.model is not None:
            return self._detect_yolo(frame)
        else:
            return self._detect_fallback(frame)

    def _detect_yolo(self, frame: np.ndarray) -> List[DetectedObstacle]:
        obstacles = []
        try:
            results = self.model(
                frame,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                device=self.device,
                verbose=False
            )
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                    label = self.CLASS_NAMES.get(cls_id, r.names.get(cls_id, f"obj_{cls_id}"))

                    # Filter for road vehicles & pedestrians
                    if cls_id in self.CLASS_NAMES or label.lower() in ["car", "truck", "bus", "motorcycle", "bicycle", "person", "pedestrian"]:
                        obstacles.append(DetectedObstacle(
                            bbox=[x1, y1, x2, y2],
                            confidence=conf,
                            class_id=cls_id,
                            label=label
                        ))
        except Exception as e:
            logger.error(f"YOLO inference error: {e}")
        return obstacles

    def _detect_fallback(self, frame: np.ndarray) -> List[DetectedObstacle]:
        """
        Lightweight fallback for testing when deep learning model is downloading/compiling:
        Detects road-level dark silhouettes or contrasting shapes.
        """
        obstacles = []
        try:
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Focus on road area (middle-to-bottom third)
            roi_y1 = int(h * 0.40)
            roi = gray[roi_y1:h, :]
            blurred = cv2.GaussianBlur(roi, (5, 5), 0)
            edged = cv2.Canny(blurred, 40, 120)

            contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 2500 < area < 80000:
                    x, y, rw, rh = cv2.boundingRect(cnt)
                    aspect = float(rw) / float(rh) if rh > 0 else 0
                    if 0.6 < aspect < 3.0:
                        obstacles.append(DetectedObstacle(
                            bbox=[x, y + roi_y1, x + rw, y + roi_y1 + rh],
                            confidence=0.55,
                            class_id=2,
                            label="vehicle_candidate"
                        ))
        except Exception:
            pass
        return obstacles
