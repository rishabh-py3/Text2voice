#!/usr/bin/env bash
set -e

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing ffmpeg..."
# Download statically compiled ffmpeg for linux amd64
curl -L -o ffmpeg https://github.com/eugeneware/ffmpeg-static/releases/download/b4.4/ffmpeg-linux-x64
chmod +x ffmpeg

# Optionally, put it in path or symlink to local bin
mkdir -p .local/bin
mv ffmpeg .local/bin/
export PATH="$PWD/.local/bin:$PATH"

echo "Build complete."
