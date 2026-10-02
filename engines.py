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
        "kokoro": "af_sarah",
        "say": "Samantha",
        "accent": "American (US)",
        "tone": "Warm & Natural",
        "description": "Clear, natural, and expressive tone. Great for narration, audiobooks, and tutorials.",
    },
    "Ethan": {
        "gender": "Male",
        "piper": "en_US-ryan-medium",
        "kokoro": "am_michael",
        "say": "Alex",
        "accent": "American (US)",
        "tone": "Deep & Confident",
        "description": "Articulate, resonant, and energetic voice tailored for podcasts, presentations, and announcements.",
    },
    "Nova": {
        "gender": "Neutral",
        "piper": "en_US-lessac-medium",
        "kokoro": "bf_emma",
        "say": "Daniel",
        "accent": "American (US)",
        "tone": "Balanced & Modern",
        "description": "Approachable, crisp, and adaptive AI persona ideal for conversational dialogue and assistants.",
    },
    "Adam": {
        "gender": "Male",
        "piper": "en_US-bryce-medium",
        "kokoro": "am_adam",
        "say": "Tom",
        "accent": "American (US)",
        "tone": "Energetic & Friendly",
        "description": "A young male voice with an energetic and friendly tone, ideal for social media tutorials, reels, and video narration.",
    },
}

KOKORO_DIR = VOICES_DIR / "kokoro"
KOKORO_MODEL_FILE = KOKORO_DIR / "kokoro-v0_19.onnx"
KOKORO_VOICES_BIN = KOKORO_DIR / "voices.bin"
KOKORO_VOICES_NPZ = KOKORO_DIR / "voices.bin.npz"


def _kokoro_ready() -> bool:
    voices_file = KOKORO_VOICES_BIN if KOKORO_VOICES_BIN.exists() else KOKORO_VOICES_NPZ
    if not (KOKORO_MODEL_FILE.exists() and voices_file.exists()):
        return False
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except ImportError:
        return False


_CHATTERBOX_CACHE = None
_KOKORO_CACHE = None
_PIPER_VOICE_CACHE = {}


def _chatterbox_ready() -> bool:
    try:
        import chatterbox  # noqa: F401
        return True
    except ImportError:
        return False


def _get_chatterbox():
    global _CHATTERBOX_CACHE, _KOKORO_CACHE, _PIPER_VOICE_CACHE
    # Conserve memory by evicting other models
    _KOKORO_CACHE = None
    _PIPER_VOICE_CACHE.clear()

    if _CHATTERBOX_CACHE is None:
        try:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
            _CHATTERBOX_CACHE = ChatterboxTurboTTS.from_pretrained(device=device)
        except Exception:
            try:
                import torch
                from chatterbox.tts import ChatterboxTTS
                device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
                _CHATTERBOX_CACHE = ChatterboxTTS.from_pretrained(device=device)
            except Exception as e:
                raise AudioError(f"Chatterbox initialization failed: {e}")
    return _CHATTERBOX_CACHE


def _get_kokoro():
    global _CHATTERBOX_CACHE, _KOKORO_CACHE, _PIPER_VOICE_CACHE
    
    # Aggressive memory management for Render free tier (512MB RAM limit)
    # Evict Piper and Chatterbox from memory if Kokoro is loading
    _CHATTERBOX_CACHE = None
    _PIPER_VOICE_CACHE.clear()
    
    if _KOKORO_CACHE is None:
        if not _kokoro_ready():
            raise AudioError("Kokoro model files not found. Run ./setup_kokoro.sh or select Piper in Settings.")
        from kokoro_onnx import Kokoro
        voices_path = str(KOKORO_VOICES_BIN if KOKORO_VOICES_BIN.exists() else KOKORO_VOICES_NPZ)
        _KOKORO_CACHE = Kokoro(str(KOKORO_MODEL_FILE), voices_path)
    return _KOKORO_CACHE


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
    if _kokoro_ready():
        return "kokoro"
    if _piper_ready():
        return "piper"
    if _chatterbox_ready():
        return "chatterbox"
    if platform.system() == "Darwin" and shutil.which("say"):
        return "say"
    raise AudioError(
        "No TTS engine available. Run ./setup_voices.sh to install Piper voices "
        "or ./setup_kokoro.sh for Kokoro studio AI voices."
    )


