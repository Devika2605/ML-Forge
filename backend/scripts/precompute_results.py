"""
Precomputes ML results for every valid combination of:
  imputation strategy x scaling strategy x feature-toggle set x model

for both datasets, and stores them as a JSON lookup table.

At event time, "RUN MODEL" is just a dictionary lookup against this table —
no live sklearn training happens during the event, which keeps 50
simultaneous teams from ever hammering the server with training jobs.

Also computes and stores a HIDDEN held-out test split's true labels
separately, so the backend can score final submissions against data the
frontend never sees. (This script keeps everything server-side; the CSVs
served to the frontend contain only the public/train split.)
"""
import json
import os
import itertools
import hashlib
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
)

# Model TRAINING itself is done with Orange3 (Orange Data Mining), not raw
# scikit-learn — data prep (imputation/scaling above) and metric scoring
# below still use sklearn/pandas utilities, but the six learners are all
# Orange3 classification learners.
from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable
from Orange.classification import (
    LogisticRegressionLearner, TreeLearner, RandomForestLearner,
    KNNLearner, NaiveBayesLearner, SVMLearner,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "data")

DATASETS = {
    "medivision_x": {
        "csv": "medivision_x.csv",
        "target": "Disease",
        "core_features": [
            "Age", "BMI", "BloodPressure", "Cholesterol", "Glucose",
            "HeartRate", "Exercise_Hours_Week", "Income",
        ],
        "toggle_features": ["Patient_ID", "Leakage_Feature"],
        "missing_numeric": ["BMI", "Income"],
    },
    "fraudnet_x": {
        "csv": "fraudnet_x.csv",
        "target": "Fraud",
        "core_features": [
            "Transaction_Amount", "Account_Age_Days", "Num_Transactions_24h",
            "Avg_Transaction_Amount", "Distance_From_Home_KM", "Hour_Of_Day",
            "Merchant_Category_Code",
        ],
        "toggle_features": ["Transaction_ID", "Leakage_Feature"],
        "missing_numeric": ["Distance_From_Home_KM", "Merchant_Category_Code"],
    },
}

IMPUTATIONS = ["mean", "median", "mode"]  # "remove_rows" handled specially
SCALINGS = ["none", "standardize", "normalize"]

# Orange3 learners. Note: unlike sklearn, Orange's native Tree/SVM/KNN/NaiveBayes
# learners don't all expose a class_weight parameter, so instead of relying on
# per-model class weighting we balance the TRAINING split itself (minority
# oversampling, below) — this keeps recall meaningfully responsive to
# preprocessing decisions across all six models consistently.
MODELS = {
    "logistic_regression": lambda: LogisticRegressionLearner(max_iter=2000, class_weight="balanced"),
    "decision_tree": lambda: TreeLearner(max_depth=6),
    "random_forest": lambda: RandomForestLearner(n_estimators=150, max_depth=8, random_state=42, class_weight="balanced"),
    "knn": lambda: KNNLearner(n_neighbors=7),
    "naive_bayes": lambda: NaiveBayesLearner(),
    "svm": lambda: SVMLearner(probability=True),
}


def _balance_train_split(X: pd.DataFrame, y: pd.Series, seed=42):
    """Oversample the minority class (with replacement) so every model sees
    a balanced training set, regardless of whether it natively supports
    class_weight. Only ever applied to the TRAIN split — the held-out test
    split stays at its real, imbalanced distribution."""
    rng = np.random.default_rng(seed)
    counts = y.value_counts()
    if len(counts) < 2:
        return X, y
    majority_n = counts.max()
    parts_X, parts_y = [X], [y]
    for cls, n in counts.items():
        if n == majority_n:
            continue
        deficit = majority_n - n
        cls_idx = y[y == cls].index
        extra_idx = rng.choice(cls_idx, size=deficit, replace=True)
        parts_X.append(X.loc[extra_idx])
        parts_y.append(y.loc[extra_idx])
    return pd.concat(parts_X, ignore_index=True), pd.concat(parts_y, ignore_index=True)


def _to_orange_table(X: pd.DataFrame, y: pd.Series | None = None):
    domain_x = [ContinuousVariable(c) for c in X.columns]
    if y is None:
        return Table.from_numpy(Domain(domain_x), X.to_numpy(dtype=float))
    domain_y = DiscreteVariable("target", values=["0", "1"])
    return Table.from_numpy(Domain(domain_x, domain_y), X.to_numpy(dtype=float), y.to_numpy(dtype=float))


def config_key(imputation, scaling, feature_flags, model):
    """feature_flags: dict of toggle_feature -> bool (True = included)"""
    flags_str = ",".join(f"{k}={int(v)}" for k, v in sorted(feature_flags.items()))
    raw = f"{imputation}|{scaling}|{flags_str}|{model}"
    return raw


