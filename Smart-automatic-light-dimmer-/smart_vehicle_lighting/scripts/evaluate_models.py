"""
Model Evaluation and Image/Video Inference Benchmark Script
Tests:
1. Obstacle Detection Model on test images / videos
2. Light Intensity & Headlight Detection on test scenes
3. Generates annotated evaluation frames and quantitative metrics
"""

import os
import sys
import argparse
import glob
import logging
import cv2
import numpy as np

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.light_detection import LightDetector
from src.obstacle_detection import ObstacleDetector

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("EvaluateModels")

def evaluate_on_images(image_paths: list, output_dir: str, config: dict):
    os.makedirs(output_dir, exist_ok=True)
    light_detector = LightDetector(config)
    obstacle_detector = ObstacleDetector(config)

    total_images = len(image_paths)
    headlight_detections = 0
    total_obstacles_found = 0

    logger.info(f"Evaluating {total_images} images...")

    for idx, p in enumerate(image_paths):
        frame = cv2.imread(p)
        if frame is None:
            continue

        obstacles = obstacle_detector.detect(frame)
        light_res = light_detector.analyze_frame(
            frame,
            obstacles=[{"label": o.label, "bbox": o.bbox} for o in obstacles]
        )

        if light_res.is_approaching_headlight:
            headlight_detections += 1
        total_obstacles_found += len(obstacles)

        # Draw annotations
        annotated = frame.copy()
        for obs in obstacles:
            bx1, by1, bx2, by2 = obs.bbox
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (255, 120, 0), 2)
            cv2.putText(annotated, f"{obs.label}: {obs.confidence:.2f}", (bx1, max(20, by1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 120, 0), 2)

        for reg in light_res.regions:
            x, y, rw, rh = reg.bbox
            color = (0, 255, 0) if reg.is_headlight_candidate else (0, 165, 255)
            cv2.rectangle(annotated, (x, y), (x + rw, y + rh), color, 2)

        # Header overlay
        header = f"Headlights: {'YES' if light_res.is_approaching_headlight else 'NO'} (Conf: {light_res.smoothed_confidence:.2f}) | Obstacles: {len(obstacles)}"
        cv2.putText(annotated, header, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        out_path = os.path.join(output_dir, os.path.basename(p))
        cv2.imwrite(out_path, annotated)

    logger.info("=" * 60)
    logger.info("BENCHMARK SUMMARY:")
    logger.info(f"  Total Test Frames:            {total_images}")
    logger.info(f"  Frames with Headlights:       {headlight_detections} ({(headlight_detections / max(1, total_images)) * 100:.1f}%)")
    logger.info(f"  Total Obstacles Detected:     {total_obstacles_found}")
    logger.info(f"  Annotated Visuals Saved to:   {output_dir}")
    logger.info("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Evaluate Obstacle and Light Detection Models")
    parser.add_argument("--image_dir", default="datasets/obstacle_dataset/images/test",
                        help="Directory containing test images")
    parser.add_argument("--output_dir", default="logs/evaluation_results",
                        help="Directory to save annotated result images")
    args = parser.parse_args()

    import yaml
    with open("config/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    img_paths = glob.glob(os.path.join(args.image_dir, "*.jpg")) + glob.glob(os.path.join(args.image_dir, "*.png"))
    if not img_paths:
        logger.warning(f"No test images found in {args.image_dir}. Run prepare_obstacle_dataset.py first.")
        sys.exit(0)

    evaluate_on_images(img_paths, args.output_dir, cfg)

if __name__ == "__main__":
    main()