def _get_piper_voice(model_path: Path):
    global _CHATTERBOX_CACHE, _KOKORO_CACHE, _PIPER_VOICE_CACHE
    
    # Aggressive memory management for Render free tier
    # Evict Kokoro and Chatterbox from memory if Piper is loading
    _CHATTERBOX_CACHE = None
    _KOKORO_CACHE = None
    
    path_str = str(model_path)
    if path_str not in _PIPER_VOICE_CACHE:
        # Keep only ONE Piper voice in memory at a time to prevent OOM
        _PIPER_VOICE_CACHE.clear()
        
        from piper import PiperVoice
        _PIPER_VOICE_CACHE[path_str] = PiperVoice.load(path_str)
    return _PIPER_VOICE_CACHE[path_str]


def preload_voices():
    """Disabled to prevent Out of Memory (OOM) errors on Render free tier (512MB limit).
    Models will lazy-load into memory exactly when requested instead."""
    pass


# Emotion synthesis tuning for Piper (neural variability & phoneme duration) and say (rate factor)
EMOTION_PROFILES = {
    # Paralinguistic expressions (inspired by Resemble AI Chatterbox)
    "laugh": {"length_scale": 0.88, "noise_scale": 0.80, "noise_w_scale": 0.90, "exaggeration": 1.1, "say_rate": 1.15},
    "chuckle": {"length_scale": 0.92, "noise_scale": 0.74, "noise_w_scale": 0.85, "exaggeration": 0.9, "say_rate": 1.10},
    "sigh": {"length_scale": 1.18, "noise_scale": 0.52, "noise_w_scale": 0.65, "exaggeration": 0.4, "say_rate": 0.85},
    "gasp": {"length_scale": 0.85, "noise_scale": 0.85, "noise_w_scale": 0.92, "exaggeration": 1.2, "say_rate": 1.20},
    # Core emotions
    "excited": {"length_scale": 0.88, "noise_scale": 0.78, "noise_w_scale": 0.88, "exaggeration": 1.0, "say_rate": 1.15},
    "sad": {"length_scale": 1.20, "noise_scale": 0.55, "noise_w_scale": 0.68, "exaggeration": 0.7, "say_rate": 0.85},
    "angry": {"length_scale": 0.90, "noise_scale": 0.80, "noise_w_scale": 0.90, "exaggeration": 1.2, "say_rate": 1.15},
    "whisper": {"length_scale": 1.15, "noise_scale": 0.45, "noise_w_scale": 0.55, "exaggeration": 0.3, "say_rate": 0.85},
    "calm": {"length_scale": 1.08, "noise_scale": 0.60, "noise_w_scale": 0.72, "exaggeration": 0.2, "say_rate": 0.92},
    "dramatic": {"length_scale": 1.18, "noise_scale": 0.70, "noise_w_scale": 0.84, "exaggeration": 1.1, "say_rate": 0.88},
    "fear": {"length_scale": 0.90, "noise_scale": 0.82, "noise_w_scale": 0.90, "exaggeration": 0.95, "say_rate": 1.15},
    "serious": {"length_scale": 1.06, "noise_scale": 0.58, "noise_w_scale": 0.68, "exaggeration": 0.4, "say_rate": 0.94},
    "curious": {"length_scale": 0.95, "noise_scale": 0.72, "noise_w_scale": 0.82, "exaggeration": 0.8, "say_rate": 1.05},
    "neutral": {"length_scale": 1.00, "noise_scale": 0.667, "noise_w_scale": 0.80, "exaggeration": 0.5, "say_rate": 1.00},
}


