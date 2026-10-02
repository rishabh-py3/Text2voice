#!/usr/bin/env bash
# Downloads the free Piper voices used by Aria / Ethan / Nova (~60 MB each).
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
for v in en_US-amy-medium en_US-ryan-medium en_US-lessac-medium en_US-bryce-medium; do
  "$PYTHON" -m piper.download_voices "$v" --data-dir voices
done
echo "Voices ready in ./voices"
