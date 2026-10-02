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


_PIPER_VOICE_CACHE = {}


def _get_piper_voice(model_path: Path):
    path_str = str(model_path)
    if path_str not in _PIPER_VOICE_CACHE:
        from piper import PiperVoice
        _PIPER_VOICE_CACHE[path_str] = PiperVoice.load(path_str)
    return _PIPER_VOICE_CACHE[path_str]


# Emotion synthesis tuning for Piper (neural variability & phoneme duration) and say (rate factor)
EMOTION_PROFILES = {
    "excited": {"length_scale": 0.88, "noise_scale": 0.75, "noise_w_scale": 0.85, "say_rate": 1.15},
    "sad": {"length_scale": 1.25, "noise_scale": 0.55, "noise_w_scale": 0.65, "say_rate": 0.85},
    "angry": {"length_scale": 0.90, "noise_scale": 0.85, "noise_w_scale": 0.90, "say_rate": 1.10},
    "whisper": {"length_scale": 1.15, "noise_scale": 0.45, "noise_w_scale": 0.55, "say_rate": 0.90},
    "calm": {"length_scale": 1.12, "noise_scale": 0.58, "noise_w_scale": 0.68, "say_rate": 0.92},
    "dramatic": {"length_scale": 1.20, "noise_scale": 0.70, "noise_w_scale": 0.85, "say_rate": 0.88},
    "fear": {"length_scale": 0.92, "noise_scale": 0.85, "noise_w_scale": 0.95, "say_rate": 1.10},
    "serious": {"length_scale": 1.08, "noise_scale": 0.55, "noise_w_scale": 0.65, "say_rate": 0.95},
    "curious": {"length_scale": 0.95, "noise_scale": 0.75, "noise_w_scale": 0.80, "say_rate": 1.05},
    "neutral": {"length_scale": 1.00, "noise_scale": 0.667, "noise_w_scale": 0.80, "say_rate": 1.00},
}


def synth_segment(text: str, voice: str, engine: str, out_wav: Path, speed: float = 1.0, emotion: str = "neutral") -> None:
    if voice not in VOICES:
        raise AudioError(f"Unknown voice '{voice}'.")

    # If segment has no letters or digits, output silence rather than failing
    if not any(c.isalnum() for c in text):
        run_ffmpeg("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.4",
                   "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(out_wav))
        return

    emo_profile = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["neutral"])
    emo_length_mult = emo_profile["length_scale"]

    if engine == "piper":
        model = VOICES_DIR / f"{VOICES[voice]['piper']}.onnx"
        if not model.exists():
            raise AudioError(f"Voice file missing: {model.name}. Run ./setup_voices.sh")
        
        base_length_scale = 1.0 / max(speed, 0.1)
        length_scale = max(0.35, min(2.5, base_length_scale * emo_length_mult))
        
        raw = out_wav.with_suffix(".raw.wav")
        try:
            import wave
            from piper import SynthesisConfig
            piper_voice = _get_piper_voice(model)
            syn_cfg = SynthesisConfig(
                length_scale=length_scale,
                noise_scale=emo_profile["noise_scale"],
                noise_w_scale=emo_profile["noise_w_scale"]
            )
            chunks = list(piper_voice.synthesize(text, syn_config=syn_cfg))
            if not chunks:
                raise RuntimeError("Piper generated empty audio chunks.")
            
            with wave.open(str(raw), "wb") as w:
                w.setnchannels(chunks[0].sample_channels)
                w.setsampwidth(chunks[0].sample_width)
                w.setframerate(chunks[0].sample_rate)
                for c in chunks:
                    w.writeframes(c.audio_int16_bytes)
        except Exception:
            # Fallback to subprocess CLI
            cmd = [
                sys.executable, "-m", "piper",
                "-m", str(model),
                "--length-scale", f"{length_scale:.3f}",
                "--noise-scale", f"{emo_profile['noise_scale']:.3f}",
                "--noise-w", f"{emo_profile['noise_w_scale']:.3f}",
                "-f", str(raw),
            ]
            proc = subprocess.run(
                cmd,
                input=text, capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                raise AudioError(f"Piper failed: {proc.stderr.strip()[-300:]}")

        # Apply emotion acoustic shaping
        from audio_utils import apply_emotion
        apply_emotion(raw, out_wav, emotion)
        try:
            raw.unlink(missing_ok=True)
        except OSError:
            pass

    elif engine == "say":
        aiff = out_wav.with_suffix(".aiff")
        rate = max(80, min(380, int(185 * speed * emo_profile["say_rate"])))
        cmd = ["say", "-v", VOICES[voice]["say"], "-r", str(rate), "-o", str(aiff), "-f", "-"]
        proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            proc = subprocess.run(["say", "-r", str(rate), "-o", str(aiff), "-f", "-"], input=text,
                                  capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                raise AudioError(f"'say' failed: {proc.stderr.strip()[-300:]}")
        
        raw_wav = out_wav.with_suffix(".raw.wav")
        to_wav(aiff, raw_wav)
        from audio_utils import apply_emotion
        apply_emotion(raw_wav, out_wav, emotion)
        try:
            aiff.unlink(missing_ok=True)
            raw_wav.unlink(missing_ok=True)
        except OSError:
            pass

    elif engine == "dummy":
        freq = {"Aria": 440, "Ethan": 220, "Nova": 330}[voice]
        secs = max(0.4, min(len(text) * 0.06 / max(speed, 0.1), 10))
        run_ffmpeg("-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}",
                   "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(out_wav))
    else:
        raise AudioError(f"Unknown TTS engine '{engine}'.")