def synth_segment_pcm(text: str, voice: str, engine: str, speed: float = 1.0, emotion: str = "neutral") -> bytes:
    """Synthesizes speech directly into 16-bit 22050Hz mono PCM bytes in memory (under 100ms)."""
    if voice not in VOICES:
        raise AudioError(f"Unknown voice '{voice}'.")

    if not any(c.isalnum() for c in text):
        return b"\x00\x00" * int(22050 * 0.3)

    emo_profile = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["neutral"])
    emo_length_mult = emo_profile["length_scale"]

    if engine == "chatterbox":
        cb = _get_chatterbox()
        exaggeration = float(emo_profile.get("exaggeration", 0.5))
        try:
            # Check if reference audio exists for the voice persona
            ref_audio = VOICES_DIR / f"{VOICES[voice]['piper']}.wav"
            prompt_path = str(ref_audio) if ref_audio.exists() else None
            if prompt_path:
                wav = cb.generate(text, audio_prompt_path=prompt_path, exaggeration=exaggeration)
            else:
                wav = cb.generate(text, exaggeration=exaggeration)
            
            import numpy as np
            sr = getattr(cb, "sr", 24000)
            samples = wav.squeeze().cpu().numpy()
            if sr != 22050 and len(samples) > 0:
                old_indices = np.arange(len(samples))
                new_length = int(len(samples) * 22050 / sr)
                new_indices = np.linspace(0, len(samples) - 1, new_length)
                samples = np.interp(new_indices, old_indices, samples).astype(np.float32)
            return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        except Exception as e:
            raise AudioError(f"Chatterbox synthesis failed: {e}")

    elif engine == "piper":
        model = VOICES_DIR / f"{VOICES[voice]['piper']}.onnx"
        if not model.exists():
            raise AudioError(f"Voice file missing: {model.name}. Run ./setup_voices.sh")

        base_length_scale = (1.0 / max(speed, 0.1)) * emo_length_mult
        length_scale = max(0.4, min(2.5, base_length_scale))
        noise_scale = float(emo_profile["noise_scale"])
        noise_w_scale = float(emo_profile["noise_w_scale"])

        try:
            try:
                from piper.config import SynthesisConfig
            except ImportError:
                from piper import SynthesisConfig
            piper_voice = _get_piper_voice(model)
            syn_cfg = SynthesisConfig(
                length_scale=length_scale,
                noise_scale=noise_scale,
                noise_w_scale=noise_w_scale,
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
                "--noise-scale", f"{noise_scale:.3f}",
                "--noise-w", f"{noise_w_scale:.3f}",
                "-f", tmp_f.name,
            ]
            proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                raise AudioError(f"Piper failed: {proc.stderr.strip()[-300:]}")
            import wave
            with wave.open(tmp_f.name, "rb") as w:
                return w.readframes(w.getnframes())

    elif engine == "kokoro":
        k = _get_kokoro()
        kokoro_voice_name = VOICES[voice].get("kokoro", "am_adam")
        kokoro_speed = float(max(0.5, min(2.0, speed * (1.0 / emo_length_mult))))
        try:
            samples, sr = k.create(text, voice=kokoro_voice_name, speed=kokoro_speed, lang="en-us")
        except Exception as e:
            raise AudioError(f"Kokoro synthesis failed: {e}")

        import numpy as np
        if sr != 22050 and len(samples) > 0:
            old_indices = np.arange(len(samples))
            new_length = int(len(samples) * 22050 / sr)
            new_indices = np.linspace(0, len(samples) - 1, new_length)
            samples = np.interp(new_indices, old_indices, samples).astype(np.float32)

        return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

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

    elif engine == "dummy":
        import math, struct
        num_samples = int(22050 * 0.8)
        pcm = bytearray()
        for i in range(num_samples):
            val = int(32767 * 0.2 * math.sin(2 * math.pi * 440 * i / 22050))
            pcm.extend(struct.pack("<h", val))
        return bytes(pcm)

    raise AudioError(f"Unsupported engine: {engine}")


def synth_segment(text: str, voice: str, engine: str, out_wav: Path, speed: float = 1.0, emotion: str = "neutral") -> None:
    pcm = synth_segment_pcm(text, voice, engine, speed=speed, emotion=emotion)
    from audio_utils import encode_pcm_to_audio
    wav_data = encode_pcm_to_audio(pcm, fmt="wav", emotion=emotion)
    out_wav.write_bytes(wav_data)
