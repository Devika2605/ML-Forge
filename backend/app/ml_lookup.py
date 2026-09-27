import json
import os
import pandas as pd
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

_precomputed = None
_dataframes = {}


def _load_precomputed():
    global _precomputed
    if _precomputed is None:
        with open(os.path.join(DATA_DIR, "precomputed_results.json")) as f:
            _precomputed = json.load(f)
    return _precomputed


def get_dataframe(dataset_key: str, csv_name: str) -> pd.DataFrame:
    if dataset_key not in _dataframes:
        _dataframes[dataset_key] = pd.read_csv(os.path.join(DATA_DIR, csv_name))
    return _dataframes[dataset_key]


def config_key(imputation, scaling, feature_flags: dict, model: str) -> str:
    flags_str = ",".join(f"{k}={int(v)}" for k, v in sorted(feature_flags.items()))
    return f"{imputation}|{scaling}|{flags_str}|{model}"


def lookup_result(dataset_key: str, imputation, scaling, feature_flags: dict, model: str):
    table = _load_precomputed()
    ds_table = table.get(dataset_key, {})
    key = config_key(imputation, scaling, feature_flags, model)
    return ds_table.get(key)


def recompute_at_threshold(result: dict, threshold: float):
    """Recompute precision/recall/F1/accuracy at an arbitrary decision
    threshold, using ONLY the probabilities already cached in `result` by
    precompute_results.py. No model is touched — this is cheap arithmetic
    over a stored array, safe to call live from many teams at once."""
    probs = result.get("test_probs")
    labels = result.get("test_labels")
    if not probs or not labels:
        return None

    preds = [1 if p >= threshold else 0 for p in probs]
    return {
        "threshold": round(float(threshold), 3),
        "accuracy": round(float(accuracy_score(labels, preds)), 4),
        "precision": round(float(precision_score(labels, preds, zero_division=0)), 4),
        "recall": round(float(recall_score(labels, preds, zero_division=0)), 4),
        "f1": round(float(f1_score(labels, preds, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(labels, preds, labels=[0, 1]).tolist(),
    }