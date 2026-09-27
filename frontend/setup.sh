#!/usr/bin/env bash
# Installs frontend dependencies.
set -e
cd "$(dirname "$0")"
npm install
echo "Done. Start dev server with: npm run dev   (or build with: npm run build)"
