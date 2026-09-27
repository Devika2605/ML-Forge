#!/usr/bin/env bash
# Sets up and prepares the ML Forge backend: installs deps, generates the
# two event datasets, and precomputes the full ML results lookup table.
# Run this once before the event (or after any dataset/scoring change).
set -e
cd "$(dirname "$0")"

echo "== Creating virtual environment (venv/) =="
python3 -m venv venv

echo "== Installing backend dependencies into venv =="
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "== Generating datasets (MEDIVISION-X, FRAUDNET-X) =="
venv/bin/python3 scripts/generate_datasets.py

echo "== Precomputing ML results lookup table =="
venv/bin/python3 scripts/precompute_results.py

echo "== Removing any stale dev database =="
rm -f app/mlforge.db

echo "Done. Start the server with: ./run.sh"
