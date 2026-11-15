"""
Obstacle Dataset Preparation Pipeline
Organizes, converts, and structures datasets for YOLO obstacle detection.
Supports:
1. YOLO directory structure creation (train / val / test)
2. Generating a starter synthetic road dataset for immediate pipeline testing
3. Importing & validating custom labeled images from ESP32-CAM
4. Creating dataset.yaml config for YOLO training
"""

import os
import sys
import argparse
import random
import yaml
import cv2
import numpy as np

# Road obstacle classes
CLASSES = ["pedestrian", "bicycle", "car", "motorcycle", "bus", "truck"]

def create_directory_structure(base_dir: str):
    """Creates train, val, and test splits for images and labels."""
    splits = ["train", "val", "test"]
    for split in splits:
        os.makedirs(os.path.join(base_dir, "images", split), exist_ok=True)
        os.makedirs(os.path.join(base_dir, "labels", split), exist_ok=True)
    print(f"[OK] Directory structure created at: {base_dir}")

def generate_synthetic_sample(output_img_path: str, output_lbl_path: str, img_id: int):
    """
    Generates a realistic synthetic road training sample with bounding box annotations.
    Allows validating the full training pipeline before acquiring large 10GB public datasets.
    """
    w, h = 640, 480
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Dark nighttime background
    img[:] = (15, 12, 10)

    # Road surface
    pts = np.array([[w * 0.1, h], [w * 0.45, h * 0.4], [w * 0.55, h * 0.4], [w * 0.9, h]], np.int32)
    cv2.fillPoly(img, [pts], (25, 25, 25))

    labels = []
    # Place 1-3 vehicles/pedestrians randomly
    num_objects = random.randint(1, 3)
    for _ in range(num_objects):
        cls_id = random.choice([0, 2, 4, 5]) # pedestrian, car, bus, truck
        
        # Position along the road
        depth = random.uniform(0.1, 0.9)
        obj_y = int(h * 0.45 + (h * 0.45) * depth)
        obj_w = int(40 + 120 * depth)
        obj_h = int(30 + 80 * depth)
        if cls_id == 0:  # Pedestrian: taller than wide
            obj_w = int(20 + 30 * depth)
            obj_h = int(50 + 90 * depth)

        obj_x = int(random.uniform(w * 0.25, w * 0.75) - obj_w / 2)
        obj_x = max(10, min(w - obj_w - 10, obj_x))
        obj_y = max(int(h * 0.4), min(h - obj_h - 10, obj_y))

        # Draw vehicle shape
        color = (random.randint(40, 180), random.randint(40, 180), random.randint(40, 180))
        cv2.rectangle(img, (obj_x, obj_y), (obj_x + obj_w, obj_y + obj_h), color, -1)

        # If vehicle, draw headlights/taillights
        if cls_id in [2, 4, 5]:
            hl_r = max(2, int(8 * depth))
            cv2.circle(img, (obj_x + hl_r + 2, obj_y + obj_h - hl_r - 2), hl_r, (230, 255, 255), -1)
            cv2.circle(img, (obj_x + obj_w - hl_r - 2, obj_y + obj_h - hl_r - 2), hl_r, (230, 255, 255), -1)

        # Convert to normalized YOLO format: class x_center y_center width height
        x_c = (obj_x + obj_w / 2.0) / w
        y_c = (obj_y + obj_h / 2.0) / h
        norm_w = obj_w / w
        norm_h = obj_h / h
        labels.append(f"{cls_id} {x_c:.6f} {y_c:.6f} {norm_w:.6f} {norm_h:.6f}")

    # Save image
    cv2.imwrite(output_img_path, img)

    # Save YOLO label txt
    with open(output_lbl_path, "w") as f:
        f.write("\n".join(labels) + "\n")

def create_dataset_yaml(base_dir: str):
    """Writes YOLO dataset.yaml metadata file."""
    yaml_path = os.path.join(base_dir, "dataset.yaml")
    abs_base = os.path.abspath(base_dir).replace("\\", "/")
    
    data = {
        "path": abs_base,
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {i: name for i, name in enumerate(CLASSES)}
    }
    with open(yaml_path, "w") as f:
        yaml.dump(data, f, sort_keys=False)
    print(f"[OK] Generated dataset configuration at: {yaml_path}")

def main():
    parser = argparse.ArgumentParser(description="Prepare YOLO obstacle detection dataset")
    parser.add_argument("--output_dir", default="datasets/obstacle_dataset", help="Output directory")
    parser.add_argument("--generate_starter", action="store_true", default=True,
                        help="Generate a synthetic starter dataset for pipeline verification")
    parser.add_argument("--train_count", type=int, default=30, help="Number of starter training images")
    parser.add_argument("--val_count", type=int, default=10, help="Number of starter validation images")
    parser.add_argument("--test_count", type=int, default=5, help="Number of starter test images")
    args = parser.parse_args()

    create_directory_structure(args.output_dir)

    if args.generate_starter:
        print("[INFO] Generating synthetic starter road scene images and YOLO labels...")
        # Train split
        for i in range(args.train_count):
            img_p = os.path.join(args.output_dir, "images", "train", f"sample_train_{i:04d}.jpg")
            lbl_p = os.path.join(args.output_dir, "labels", "train", f"sample_train_{i:04d}.txt")
            generate_synthetic_sample(img_p, lbl_p, i)

        # Val split
        for i in range(args.val_count):
            img_p = os.path.join(args.output_dir, "images", "val", f"sample_val_{i:04d}.jpg")
            lbl_p = os.path.join(args.output_dir, "labels", "val", f"sample_val_{i:04d}.txt")
            generate_synthetic_sample(img_p, lbl_p, i)

        # Test split
        for i in range(args.test_count):
            img_p = os.path.join(args.output_dir, "images", "test", f"sample_test_{i:04d}.jpg")
            lbl_p = os.path.join(args.output_dir, "labels", "test", f"sample_test_{i:04d}.txt")
            generate_synthetic_sample(img_p, lbl_p, i)

        print(f"[OK] Generated {args.train_count} train, {args.val_count} val, and {args.test_count} test samples.")

    create_dataset_yaml(args.output_dir)
    print("\nDataset preparation complete! You can now run `train_obstacle_model.py`.")

if __name__ == "__main__":
    main()
