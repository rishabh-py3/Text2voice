"""Text-to-speech engines. Each one turns a short text into a wav file.

Engines (set TTS_ENGINE, default "auto"):
  piper  - free, local, cross-platform (needs voice files: ./setup_voices.sh)
  say    - built into macOS, zero setup, good for getting started on a Mac
  dummy  - plays a tone; only for testing the front-end wiring
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from audio_utils import AudioError, run_ffmpeg, to_wav

VOICES_DIR = Path(__file__).parent / "voices"

VOICES = {
    "Aria": {
        "gender": "Female",
        "piper": "en_US-amy-medium",
        "say": "Samantha",
        "accent": "American (US)",
        "tone": "Warm & Natural",
        "description": "Clear, natural, and expressive tone. Great for narration, audiobooks, and tutorials.",
    },
    "Ethan": {
        "gender": "Male",
        "piper": "en_US-ryan-medium",
        "say": "Alex",
        "accent": "American (US)",
        "tone": "Deep & Confident",
        "description": "Articulate, resonant, and energetic voice tailored for podcasts, presentations, and announcements.",
    },
    "Nova": {
        "gender": "Neutral",
        "piper": "en_US-lessac-medium",
        "say": "Daniel",
        "accent": "American (US)",
        "tone": "Balanced & Modern",
        "description": "Approachable, crisp, and adaptive AI persona ideal for conversational dialogue and assistants.",
    },
}


def _piper_ready() -> bool:
    if not any(VOICES_DIR.glob("*.onnx")):
        return False
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


def pick_engine() -> str:
    wanted = os.getenv("TTS_ENGINE", "auto").lower()
    if wanted != "auto":
        return wanted
    if _piper_ready():
        return "piper"
    if platform.system() == "Darwin" and shutil.which("say"):
        return "say"
    raise AudioError(
        "No TTS engine available. Run ./setup_voices.sh to install Piper voices "
        "(or use a Mac, which has the built-in 'say' voices)."
    )


def synth_segment(text: str, voice: str, engine: str, out_wav: Path, speed: float = 1.0) -> None:
    if voice not in VOICES:
        raise AudioError(f"Unknown voice '{voice}'.")

    # If segment has no letters or digits, output silence rather than failing
    if not any(c.isalnum() for c in text):
        run_ffmpeg("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.4",
                   "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(out_wav))
        return

    if engine == "piper":
        model = VOICES_DIR / f"{VOICES[voice]['piper']}.onnx"
        if not model.exists():
            raise AudioError(f"Voice file missing: {model.name}. Run ./setup_voices.sh")
        raw = out_wav.with_suffix(".raw.wav")
        # Native neural phoneme duration: length-scale is inverse of speed
        # Slower speed -> higher length_scale (natural slow vowels without robotic atempo distortion)
        # Faster speed -> lower length_scale (natural fast articulation)
        length_scale = max(0.4, min(2.5, 1.0 / max(speed, 0.1)))
        cmd = [
            sys.executable, "-m", "piper",
            "-m", str(model),
            "--length-scale", f"{length_scale:.3f}",
            "-f", str(raw),
        ]
        proc = subprocess.run(
            cmd,
            input=text, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise AudioError(f"Piper failed: {proc.stderr.strip()[-300:]}")
        to_wav(raw, out_wav)

    elif engine == "say":
        aiff = out_wav.with_suffix(".aiff")
        # macOS say native rate in words per minute (default is ~185 wpm)
        rate = max(80, min(380, int(185 * speed)))
        cmd = ["say", "-v", VOICES[voice]["say"], "-r", str(rate), "-o", str(aiff), "-f", "-"]
        proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:  # voice not installed -> fall back to system default
            proc = subprocess.run(["say", "-r", str(rate), "-o", str(aiff), "-f", "-"], input=text,
                                  capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                raise AudioError(f"'say' failed: {proc.stderr.strip()[-300:]}")
        to_wav(aiff, out_wav)

    elif engine == "dummy":
        freq = {"Aria": 440, "Ethan": 220, "Nova": 330}[voice]
        secs = max(0.4, min(len(text) * 0.06 / max(speed, 0.1), 10))
        run_ffmpeg("-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}",
                   "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(out_wav))
    else:
        raise AudioError(f"Unknown TTS engine '{engine}'.")
