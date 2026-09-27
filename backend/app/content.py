"""
Static content for ML Forge: dataset metadata, per-dataset answer keys,
twist/incident text, and the Black Box question bank. This is the single
source of truth the scoring engine and mission endpoints read from — kept
out of the DB since it's fixed content, not per-team state.
"""

DATASETS = {
    "medivision_x": {
        "display_name": "MEDIVISION-X",
        "csv": "medivision_x.csv",
        "target": "Disease",
        "target_labels": {"0": "Healthy", "1": "Disease"},
        "core_features": [
            "Age", "BMI", "BloodPressure", "Cholesterol", "Glucose",
            "HeartRate", "Exercise_Hours_Week", "Income",
        ],
        "toggle_features": ["Patient_ID", "Leakage_Feature"],
        "missing_numeric": ["BMI", "Income"],
        "acceptable_imputations": {"BMI": ["mean", "median"], "Income": ["median", "mode"]},
        # An imputation choice counts as "acceptable" overall if it matches
        # the intended technique for the dataset's primary missing column.
        "acceptable_imputation_set": ["median", "mean"],
        "leakage_features": ["Leakage_Feature"],
        "irrelevant_features": ["Patient_ID"],
        "brief": (
            "A hospital diagnostic AI has started producing unreliable "
            "predictions and is scheduled for deployment. Your team has 30 "
            "minutes to investigate, repair, and redeploy it safely."
        ),
    },
    "fraudnet_x": {
        "display_name": "FRAUDNET-X",
        "csv": "fraudnet_x.csv",
        "target": "Fraud",
        "target_labels": {"0": "Legitimate", "1": "Fraud"},
        "core_features": [
            "Transaction_Amount", "Account_Age_Days", "Num_Transactions_24h",
            "Avg_Transaction_Amount", "Distance_From_Home_KM", "Hour_Of_Day",
            "Merchant_Category_Code",
        ],
        "toggle_features": ["Transaction_ID", "Leakage_Feature"],
        "missing_numeric": ["Distance_From_Home_KM", "Merchant_Category_Code"],
        "acceptable_imputation_set": ["median", "mean"],
        "leakage_features": ["Leakage_Feature"],
        "irrelevant_features": ["Transaction_ID"],
        "brief": (
            "A fraud-detection model flagged an unusual spike of missed "
            "cases in a live audit. Your team has 20 minutes to diagnose, "
            "rebuild, and redeploy it under a new incident."
        ),
    },
}

MODEL_INFO = {
    "logistic_regression": "A simple, fast linear model. Good baseline, easy to explain to a client.",
    "decision_tree": "A single tree of yes/no splits. Easy to interpret, prone to overfitting alone.",
    "random_forest": "An ensemble of decision trees. Strong general-purpose model, handles nonlinear patterns.",
    "knn": "Classifies based on the nearest similar records. Simple, but sensitive to scaling.",
    "naive_bayes": "A fast probabilistic model. Works well as a lightweight baseline.",
    "svm": "Finds the best boundary between classes. Can be strong but slower to reason about.",
}

METRIC_INFO = {
    "accuracy": "Percentage of all predictions that were correct. Misleading on imbalanced data.",
    "precision": "Of everything flagged positive, how many were actually positive.",
    "recall": "Of all actual positive cases, how many did the model detect.",
    "f1": "Balance between precision and recall in a single number.",
}

TWISTS = {
    1: {
        "headline": "Missing a sick patient is now more costly. Focus on Recall.",
        "detail": (
            "Double-check nothing in your final features could be giving "
            "the model an unfair shortcut. Your preprocessing and model "
            "choices remain valid — only the priority metric needs to change."
        ),
        "required_metric": "recall",
    },
    2: {
        "headline": "False alarms are now too expensive. Focus on Precision.",
        "detail": (
            "Confirm your current feature set still makes sense for that "
            "goal. Your preprocessing and model choices remain valid — only "
            "the priority metric needs to change."
        ),
        "required_metric": "precision",
    },
}

BLACKBOX_QUESTIONS = [
    {
        "id": "bb01",
        "prompt": (
            "Model A has 97% accuracy. Model B has 92% accuracy but 95% "
            "recall. The system is used for disease detection. Which model "
            "should be deployed?"
        ),
        "options": ["Model A (higher accuracy)", "Model B (higher recall)"],
        "correct_option": "Model B (higher recall)",
        "concept": "Recall matters more than accuracy in imbalanced, high-stakes detection tasks.",
    },
    {
        "id": "bb02",
        "prompt": "Training accuracy = 99%. Testing accuracy = 71%. What is most likely happening?",
        "options": ["Overfitting", "Underfitting", "Data leakage", "Perfect model"],
        "correct_option": "Overfitting",
        "concept": "A large train/test gap indicates the model memorized training data.",
    },
    {
        "id": "bb03",
        "prompt": "Dataset contains 90% Class A and 10% Class B. Is accuracy alone a sufficient metric?",
        "options": ["Yes", "No"],
        "correct_option": "No",
        "concept": "Class imbalance makes accuracy misleading — a model predicting only Class A scores 90%.",
    },
    {
        "id": "bb04",
        "prompt": (
            "A feature is only available after the event being predicted "
            "has already occurred. Should it be used?"
        ),
        "options": ["Yes, if it improves accuracy", "No, it's data leakage"],
        "correct_option": "No, it's data leakage",
        "concept": "Using post-outcome information leaks the answer and won't be available at real prediction time.",
    },
]

ACHIEVEMENTS = {
    "leak_detector": "Identified target leakage",
    "data_miner": "Found all hidden dataset issues",
    "metric_master": "Selected the correct metric after the twist",
    "model_smith": "Built a strong model pipeline",
    "last_stand": "Successfully adapted during the final incident",
}