def build_pipeline_data(df, target, core_features, toggle_features, feature_flags,
                         imputation, scaling, missing_numeric):
    features = list(core_features) + [f for f, on in feature_flags.items() if on]
    work = df[features + [target]].copy()

    if imputation == "remove_rows":
        work = work.dropna()
    else:
        for col in missing_numeric:
            if col not in work.columns:
                continue
            if imputation == "mean":
                work[col] = work[col].fillna(work[col].mean())
            elif imputation == "median":
                work[col] = work[col].fillna(work[col].median())
            elif imputation == "mode":
                work[col] = work[col].fillna(work[col].mode().iloc[0])

    work = work.dropna()  # safety net for any remaining NaNs (e.g. toggle cols)

    X = work[features].astype(float)
    y = work[target].astype(int)

    if scaling == "standardize":
        X = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns, index=X.index)
    elif scaling == "normalize":
        X = pd.DataFrame(MinMaxScaler().fit_transform(X), columns=X.columns, index=X.index)

    return X, y


def run_all(dataset_key, cfg):
    df = pd.read_csv(os.path.join(DATA_DIR, cfg["csv"]))
    target = cfg["target"]

    # Fixed train/test split for the WHOLE dataset -> reused across all
    # configs so results are comparable and a hidden test set exists.
    train_idx, test_idx = train_test_split(
        df.index, test_size=0.25, random_state=7, stratify=df[target]
    )

    results = {}
    toggle_combos = list(itertools.product([True, False], repeat=len(cfg["toggle_features"])))

    total = len(IMPUTATIONS) * len(SCALINGS) * len(toggle_combos) * len(MODELS)
    done = 0

    for imputation in IMPUTATIONS + ["remove_rows"]:
        for scaling in SCALINGS:
            for combo in toggle_combos:
                feature_flags = dict(zip(cfg["toggle_features"], combo))

                train_df = df.loc[train_idx]
                test_df = df.loc[test_idx]

                X_train, y_train = build_pipeline_data(
                    train_df, target, cfg["core_features"], cfg["toggle_features"],
                    feature_flags, imputation, scaling, cfg["missing_numeric"]
                )
                X_test, y_test = build_pipeline_data(
                    test_df, target, cfg["core_features"], cfg["toggle_features"],
                    feature_flags, imputation, scaling, cfg["missing_numeric"]
                )

                if len(X_train) < 20 or len(X_test) < 10 or y_train.nunique() < 2:
                    continue  # degenerate config, skip

                X_train_bal, y_train_bal = _balance_train_split(X_train, y_train)
                train_table = _to_orange_table(X_train_bal, y_train_bal)
                test_table_x = _to_orange_table(X_test)

                for model_name, model_fn in MODELS.items():
                    try:
                        learner = model_fn()
                        model = learner(train_table)
                        probs = model(test_table_x, ret=model.Probs)  # [:, 1] = P(class=1)
                        pos_probs = probs[:, 1]
                        preds = (pos_probs >= 0.5).astype(int)

                        acc = accuracy_score(y_test, preds)
                        prec = precision_score(y_test, preds, zero_division=0)
                        rec = recall_score(y_test, preds, zero_division=0)
                        f1 = f1_score(y_test, preds, zero_division=0)
                        cm = confusion_matrix(y_test, preds, labels=[0, 1]).tolist()

                        key = config_key(imputation, scaling, feature_flags, model_name)
                        results[key] = {
                            "accuracy": round(float(acc), 4),
                            "precision": round(float(prec), 4),
                            "recall": round(float(rec), 4),
                            "f1": round(float(f1), 4),
                            "confusion_matrix": cm,
                            "train_rows": int(len(X_train)),
                            "test_rows": int(len(X_test)),
                            "features_used": list(X_train.columns),
                            # stored so the backend can recompute precision/recall/F1
                            # at any threshold LIVE during the event, without retraining
                            "test_probs": [round(float(p), 3) for p in pos_probs],
                            "test_labels": [int(v) for v in y_test],
                        }
                    except Exception as e:
                        pass  # skip configs that fail (e.g. SVM edge cases)
                    done += 1

    print(f"{dataset_key}: computed {len(results)} valid result entries "
          f"out of {total} theoretical combos")
    return results


if __name__ == "__main__":
    all_results = {}
    for key, cfg in DATASETS.items():
        all_results[key] = run_all(key, cfg)

    out_path = os.path.join(DATA_DIR, "precomputed_results.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f)
    print("Saved precomputed results to", out_path)
    total_size_kb = os.path.getsize(out_path) / 1024
    print(f"File size: {total_size_kb:.1f} KB")