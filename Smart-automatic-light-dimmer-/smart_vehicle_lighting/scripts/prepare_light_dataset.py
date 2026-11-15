"""
Light Classification Dataset Preparation
Prepares structured image dataset for training the optional ML light classifier.
Categories:
- NO_LIGHT: Dark empty nighttime road scenes
- WEAK_LIGHT: Distant low-intensity light sources
- ONCOMING_HEADLIGHT: Strong approaching vehicle headlights
- STREETLIGHT: Overhead streetlights, illuminated billboards, non-vehicle sources
- GLARE_UNCERTAIN: Wet asphalt reflections, high glare, ambiguous illumination
"""

import os
import argparse
import random
import cv2
import numpy as np

CATEGORIES = [
    "NO_LIGHT",
    "WEAK_LIGHT",
    "ONCOMING_HEADLIGHT",
    "STREETLIGHT",
    "GLARE_UNCERTAIN"
]

def generate_light_sample(category: str, output_path: str):
    w, h = 640, 480
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Base nighttime scene
    img[:] = (12, 10, 8)
    pts = np.array([[w * 0.15, h], [w * 0.45, h * 0.45], [w * 0.55, h * 0.45], [w * 0.85, h]], np.int32)
    cv2.fillPoly(img, [pts], (22, 22, 22))

    if category == "NO_LIGHT":
        # Pure dark road, minimal ambient light
        pass

    elif category == "WEAK_LIGHT":
        # Small faint point in distance
        cx, cy = int(w * 0.5), int(h * 0.46)
        cv2.circle(img, (cx, cy), 3, (160, 160, 160), -1)

    elif category == "ONCOMING_HEADLIGHT":
        # Distinct paired bright headlights on road
        cy = int(h * 0.55 + random.randint(-15, 30))
        cx = int(w * 0.45 + random.randint(-20, 20))
        spread = random.randint(30, 70)
        radius = random.randint(12, 26)
        # Left and Right headlights
        for hx in [cx - spread // 2, cx + spread // 2]:
            cv2.circle(img, (hx, cy), radius * 2, (100, 140, 160), -1)
            cv2.circle(img, (hx, cy), radius, (245, 255, 255), -1)

    elif category == "STREETLIGHT":
        # High overhead yellow/orange lamp
        lx = random.choice([int(w * 0.2), int(w * 0.8)])
        ly = int(h * 0.08 + random.randint(0, 15))
        cv2.circle(img, (lx, ly), 18, (120, 180, 220), -1)
        cv2.circle(img, (lx, ly), 7, (200, 240, 255), -1)

    elif category == "GLARE_UNCERTAIN":
        # Diffuse reflection streak across wet asphalt
        for _ in range(4):
            sx = int(random.uniform(w * 0.3, w * 0.7))
            sy = int(random.uniform(h * 0.65, h * 0.9))
            cv2.ellipse(img, (sx, sy), (60, 8), 0, 0, 360, (140, 140, 150), -1)

    # Save sample
    cv2.imwrite(output_path, img)

def main():
    parser = argparse.ArgumentParser(description="Prepare light classification dataset")
    parser.add_argument("--output_dir", default="datasets/light_dataset", help="Output directory")
    parser.add_argument("--samples_per_class", type=int, default=25,
                        help="Number of starter samples to generate per class")
    args = parser.parse_args()

    for split in ["train", "val"]:
        count = args.samples_per_class if split == "train" else max(5, args.samples_per_class // 4)
        for cat in CATEGORIES:
            folder = os.path.join(args.output_dir, split, cat)
            os.makedirs(folder, exist_ok=True)
            for i in range(count):
                out_p = os.path.join(folder, f"{cat.lower()}_{i:04d}.jpg")
                generate_light_sample(cat, out_p)

    print(f"[OK] Light dataset prepared with {len(CATEGORIES)} categories in {args.output_dir}")

if __name__ == "__main__":
    main()
