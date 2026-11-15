"""
Unit Tests for Light Detection Module
"""

import unittest
import numpy as np
import cv2
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.light_detection import LightDetector

class TestLightDetection(unittest.TestCase):
    def setUp(self):
        self.config = {
            "light_detection": {
                "min_brightness_threshold": 220,
                "min_bright_region_area": 100,
                "min_bright_pixel_percent": 0.05,
                "confirm_frames": 2,
                "confirm_time_sec": 0.0,
                "return_time_sec": 1.0,
                "ignore_top_fraction": 0.15,
                "ignore_bottom_fraction": 0.05
            }
        }
        self.detector = LightDetector(self.config)

    def test_dark_frame_produces_no_headlight(self):
        """Pure black/dark frame should report no headlights."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        res = self.detector.analyze_frame(frame)
        self.assertFalse(res.is_approaching_headlight)
        self.assertEqual(res.bright_pixel_count, 0)
        self.assertEqual(len(res.regions), 0)

    def test_single_noisy_pixel_is_rejected(self):
        """Isolated single pixel flashes should be filtered by morphological opening."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Single bright pixel
        frame[240, 320] = (255, 255, 255)
        res = self.detector.analyze_frame(frame)
        self.assertFalse(res.is_approaching_headlight)
        self.assertEqual(res.bright_pixel_count, 0)

    def test_overhead_streetlight_is_rejected(self):
        """Bright light located in upper 15% of frame (sky) should be rejected as streetlight."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Place bright circle in top 5% (y = 20)
        cv2.circle(frame, (320, 20), 15, (255, 255, 255), -1)
        res = self.detector.analyze_frame(frame)
        self.assertFalse(res.is_approaching_headlight)
        self.assertTrue(len(res.regions) > 0)
        # Check rejection reason
        self.assertFalse(res.regions[0].is_headlight_candidate)
        self.assertIn("Overhead streetlight", res.regions[0].rejection_reason)

    def test_genuine_oncoming_headlight_pair_detection(self):
        """Two aligned bright headlights on the road should be detected and confirmed."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Two headlights on the road (y = 280, spread 60px)
        cv2.circle(frame, (280, 280), 12, (255, 255, 255), -1)
        cv2.circle(frame, (340, 280), 12, (255, 255, 255), -1)

        # Analyze frame 1
        res1 = self.detector.analyze_frame(frame)
        self.assertGreater(res1.confidence, 0.5)

        # Analyze frame 2 (satisfies confirm_frames=2)
        res2 = self.detector.analyze_frame(frame)
        self.assertTrue(res2.is_approaching_headlight)
        self.assertIn("Confirmed approaching headlights", res2.reason)
        # Verify optical distance calculation in meters
        self.assertGreater(res2.estimated_distance_m, 0.0)
        self.assertLess(res2.estimated_distance_m, 100.0)
        # Verify light intensity measurement
        self.assertGreater(res2.peak_brightness, 200.0)

    def test_single_frame_glitch_does_not_trigger_persistence(self):
        """A transient 1-frame light burst should NOT trigger the 2-second persistence hold."""
        bright_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.circle(bright_frame, (280, 280), 12, (255, 255, 255), -1)
        cv2.circle(bright_frame, (340, 280), 12, (255, 255, 255), -1)

        dark_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Frame 1: Transient flash
        res1 = self.detector.analyze_frame(bright_frame)
        self.assertFalse(res1.is_approaching_headlight)  # Not confirmed yet (requires 2 frames)

        # Frame 2: Dark frame immediately after
        res2 = self.detector.analyze_frame(dark_frame)
        # Must immediately remain clear road - NOT triggered into 2s persistence!
        self.assertFalse(res2.is_approaching_headlight)
        self.assertIn("Clear road", res2.reason)

    def test_flashlight_on_camera_detected(self):
        """A flashlight shining into the camera lens should immediately trigger confirmed headlight detection."""
        frame = np.full((480, 640, 3), 20, dtype=np.uint8)
        # Torch beam in center
        cv2.circle(frame, (320, 240), 30, (235, 240, 245), -1)

        # Frame 1
        res1 = self.detector.analyze_frame(frame)
        self.assertGreaterEqual(res1.confidence, 0.70)

        # Frame 2 (meets confirm_frames=2)
        res2 = self.detector.analyze_frame(frame)
        self.assertTrue(res2.is_approaching_headlight)
        self.assertGreaterEqual(res2.peak_brightness, 200.0)

if __name__ == "__main__":
    unittest.main()
