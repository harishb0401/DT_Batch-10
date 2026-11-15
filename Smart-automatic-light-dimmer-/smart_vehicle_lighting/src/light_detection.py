"""
Light Detection Module: Whole-Frame Intensity Analysis & Trainable Classifier
Implements:
1. Baseline Whole-Frame Image Processing:
   - HSV color space conversion and V-channel / Luminance extraction
   - Full frame & ROI bright pixel percentage calculation
   - Connected component analysis (area, centroid, aspect ratio, mean/max brightness)
   - Noise & isolated pixel rejection (morphological opening/closing)
   - Vertical spatial filtering (excluding sky/high streetlights and vehicle hood)
   - Temporal smoothing (EMA) and multi-frame hysteresis
2. Trainable Light Classifier (Optional ML model integration)
"""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class BrightRegion:
    contour: np.ndarray
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    centroid: Tuple[int, int]        # (cx, cy)
    area: float
    aspect_ratio: float
    mean_brightness: float
    max_brightness: float
    is_headlight_candidate: bool
    rejection_reason: str = ""

@dataclass
class LightDetectionResult:
    is_approaching_headlight: bool
    confidence: float
    bright_pixel_count: int
    bright_pixel_percent: float
    regions: List[BrightRegion] = field(default_factory=list)
    smoothed_confidence: float = 0.0
    classification_label: str = "NO_LIGHT"
    debug_mask: Optional[np.ndarray] = None
    reason: str = ""
    estimated_distance_m: float = -1.0
    peak_brightness: float = 0.0
    frame_mean_brightness: float = 0.0

