#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== ELearning Video Generator ==="
echo "Checking dependencies..."

# Install Python packages if missing
pip3 install -q fastapi "uvicorn[standard]" python-multipart aiofiles python-pptx anthropic openai Pillow

# Install system tools if missing
if ! command -v pdftoppm &>/dev/null; then
  echo "Installing poppler-utils..."
  apt-get install -y -q poppler-utils
fi
if ! command -v ffmpeg &>/dev/null; then
  echo "Installing ffmpeg..."
  apt-get install -y -q ffmpeg
fi

echo "Starting server at http://0.0.0.0:8000 ..."
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
