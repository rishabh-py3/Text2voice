#!/usr/bin/env bash
# Downloads Kokoro-82M ONNX model and voice weights (~315 MB).
set -e
cd "$(dirname "$0")"

PYTHON="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
fi

mkdir -p voices/kokoro
"$PYTHON" -c '
import os, sys, urllib.request
from pathlib import Path

out_dir = Path("voices/kokoro")
out_dir.mkdir(parents=True, exist_ok=True)

files = {
    "kokoro-v0_19.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx",
    "voices.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin",
}

for name, url in files.items():
    dst = out_dir / name
    if not dst.exists() or dst.stat().st_size == 0:
        print(f"Downloading {name}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(dst, "wb") as f:
            while chunk := resp.read(1024 * 1024):
                f.write(chunk)
        print(f"Downloaded {name} ({dst.stat().st_size / (1024*1024):.1f} MB)")
    else:
        print(f"{name} already present ({dst.stat().st_size / (1024*1024):.1f} MB).")
'
echo "Kokoro models ready in ./voices/kokoro"