class LightDetector:
    def __init__(self, config: dict):
        self.cfg = config.get("light_detection", {})
        
        # Configurable calibration thresholds
        self.min_brightness = self.cfg.get("min_brightness_threshold", 220)
        self.min_area = self.cfg.get("min_bright_region_area", 250)
        self.max_area = self.cfg.get("max_bright_region_area", 120000)
        self.min_pixel_pct = self.cfg.get("min_bright_pixel_percent", 0.05)
        self.min_aspect_ratio = self.cfg.get("min_aspect_ratio", 0.4)
        self.max_aspect_ratio = self.cfg.get("max_aspect_ratio", 4.0)

        # Spatial ROI constraints
        self.ignore_top_fraction = self.cfg.get("ignore_top_fraction", 0.15)
        self.ignore_bottom_fraction = self.cfg.get("ignore_bottom_fraction", 0.05)

        # Temporal smoothing & Hysteresis parameters
        self.confirm_frames = self.cfg.get("confirm_frames", 4)
        self.confirm_time_sec = self.cfg.get("confirm_time_sec", 0.35)
        self.return_time_sec = self.cfg.get("return_time_sec", 2.5)
        self.alpha = self.cfg.get("temporal_smoothing_alpha", 0.35)

        # Classifier options
        self.classifier_enabled = self.cfg.get("classifier_enabled", False)
        self.classifier_model_path = self.cfg.get("classifier_model_path", "models/light_classifier.pt")
        self.classifier = None
        self._load_classifier_if_available()

        # State tracking
        self._smoothed_confidence = 0.0
        self._consecutive_positive_frames = 0
        self._first_candidate_time = 0.0
        self._last_confirmed_headlight_time = 0.0
        self._headlight_confirmed_active = False

    def _load_classifier_if_available(self):
        """Loads optional trained classifier model if configured and present."""
        if not self.classifier_enabled:
            return
        if not os.path.exists(self.classifier_model_path):
            return
        try:
            import pickle
            with open(self.classifier_model_path, "rb") as f:
                self.classifier = pickle.load(f)
            logger.info(f"Loaded light classifier model from {self.classifier_model_path}")
        except Exception:
            try:
                import joblib
                self.classifier = joblib.load(self.classifier_model_path)
                logger.info(f"Loaded light classifier model via joblib from {self.classifier_model_path}")
            except Exception as e:
                logger.warning(f"Trainable light classifier not loaded ({e}). Baseline image processing active.")
                self.classifier = None

    def analyze_frame(self, frame: np.ndarray, obstacles: Optional[List[dict]] = None) -> LightDetectionResult:
        """
        Performs comprehensive whole-frame brightness and headlight candidate analysis.
        Returns LightDetectionResult with full telemetry, contours, and decision justification.
        """
        if frame is None or frame.size == 0:
            return LightDetectionResult(
                is_approaching_headlight=False,
                confidence=0.0,
                bright_pixel_count=0,
                bright_pixel_percent=0.0,
                reason="Empty frame received"
            )

        h, w = frame.shape[:2]
        total_pixels = h * w

        # 1. Color space conversion to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]

        # 2. Binary thresholding for bright pixels
        _, raw_mask = cv2.threshold(v_channel, self.min_brightness, 255, cv2.THRESH_BINARY)

        # 3. Morphological opening to eliminate sensor noise & tiny flickering specks
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # 4. Measure global whole-frame brightness metrics
        bright_pixel_count = int(cv2.countNonZero(cleaned_mask))
        bright_pixel_pct = (bright_pixel_count / total_pixels) * 100.0

        # 5. Connected Component / Contour Analysis
        contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions: List[BrightRegion] = []
        headlight_candidates: List[BrightRegion] = []

        top_cutoff = int(h * self.ignore_top_fraction)
        bottom_cutoff = int(h * (1.0 - self.ignore_bottom_fraction))

        for cnt in contours:
            area = cv2.contourArea(cnt)
            x, y, rw, rh = cv2.boundingRect(cnt)
            cx, cy = x + rw // 2, y + rh // 2
            aspect_ratio = float(rw) / float(rh) if rh > 0 else 0.0

            # Compute regional brightness statistics inside contour
            region_mask = np.zeros(v_channel.shape, dtype=np.uint8)
            cv2.drawContours(region_mask, [cnt], -1, 255, -1)
            mean_val, _, _, _ = cv2.mean(v_channel, mask=region_mask)
            min_val, max_val, _, _ = cv2.minMaxLoc(v_channel, mask=region_mask)

            # Heuristic Filtering
            is_candidate = True
            rejection_reason = ""

            if area < self.min_area:
                is_candidate = False
                rejection_reason = f"Area too small ({area:.1f} < {self.min_area})"
            elif area > self.max_area:
                is_candidate = False
                rejection_reason = f"Area too large ({area:.1f} > {self.max_area})"
            elif cy < top_cutoff and bright_pixel_pct < 1.0:
                # Streetlight or moon rejection (high up in sky)
                is_candidate = False
                rejection_reason = f"Overhead streetlight location (cy={cy} < {top_cutoff})"
            elif cy > bottom_cutoff and bright_pixel_pct < 1.0:
                # Reflection on vehicle hood
                is_candidate = False
                rejection_reason = f"Bonnet reflection (cy={cy} > {bottom_cutoff})"
            elif (aspect_ratio < self.min_aspect_ratio or aspect_ratio > self.max_aspect_ratio) and area < 1000:
                is_candidate = False
                rejection_reason = f"Irregular aspect ratio ({aspect_ratio:.2f})"

            region = BrightRegion(
                contour=cnt,
                bbox=(x, y, rw, rh),
                centroid=(cx, cy),
                area=area,
                aspect_ratio=aspect_ratio,
                mean_brightness=float(mean_val),
                max_brightness=float(max_val),
                is_headlight_candidate=is_candidate,
                rejection_reason=rejection_reason
            )
            regions.append(region)
            if is_candidate:
                headlight_candidates.append(region)

        # 6. Candidate Pair & Spatial Association (Headlights usually come in pairs or correspond to vehicles)
        has_pair = False
        matched_pair_dx = 0
        if len(headlight_candidates) >= 2:
            # Check horizontal alignment and reasonable distance
            for i in range(len(headlight_candidates)):
                for j in range(i + 1, len(headlight_candidates)):
                    c1 = headlight_candidates[i]
                    c2 = headlight_candidates[j]
                    dy = abs(c1.centroid[1] - c2.centroid[1])
                    dx = abs(c1.centroid[0] - c2.centroid[0])
                    # Headlight pair: similar height, reasonable horizontal spread
                    if dy < (h * 0.12) and (w * 0.03) < dx < (w * 0.65):
                        has_pair = True
                        matched_pair_dx = dx
                        break
                if has_pair:
                    break

        # 7. Obstacle detector synergy: Check if bright candidate is inside/near a detected vehicle
        vehicle_overlap = False
        if obstacles:
            for obs in obstacles:
                label = obs.get("label", "").lower()
                if label in ["car", "truck", "bus", "motorcycle"]:
                    bx1, by1, bx2, by2 = obs.get("bbox", [0, 0, 0, 0])
                    for cand in headlight_candidates:
                        cx, cy = cand.centroid
                        if (bx1 - 25) <= cx <= (bx2 + 25) and (by1 - 25) <= cy <= (by2 + 25):
                            vehicle_overlap = True
                            break

        # 8. Compute Instantaneous Frame Confidence
        instant_confidence = 0.0
        reason_parts = []

        if len(headlight_candidates) > 0:
            max_cand_area = max(c.area for c in headlight_candidates)
            max_cand_mean = max(c.mean_brightness for c in headlight_candidates)
            max_cand_peak = max(c.max_brightness for c in headlight_candidates)

            if has_pair:
                base_score = 0.95
                reason_parts.append(f"paired headlights matched (separation={int(matched_pair_dx)}px)")
            elif vehicle_overlap:
                base_score = 0.90
                reason_parts.append("spatially aligned with oncoming vehicle bbox")
            elif max_cand_peak >= 200 and max_cand_area >= self.min_area:
                # Strong oncoming light beam (flashlight / mobile torch / single headlight / motorcycle)
                base_score = 0.85
                reason_parts.append(f"approaching light source detected (area={int(max_cand_area)}px, max={int(max_cand_peak)})")
            elif bright_pixel_pct >= self.min_pixel_pct:
                base_score = 0.70
                reason_parts.append(f"bright glare on camera ({bright_pixel_pct:.2f}% road luminance)")
            else:
                base_score = 0.40
                reason_parts.append(f"low intensity light (area={int(max_cand_area)}px)")

            instant_confidence = min(1.0, base_score)
        elif bright_pixel_pct >= (self.min_pixel_pct * 2) or bright_pixel_count >= 150:
            # Broad oncoming glare hit camera directly (even if contour filter didn't produce candidate)
            instant_confidence = 0.85
            reason_parts.append(f"intense light/glare hitting camera directly ({bright_pixel_pct:.2f}%)")
        else:
            instant_confidence = 0.0
            if bright_pixel_count > 0:
                reason_parts.append("isolated faint light rejected")
            else:
                reason_parts.append("clear dark road")

        # 9. Apply Optional Trainable Classifier if active
        classification_label = "NO_LIGHT"
        if self.classifier_enabled and self.classifier is not None:
            classification_label, ml_conf = self._predict_classifier(v_channel)
            classifier_thresh = self.cfg.get("classifier_confidence_threshold", 0.70)
            if classification_label == "ONCOMING_HEADLIGHT" and ml_conf >= classifier_thresh:
                instant_confidence = max(instant_confidence, ml_conf)
                reason_parts.append(f"ML Classifier: {classification_label} ({ml_conf:.2f})")

        # 10. Temporal Exponential Moving Average (EMA) Smoothing
        self._smoothed_confidence = (self.alpha * instant_confidence) + ((1.0 - self.alpha) * self._smoothed_confidence)

        # 11. Multi-Frame Hysteresis & Persistence Validation (Strictly verified)
        now = time.time()
        is_candidate_frame = (instant_confidence >= 0.50)

        if is_candidate_frame:
            self._consecutive_positive_frames += 1
            if self._first_candidate_time == 0.0:
                self._first_candidate_time = now
        else:
            self._consecutive_positive_frames = 0
            self._first_candidate_time = 0.0

        time_sustained = (now - self._first_candidate_time) if self._first_candidate_time > 0 else 0.0

        # Confirmed condition: Requires consecutive sustained candidate frames
        is_confirmed = (self._consecutive_positive_frames >= self.confirm_frames and time_sustained >= self.confirm_time_sec)
        if is_confirmed:
            self._last_confirmed_headlight_time = now
            self._headlight_confirmed_active = True

        time_since_last_confirmed = (now - self._last_confirmed_headlight_time) if self._last_confirmed_headlight_time > 0 else 999.0

        # Decision rule:
        # 1. Oncoming headlights confirmed
        # 2. Persistence hold ONLY AFTER previous confirmed detection (prevents false 2s ghosts from unconfirmed noise)
        # 3. Otherwise: CLEAR ROAD
        is_approaching = False
        final_reason = ""

        if is_confirmed:
            is_approaching = True
            final_reason = f"Confirmed approaching headlights ({self._consecutive_positive_frames} frames, {time_sustained:.2f}s sustained; {', '.join(reason_parts)})"
        elif self._headlight_confirmed_active and time_since_last_confirmed < self.return_time_sec:
            is_approaching = True
            final_reason = f"Headlight persistence active ({self.return_time_sec - time_since_last_confirmed:.1f}s cooldown remaining)"
        else:
            self._headlight_confirmed_active = False
            is_approaching = False
            final_reason = f"Clear road ahead ({', '.join(reason_parts)})"

        # Calculate optical distance estimation in meters
        est_dist = -1.0
        frame_mean = float(np.mean(v_channel))
        frame_max = float(np.max(v_channel))

        if has_pair and matched_pair_dx > 0:
            # Pair triangulation: d = (focal_length * vehicle_width) / pixel_width
            est_dist = (520.0 * 1.30) / max(float(matched_pair_dx), 8.0)
            est_dist = max(4.0, min(95.0, est_dist))
        elif len(headlight_candidates) > 0:
            closest_cand = max(headlight_candidates, key=lambda c: c.area)
            cx, cy = closest_cand.centroid
            # Road ground-plane perspective estimation
            norm_y = max(0.0, min(1.0, float(cy - top_cutoff) / max(1.0, float(bottom_cutoff - top_cutoff))))
            est_dist = max(4.0, min(95.0, 75.0 * (1.0 - (norm_y ** 0.8)) + 6.0))
        elif obstacles and len(obstacles) > 0:
            closest_obs = max(obstacles, key=lambda o: (o.get("bbox", [0, 0, 0, 0])[2] - o.get("bbox", [0, 0, 0, 0])[0]))
            bx1, by1, bx2, by2 = closest_obs.get("bbox", [0, 0, 0, 0])
            w_box = max(10, bx2 - bx1)
            est_dist = max(3.0, min(80.0, (520.0 * 1.8) / float(w_box)))

        return LightDetectionResult(
            is_approaching_headlight=is_approaching,
            confidence=float(instant_confidence),
            bright_pixel_count=bright_pixel_count,
            bright_pixel_percent=float(bright_pixel_pct),
            regions=regions,
            smoothed_confidence=float(self._smoothed_confidence),
            classification_label=classification_label,
            debug_mask=cleaned_mask,
            reason=final_reason,
            estimated_distance_m=float(est_dist),
            peak_brightness=float(frame_max),
            frame_mean_brightness=float(frame_mean)
        )

    def _predict_classifier(self, v_channel: np.ndarray) -> Tuple[str, float]:
        """Runs the optional trained machine learning model."""
        try:
            # Downsample to fixed feature vector (e.g. 32x32 luminance grid)
            resized = cv2.resize(v_channel, (32, 32)).flatten().reshape(1, -1) / 255.0
            probs = self.classifier.predict_proba(resized)[0]
            pred_idx = int(np.argmax(probs))
            classes = getattr(self.classifier, "classes_", ["NO_LIGHT", "ONCOMING_HEADLIGHT", "STREETLIGHT"])
            label = str(classes[pred_idx])
            conf = float(probs[pred_idx])
            return label, conf
        except Exception:
            return "NO_LIGHT", 0.0
