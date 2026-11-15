"""
YOLO Obstacle Detection Model Training Script
Trains a lightweight YOLO model (YOLO11n / YOLOv8n) on road obstacle datasets.
Saves model weights to models/obstacle_detector.pt and evaluates mAP50, mAP50-95, Precision, and Recall.
"""

import os
import sys
import argparse
import logging
import shutil

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("TrainObstacleModel")

def main():
    parser = argparse.ArgumentParser(description="Train YOLO Obstacle Detection Model")
    parser.add_argument("--data", default="datasets/obstacle_dataset/dataset.yaml",
                        help="Path to dataset.yaml")
    parser.add_argument("--model", default="yolo11n.pt",
                        help="Base model to fine-tune (yolo11n.pt or yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=5,
                        help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="Input image resolution")
    parser.add_argument("--batch", type=int, default=4,
                        help="Batch size")
    parser.add_argument("--device", default="cpu",
                        help="Training device ('cpu' or '0' for CUDA GPU)")
    parser.add_argument("--output_model", default="models/obstacle_detector.pt",
                        help="Path to save the best model weights")
    args = parser.parse_args()

    if not os.path.exists(args.data):
        logger.error(f"Dataset config not found at '{args.data}'. Please run 'prepare_obstacle_dataset.py' first.")
        sys.exit(1)

    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics package not installed. Run: pip install ultralytics")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("STARTING OBSTACLE DETECTOR TRAINING PIPELINE")
    logger.info(f"Base Model:       {args.model}")
    logger.info(f"Dataset:          {args.data}")
    logger.info(f"Epochs:           {args.epochs}")
    logger.info(f"Batch Size:       {args.batch}")
    logger.info(f"Image Size:       {args.imgsz}")
    logger.info(f"Device:           {args.device}")
    logger.info("=" * 60)

    # 1. Load base architecture
    model = YOLO(args.model)

    # 2. Train model
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        plots=True,
        verbose=True,
        name="obstacle_detector_run"
    )

    # 3. Evaluate Validation Metrics
    logger.info("\nEvaluating Model on Validation Set...")
    metrics = model.val()

    p = metrics.box.mp       # Mean Precision
    r = metrics.box.mr       # Mean Recall
    map50 = metrics.box.map50 # mAP @ 0.50 IoU
    map = metrics.box.map    # mAP @ 0.50:0.95 IoU

    logger.info("=" * 60)
    logger.info("TRAINING & VALIDATION RESULTS:")
    logger.info(f"  Precision (P):  {p:.4f}")
    logger.info(f"  Recall (R):     {r:.4f}")
    logger.info(f"  mAP@0.50:       {map50:.4f}")
    logger.info(f"  mAP@0.50:0.95:  {map:.4f}")
    logger.info("=" * 60)

    # 4. Save best model weights
    os.makedirs(os.path.dirname(args.output_model), exist_ok=True)
    best_weights_path = getattr(model.trainer, "best", None)
    if best_weights_path and os.path.exists(best_weights_path):
        shutil.copy(best_weights_path, args.output_model)
        logger.info(f"[SUCCESS] Best weights saved to: {args.output_model}")
    else:
        model.save(args.output_model)
        logger.info(f"[SUCCESS] Model saved to: {args.output_model}")

    logger.info(f"Training artifact directory: {model.trainer.save_dir}")
    logger.info("To test model on video or image, run: python scripts/evaluate_models.py")

if __name__ == "__main__":
    main()
