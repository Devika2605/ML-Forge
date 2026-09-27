"""
Generates the two ML Forge datasets:
  - MEDIVISION-X (Round 1): hospital diagnosis, imbalanced, with a leakage
    feature, an irrelevant ID column, and missing values.
  - FRAUDNET-X (Round 2): fraud detection, same trap categories, different
    domain so Round 2 doesn't feel like a re-run of Round 1.

Both are saved as CSV under backend/app/data/.
"""
import numpy as np
import pandas as pd
import os

RNG = np.random.default_rng(42)
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "data")
os.makedirs(OUT_DIR, exist_ok=True)


def make_medivision_x(n=1200):
    rng = RNG
    age = rng.integers(18, 85, n)
    bmi = rng.normal(26, 5, n).clip(15, 45)
    blood_pressure = rng.normal(120, 15, n).clip(80, 200)
    cholesterol = rng.normal(200, 35, n).clip(100, 350)
    glucose = rng.normal(100, 25, n).clip(60, 300)
    heart_rate = rng.normal(75, 10, n).clip(45, 130)
    exercise_hours_week = rng.gamma(2, 1.5, n).clip(0, 20)

    # true disease risk score drives the actual target
    risk = (
        0.03 * (age - 50)
        + 0.08 * (bmi - 25)
        + 0.02 * (blood_pressure - 120)
        + 0.015 * (cholesterol - 200)
        + 0.02 * (glucose - 100)
        - 0.05 * exercise_hours_week
    )
    prob = 1 / (1 + np.exp(-0.12 * risk))
    disease = (rng.random(n) < prob * 0.35).astype(int)  # force imbalance ~10-15%

    # TRAP 1: target leakage — this field is only ever set AFTER diagnosis
    # (a prescribed medication code), so it leaks the target almost
    # perfectly. Kept near-deterministic so an "unrealistically good" score
    # is a discoverable, visible clue during investigation.
    leakage_noise = rng.random(n) < 0.04
    leakage_feature = np.where(leakage_noise, 1 - disease, disease)

    # TRAP 2: irrelevant identifier column
    patient_id = np.arange(100000, 100000 + n)

    # TRAP 3: missing values injected into Income (~15%) and BMI (~5%)
    income = rng.normal(45000, 15000, n).clip(10000, 200000)
    missing_income_mask = rng.random(n) < 0.15
    income = income.astype(float)
    income[missing_income_mask] = np.nan

    missing_bmi_mask = rng.random(n) < 0.05
    bmi = bmi.astype(float)
    bmi[missing_bmi_mask] = np.nan

    df = pd.DataFrame({
        "Patient_ID": patient_id,
        "Age": age,
        "BMI": bmi.round(1),
        "BloodPressure": blood_pressure.round(1),
        "Cholesterol": cholesterol.round(1),
        "Glucose": glucose.round(1),
        "HeartRate": heart_rate.round(1),
        "Exercise_Hours_Week": exercise_hours_week.round(1),
        "Income": income.round(0),
        "Leakage_Feature": leakage_feature,
        "Disease": disease,
    })
    return df


def make_fraudnet_x(n=1200):
    rng = RNG
    transaction_amount = rng.gamma(2, 80, n).clip(1, 5000)
    account_age_days = rng.integers(1, 3000, n)
    num_transactions_24h = rng.poisson(3, n)
    avg_transaction_amount = rng.gamma(2, 60, n).clip(1, 3000)
    distance_from_home_km = rng.gamma(1.5, 20, n).clip(0, 2000)
    hour_of_day = rng.integers(0, 24, n)

    risk = (
        0.01 * (transaction_amount - avg_transaction_amount)
        + 0.02 * distance_from_home_km
        - 0.001 * account_age_days
        + 0.15 * num_transactions_24h
    )
    prob = 1 / (1 + np.exp(-0.05 * risk))
    fraud = (rng.random(n) < prob * 0.25).astype(int)  # imbalance ~8-12%

    # TRAP 1: target leakage — a "chargeback_flag" set only after the fraud
    # investigation concludes, so it's not legitimately available
    # pre-decision. Near-deterministic so it produces a suspiciously
    # perfect score if a team keeps it in.
    leakage_noise = rng.random(n) < 0.04
    leakage_feature = np.where(leakage_noise, 1 - fraud, fraud)

    # TRAP 2: irrelevant identifier (numeric so it CAN be included as a
    # feature by mistake — the trap is realistic: including a raw ID rarely
    # helps prediction and slightly encourages overfitting).
    transaction_id = np.arange(500000, 500000 + n)

    # TRAP 3: missing values in Merchant_Category (~12%) and Distance (~6%)
    merchant_category_codes = rng.integers(1, 9, n).astype(float)
    missing_cat_mask = rng.random(n) < 0.12
    merchant_category_codes[missing_cat_mask] = np.nan

    distance_from_home_km = distance_from_home_km.astype(float)
    missing_dist_mask = rng.random(n) < 0.06
    distance_from_home_km[missing_dist_mask] = np.nan

    df = pd.DataFrame({
        "Transaction_ID": transaction_id,
        "Transaction_Amount": transaction_amount.round(2),
        "Account_Age_Days": account_age_days,
        "Num_Transactions_24h": num_transactions_24h,
        "Avg_Transaction_Amount": avg_transaction_amount.round(2),
        "Distance_From_Home_KM": distance_from_home_km.round(1),
        "Hour_Of_Day": hour_of_day,
        "Merchant_Category_Code": merchant_category_codes,
        "Leakage_Feature": leakage_feature,
        "Fraud": fraud,
    })
    return df


if __name__ == "__main__":
    med = make_medivision_x()
    fraud = make_fraudnet_x()
    med.to_csv(os.path.join(OUT_DIR, "medivision_x.csv"), index=False)
    fraud.to_csv(os.path.join(OUT_DIR, "fraudnet_x.csv"), index=False)
    print("MEDIVISION-X:", med.shape, "disease rate:", med.Disease.mean().round(3))
    print("FRAUDNET-X:", fraud.shape, "fraud rate:", fraud.Fraud.mean().round(3))
    print("MEDIVISION-X missing:\n", med.isna().mean().round(3))
    print("FRAUDNET-X missing:\n", fraud.isna().mean().round(3))
