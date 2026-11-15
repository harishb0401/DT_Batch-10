"""
Sensor Fusion Module
Fuses:
1. Full-frame light intensity measurements (approaching headlights vs noise/streetlights)
2. AI obstacle detections (stationary obstacle vs oncoming vehicle)
3. Camera stream health & optical distance estimation
"""

import time
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from .light_detection import LightDetectionResult
from .obstacle_detection import DetectedObstacle
from .beam_controller import BeamController, BeamDecision, BeamState

logger = logging.getLogger(__name__)

@dataclass
class FusedDecision:
    beam_state: BeamState
    hardware_command: str
    decision_reason: str
    decision_confidence: float
    time_in_state: float
    is_state_transition: bool

    # Sensory context
    num_obstacles_detected: int
    headlight_confirmed: bool
    bright_pixel_pct: float
    peak_brightness: float
    frame_mean_brightness: float
    estimated_distance_m: float
    is_camera_healthy: bool

class SensorFusionEngine:
    def __init__(self, config: dict):
        self.cfg = config.get("sensor_fusion", {})
        self.beam_controller = BeamController(config)

    def fuse(
        self,
        light_result: LightDetectionResult,
        obstacles: List[DetectedObstacle],
        telemetry: Dict[str, Any],
        is_stream_healthy: bool
    ) -> FusedDecision:
        """
        Combines all real-time sensory inputs into a synchronized lighting decision.
        """
        # Nighttime driving condition is vision-driven (camera light intensity)
        ambient_dark = True

        # Headlight condition from full-frame light detection
        headlight_confirmed = light_result.is_approaching_headlight

        # Ambiguity / Uncertainty detection
        uncertainty_flag = False
        uncertainty_reason = ""

        # Example uncertainty: high bright pixels detected near obstacle but confidence is borderline
        if (0.35 <= light_result.confidence <= 0.65) and not headlight_confirmed and len(obstacles) > 0:
            uncertainty_flag = True
            uncertainty_reason = "Ambiguous light near detected object; prioritizing glare safety"

        # State Machine Evaluation
        decision: BeamDecision = self.beam_controller.evaluate(
            headlight_confirmed=headlight_confirmed,
            headlight_confidence=light_result.smoothed_confidence,
            ambient_dark=ambient_dark,
            is_stream_healthy=is_stream_healthy,
            uncertainty_flag=uncertainty_flag,
            detail_reason=light_result.reason
        )

        return FusedDecision(
            beam_state=decision.state,
            hardware_command=decision.hardware_command,
            decision_reason=decision.reason,
            decision_confidence=decision.confidence,
            time_in_state=decision.time_in_state,
            is_state_transition=decision.is_state_transition,
            num_obstacles_detected=len(obstacles),
            headlight_confirmed=headlight_confirmed,
            bright_pixel_pct=light_result.bright_pixel_percent,
            peak_brightness=light_result.peak_brightness,
            frame_mean_brightness=light_result.frame_mean_brightness,
            estimated_distance_m=light_result.estimated_distance_m,
            is_camera_healthy=is_stream_healthy
        )
