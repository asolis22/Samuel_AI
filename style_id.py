# style_id.py
# Two-bucket style ID: Amairani vs UNKNOWN_OTHER

import os
import json
import joblib
from datetime import datetime
from typing import List, Tuple, Optional

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier

DATA_DIR = "style_id_data"
MODEL_PATH = os.path.join(DATA_DIR, "model.joblib")
LABELS_PATH = os.path.join(DATA_DIR, "labels.json")
SAMPLES_PATH = os.path.join(DATA_DIR, "samples.jsonl")

OWNER_ME = "Amairani"
UNKNOWN_BUCKET = "UNKNOWN_OTHER"

# When model's best confidence is below this, treat as uncertain
UNKNOWN_THRESHOLD = 0.65

VECTORIZER = HashingVectorizer(
    analyzer="char",
    ngram_range=(3, 5),
    n_features=2**18,
    alternate_sign=False,
    norm="l2"
)

def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def _default_labels() -> List[str]:
    return [OWNER_ME, UNKNOWN_BUCKET]

def load_labels() -> List[str]:
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, "r", encoding="utf-8") as f:
            labels = json.load(f)
            if OWNER_ME not in labels:
                labels.insert(0, OWNER_ME)
            if UNKNOWN_BUCKET not in labels:
                labels.append(UNKNOWN_BUCKET)
            return labels
    return _default_labels()

def save_labels(labels: List[str]):
    with open(LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2)

def append_sample(text: str, label: str):
    rec = {"ts": datetime.utcnow().isoformat(), "label": label, "text": text}
    with open(SAMPLES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def load_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return SGDClassifier(loss="log_loss", alpha=1e-5, penalty="l2", random_state=42)

def save_model(model):
    joblib.dump(model, MODEL_PATH)

def rebuild_from_samples(labels: List[str]):
    clf = SGDClassifier(loss="log_loss", alpha=1e-5, penalty="l2", random_state=42)

    texts, ys = [], []
    if os.path.exists(SAMPLES_PATH):
        with open(SAMPLES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                texts.append(rec["text"])
                ys.append(rec["label"])

    if not texts:
        return clf

    X = VECTORIZER.transform(texts)
    y = np.array(ys)

    clf.partial_fit(X, y, classes=np.array(labels))
    save_model(clf)
    return clf

def predict_author(model, labels: List[str], text: str) -> Tuple[str, float]:
    if len(labels) < 2 or not hasattr(model, "classes_"):
        return ("UNKNOWN", 0.0)

    X = VECTORIZER.transform([text])
    probs = model.predict_proba(X)[0]
    names = model.classes_.tolist()
    pairs = sorted(zip(names, probs), key=lambda x: x[1], reverse=True)
    best_label, best_prob = pairs[0]

    if float(best_prob) < UNKNOWN_THRESHOLD:
        return ("UNKNOWN", float(best_prob))
    return (best_label, float(best_prob))

def online_update(model, labels: List[str], text: str, label: str):
    X = VECTORIZER.transform([text])
    y = np.array([label])

    # ensure labels are exactly our two buckets
    if OWNER_ME not in labels:
        labels.insert(0, OWNER_ME)
    if UNKNOWN_BUCKET not in labels:
        labels.append(UNKNOWN_BUCKET)

    if not hasattr(model, "classes_"):
        model.partial_fit(X, y, classes=np.array(labels))
    else:
        known = set(model.classes_.tolist())
        if set(labels) != known:
            model = rebuild_from_samples(labels)
            model.partial_fit(X, y)
        else:
            model.partial_fit(X, y)

    append_sample(text, label)
    save_model(model)
    save_labels(labels)
    return model, labels

def bootstrap() -> Tuple[object, List[str]]:
    ensure_dir()
    labels = load_labels()
    save_labels(labels)

    model = load_model()

    # If we have samples, sync model to labels
    if os.path.exists(SAMPLES_PATH) and os.path.getsize(SAMPLES_PATH) > 0:
        model = rebuild_from_samples(labels)

    return model, labels