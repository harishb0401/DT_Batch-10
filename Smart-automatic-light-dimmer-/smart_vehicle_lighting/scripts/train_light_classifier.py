"""
Light Classifier Training Script
Trains a machine learning classifier to categorize night lighting conditions:
[NO_LIGHT, WEAK_LIGHT, ONCOMING_HEADLIGHT, STREETLIGHT, GLARE_UNCERTAIN]
Supports:
1. Scikit-Learn RandomForestClassifier (when sklearn installed)
2. High-performance Pure-NumPy Softmax / Centroid Classifier (standalone fallback)
Saves model weights to models/light_classifier.pt (or .pkl).
"""

import os
import sys
import glob
import pickle
import argparse
import logging
import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("TrainLightClassifier")

def extract_features(img_path: str) -> np.ndarray:
    """Extracts standardized 32x32 luminance grid feature vector."""
    img = cv2.imread(img_path)
    if img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    # Downsample to 32x32 = 1024 spatial luminance features
    resized = cv2.resize(v, (32, 32)).flatten() / 255.0
    return resized

def load_dataset(data_dir: str):
    X, y = [], []
    categories = sorted([d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))])
    
    for cat in categories:
        img_paths = glob.glob(os.path.join(data_dir, cat, "*.jpg"))
        for p in img_paths:
            feat = extract_features(p)
            if feat is not None:
                X.append(feat)
                y.append(cat)
    return np.array(X), np.array(y), categories

class PureNumpyLightClassifier:
    """Lightweight pure-NumPy Softmax / Nearest Centroid classifier."""
    def __init__(self, classes):
        self.classes_ = list(classes)
        self.centroids_ = {}

    def fit(self, X, y):
        for c in self.classes_:
            mask = (y == c)
            if np.any(mask):
                self.centroids_[c] = np.mean(X[mask], axis=0)
            else:
                self.centroids_[c] = np.zeros(X.shape[1])

    def predict_proba(self, X):
        dists = []
        for c in self.classes_:
            centroid = self.centroids_[c]
            # Euclidean distance to centroid
            d = np.linalg.norm(X - centroid, axis=1)
            dists.append(d)
        dists = np.array(dists).T # shape (N, num_classes)
        # Softmax on negative distances
        neg_d = -dists * 4.0
        exp_d = np.exp(neg_d - np.max(neg_d, axis=1, keepdims=True))
        probs = exp_d / np.sum(exp_d, axis=1, keepdims=True)
        return probs

    def predict(self, X):
        probs = self.predict_proba(X)
        indices = np.argmax(probs, axis=1)
        return np.array([self.classes_[i] for i in indices])

def main():
    parser = argparse.ArgumentParser(description="Train Light Classifier")
    parser.add_argument("--data_dir", default="datasets/light_dataset", help="Dataset directory")
    parser.add_argument("--output_model", default="models/light_classifier.pt", help="Path to save trained model")
    args = parser.parse_args()

    train_dir = os.path.join(args.data_dir, "train")
    val_dir = os.path.join(args.data_dir, "val")

    if not os.path.exists(train_dir):
        logger.error(f"Training dataset not found at {train_dir}. Run prepare_light_dataset.py first.")
        sys.exit(1)

    logger.info("Extracting image features from training set...")
    X_train, y_train, classes = load_dataset(train_dir)
    logger.info(f"Loaded {len(X_train)} training samples across {len(classes)} classes: {classes}")

    logger.info("Extracting image features from validation set...")
    X_val, y_val, _ = load_dataset(val_dir)
    logger.info(f"Loaded {len(X_val)} validation samples.")

    clf = None
    use_sklearn = False
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
        use_sklearn = True
        logger.info("Training Scikit-Learn RandomForestClassifier...")
        clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=12)
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_val)
        acc = accuracy_score(y_val, y_pred)
        logger.info("=" * 60)
        logger.info(f"VALIDATION ACCURACY: {acc * 100:.2f}%")
        logger.info("\nClassification Report:\n" + classification_report(y_val, y_pred, zero_division=0))
        logger.info("Confusion Matrix:\n" + str(confusion_matrix(y_val, y_pred)))
        logger.info("=" * 60)
    except ImportError:
        logger.info("Scikit-Learn not found; using pure-NumPy Multi-Class Centroid Classifier...")
        clf = PureNumpyLightClassifier(classes)
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_val)
        acc = np.mean(y_pred == y_val)
        logger.info("=" * 60)
        logger.info(f"PURE NUMPY CLASSIFIER VALIDATION ACCURACY: {acc * 100:.2f}%")
        logger.info("Sample Predictions:")
        for true_l, pred_l in zip(y_val[:10], y_pred[:10]):
            logger.info(f"  True: {true_l:20s} | Predicted: {pred_l}")
        logger.info("=" * 60)

    # Save model
    os.makedirs(os.path.dirname(args.output_model), exist_ok=True)
    with open(args.output_model, "wb") as f:
        pickle.dump(clf, f)
    logger.info(f"[SUCCESS] Trained light classifier model saved to: {args.output_model}")

if __name__ == "__main__":
    main()
