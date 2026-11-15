"""
Unit Tests for Beam Controller State Machine
"""

import unittest
import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.beam_controller import BeamController, BeamState

class TestBeamController(unittest.TestCase):
    def setUp(self):
        self.config = {
            "sensor_fusion": {
                "conservative_fallback_beam": "LOW",
                "ultrasonic_emergency_dist_cm": 60.0
            }
        }
        self.controller = BeamController(self.config)
        self.controller.min_state_duration_sec = 0.1  # Fast for testing

    def test_initial_state_is_normal_beam(self):
        self.assertEqual(self.controller.current_state, BeamState.NORMAL_BEAM)

    def test_switch_to_low_beam_on_headlight(self):
        time.sleep(0.12)
        decision = self.controller.evaluate(
            headlight_confirmed=True,
            headlight_confidence=0.85,
            ambient_dark=True,
            emergency_obstacle=False,
            is_stream_healthy=True
        )
        self.assertEqual(decision.state, BeamState.LOW_BEAM)
        self.assertEqual(decision.hardware_command, "LOW")

    def test_emergency_obstacle_forces_low_beam(self):
        time.sleep(0.12)
        decision = self.controller.evaluate(
            headlight_confirmed=False,
            headlight_confidence=0.0,
            ambient_dark=True,
            emergency_obstacle=True,
            is_stream_healthy=True
        )
        self.assertEqual(decision.state, BeamState.LOW_BEAM)
        self.assertEqual(decision.hardware_command, "LOW")

    def test_camera_offline_safe_fallback(self):
        time.sleep(0.12)
        decision = self.controller.evaluate(
            headlight_confirmed=False,
            headlight_confidence=0.0,
            ambient_dark=True,
            emergency_obstacle=False,
            is_stream_healthy=False  # Stream failure
        )
        # Conservative policy selects UNCERTAIN with LOW hardware relay command
        self.assertEqual(decision.state, BeamState.UNCERTAIN)
        self.assertEqual(decision.hardware_command, "LOW")

    def test_return_to_normal_beam_after_clear_road(self):
        # First trigger LOW beam
        time.sleep(0.12)
        self.controller.evaluate(
            headlight_confirmed=True,
            headlight_confidence=0.9,
            ambient_dark=True,
            is_stream_healthy=True
        )
        self.assertEqual(self.controller.current_state, BeamState.LOW_BEAM)

        # Clear conditions
        time.sleep(0.12)
        decision = self.controller.evaluate(
            headlight_confirmed=False,
            headlight_confidence=0.0,
            ambient_dark=True,
            is_stream_healthy=True
        )
        self.assertEqual(decision.state, BeamState.NORMAL_BEAM)
        self.assertEqual(decision.hardware_command, "NORMAL")

if __name__ == "__main__":
    unittest.main()
