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


def preload_voices():
    """Pre-warm onnx neural models in memory at startup for zero-latency response."""
    for v in VOICES.values():
        model = VOICES_DIR / f"{v['piper']}.onnx"
        if model.exists():
            try:
                _get_piper_voice(model)
            except Exception as e:
                pass


# Emotion synthesis tuning for Piper (neural variability & phoneme duration) and say (rate factor)
EMOTION_PROFILES = {
    # Excited: upbeat tempo, vibrant neural expressiveness and lively energy
    "excited": {"length_scale": 0.90, "noise_scale": 0.72, "noise_w_scale": 0.85, "say_rate": 1.15},
    # Sad: gentle reflective cadence, preserves 100% natural vocal timbre, sorrowful delivery
    "sad": {"length_scale": 1.16, "noise_scale": 0.60, "noise_w_scale": 0.72, "say_rate": 0.85},
    # Angry: firm cadence, punchy articulation
    "angry": {"length_scale": 0.92, "noise_scale": 0.75, "noise_w_scale": 0.88, "say_rate": 1.15},
    # Whisper: slow breathy cadence, intimate soft delivery
    "whisper": {"length_scale": 1.12, "noise_scale": 0.48, "noise_w_scale": 0.58, "say_rate": 0.88},
    # Calm: gentle relaxed cadence, smooth steady rhythm
    "calm": {"length_scale": 1.06, "noise_scale": 0.62, "noise_w_scale": 0.74, "say_rate": 0.94},
    # Dramatic: expansive deliberate cadence, cinematic weight
    "dramatic": {"length_scale": 1.16, "noise_scale": 0.68, "noise_w_scale": 0.82, "say_rate": 0.88},
    # Fear: fast anxious flutter, tense cadence
    "fear": {"length_scale": 0.92, "noise_scale": 0.75, "noise_w_scale": 0.88, "say_rate": 1.12},
    # Serious: deliberate steady cadence, authoritative
    "serious": {"length_scale": 1.06, "noise_scale": 0.60, "noise_w_scale": 0.70, "say_rate": 0.94},
    # Curious: light upward questioning inflection
    "curious": {"length_scale": 0.96, "noise_scale": 0.70, "noise_w_scale": 0.80, "say_rate": 1.04},
    "neutral": {"length_scale": 1.00, "noise_scale": 0.667, "noise_w_scale": 0.80, "say_rate": 1.00},
}


def synth_segment_pcm(text: str, voice: str, engine: str, speed: float = 1.0, emotion: str = "neutral") -> bytes:
    """Synthesizes speech directly into 16-bit 22050Hz mono PCM bytes in memory (under 100ms)."""
    if voice not in VOICES:
        raise AudioError(f"Unknown voice '{voice}'.")

    if not any(c.isalnum() for c in text):
        return b"\x00\x00" * int(22050 * 0.3)

    emo_profile = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["neutral"])
    emo_length_mult = emo_profile["length_scale"]

    if engine == "piper":
        model = VOICES_DIR / f"{VOICES[voice]['piper']}.onnx"
        if not model.exists():
            raise AudioError(f"Voice file missing: {model.name}. Run ./setup_voices.sh")

        base_length_scale = 1.0 / max(speed, 0.1)
        length_scale = max(0.35, min(2.5, base_length_scale * emo_length_mult))

        try:
            try:
                from piper.config import SynthesisConfig
            except ImportError:
                from piper import SynthesisConfig
            piper_voice = _get_piper_voice(model)
            syn_cfg = SynthesisConfig(
                length_scale=length_scale,
                noise_scale=emo_profile["noise_scale"],
                noise_w_scale=emo_profile["noise_w_scale"]
            )
            chunks = list(piper_voice.synthesize(text, syn_config=syn_cfg))
            if chunks:
                return b"".join(c.audio_int16_bytes for c in chunks)
        except Exception:
            pass

        # Subprocess fallback if in-memory synthesis fails
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp_f:
            cmd = [
                sys.executable, "-m", "piper",
                "-m", str(model),
                "--length-scale", f"{length_scale:.3f}",
                "--noise-scale", f"{emo_profile['noise_scale']:.3f}",
                "--noise-w", f"{emo_profile['noise_w_scale']:.3f}",
                "-f", tmp_f.name,
            ]
            proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                raise AudioError(f"Piper failed: {proc.stderr.strip()[-300:]}")
            import wave
            with wave.open(tmp_f.name, "rb") as w:
                return w.readframes(w.getnframes())

    elif engine == "say":
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            aiff = tmp / "temp.aiff"
            rate = max(80, min(380, int(185 * speed * emo_profile["say_rate"])))
            cmd = ["say", "-v", VOICES[voice]["say"], "-r", str(rate), "-o", str(aiff), "-f", "-"]
            proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                raise AudioError(f"'say' failed: {proc.stderr.strip()[-300:]}")
            raw_wav = tmp / "raw.wav"
            to_wav(aiff, raw_wav)
            import wave
            with wave.open(str(raw_wav), "rb") as w:
                return w.readframes(w.getnframes())

    raise AudioError(f"Unsupported engine: {engine}")


def synth_segment(text: str, voice: str, engine: str, out_wav: Path, speed: float = 1.0, emotion: str = "neutral") -> None:
    pcm = synth_segment_pcm(text, voice, engine, speed=speed, emotion=emotion)
    from audio_utils import encode_pcm_to_audio
    wav_data = encode_pcm_to_audio(pcm, fmt="wav", emotion=emotion)
    out_wav.write_bytes(wav_data)
