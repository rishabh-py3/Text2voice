#!/usr/bin/env bash
# Resemble AI Chatterbox TTS Setup (MIT Licensed)
# Installs Chatterbox TTS with native paralinguistic and emotion tags
set -e

echo "=== Setting up Resemble AI Chatterbox TTS (MIT License) ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -d ".venv" ]; then
  PYTHON=".venv/bin/python"
  PIP=".venv/bin/pip"
else
  PYTHON="python3"
  PIP="pip"
fi

echo "Installing chatterbox-tts..."
$PIP install --upgrade chatterbox-tts

echo "Verifying Chatterbox installation..."
$PYTHON -c "
import chatterbox
print('✓ Chatterbox version:', getattr(chatterbox, '__version__', 'ready'))
from chatterbox.tts import ChatterboxTTS
print('✓ ChatterboxTTS class available')
"

echo "=== Chatterbox setup complete! ==="
echo "Select 'Chatterbox (Resemble AI - MIT Model)' in Settings or set TTS_ENGINE=chatterbox."
