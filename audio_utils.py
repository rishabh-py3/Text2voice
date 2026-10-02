"""Audio helpers built on FFmpeg (no AI here, just signal processing)."""
import subprocess
import wave
from pathlib import Path

SAMPLE_RATE = 22050  # internal working rate for generated speech


class AudioError(RuntimeError):
    pass


def run_ffmpeg(*args: str) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise AudioError("FFmpeg is not installed. On Mac run: brew install ffmpeg")
    except subprocess.TimeoutExpired:
        raise AudioError("Audio processing timed out.")
    if result.returncode != 0:
        raise AudioError(f"FFmpeg failed: {result.stderr.strip()[-400:]}")


def to_wav(src: Path, dst: Path, rate: int = SAMPLE_RATE) -> None:
    """Convert any audio file to mono 16-bit PCM wav at a fixed rate."""
    run_ffmpeg("-i", str(src), "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(dst))


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def concat_with_pauses(segments: list[Path], pause_seconds: float, dst: Path) -> None:
    """Join wav segments (all mono 16-bit @ SAMPLE_RATE) with silence between them."""
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        silence = b"\x00\x00" * int(SAMPLE_RATE * pause_seconds)
        for i, seg in enumerate(segments):
            with wave.open(str(seg), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            if i < len(segments) - 1:
                out.writeframes(silence)


def concat_wavs(segments: list[Path], dst: Path) -> None:
    """Join any list of wav files (mono 16-bit @ SAMPLE_RATE) seamlessly."""
    if not segments:
        return
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for seg in segments:
            with wave.open(str(seg), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))


def generate_silence(seconds: float, dst: Path) -> None:
    """Generate exact silence wav for speech pauses."""
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        num_frames = int(SAMPLE_RATE * max(0.05, seconds))
        out.writeframes(b"\x00\x00" * num_frames)


def change_speed(src: Path, dst: Path, speed: float) -> None:
    if abs(speed - 1.0) < 0.01:
        dst.write_bytes(src.read_bytes())
        return
    run_ffmpeg("-i", str(src), "-filter:a", f"atempo={speed:.3f}", str(dst))


# Emotion acoustic prosody filters (Acoustic presence, warmth, contour & dynamics)
# Note: Pitch & tempo are handled naturally at synthesis time to preserve speaker identity 100%.
EMOTION_FILTERS = {
    # Excited / Cheerful: bright vocal presence + crisp articulation + energetic compression
    "excited": "equalizer=f=3200:t=q:w=1.2:g=2.5,treble=g=2.0:f=6500,acompressor=threshold=-16dB:ratio=3.0:attack=8:release=80,alimiter=limit=-0.5dB",
    # Sad / Melancholic: soft warm contour + gentle presence reduction + mellow dynamics
    "sad": "volume=0.94,equalizer=f=260:t=q:w=1.0:g=1.8,equalizer=f=3600:t=q:w=1.2:g=-2.2,acompressor=threshold=-20dB:ratio=2.2:attack=25:release=180,alimiter=limit=-0.5dB",
    # Angry / Aggressive: firm mid-range punch + forceful articulation + tight leveling
    "angry": "equalizer=f=1800:t=q:w=1.2:g=3.5,equalizer=f=150:t=q:w=1.0:g=2.0,acompressor=threshold=-15dB:ratio=4.5:attack=5:release=60,alimiter=limit=-0.5dB",
    # Whisper / Soft: breathy highpass + airy presence boost + intimate leveling
    "whisper": "highpass=f=200,equalizer=f=400:t=q:w=1.2:g=-3.5,equalizer=f=5500:t=q:w=1.0:g=3.5,treble=g=3.0:f=8000,volume=0.90,alimiter=limit=-0.5dB",
    # Calm / Relaxed: gentle low-mid warmth + smooth presence + transparent dynamics
    "calm": "equalizer=f=220:t=q:w=1.0:g=1.5,equalizer=f=4000:t=q:w=1.2:g=-1.2,acompressor=threshold=-18dB:ratio=2.5:attack=20:release=140,alimiter=limit=-0.5dB",
    # Dramatic / Epic: cinematic resonance + expressive presence
    "dramatic": "equalizer=f=140:t=q:w=1.0:g=2.5,equalizer=f=3000:t=q:w=1.2:g=2.0,acompressor=threshold=-16dB:ratio=3.5:attack=15:release=120,alimiter=limit=-0.5dB",
    # Fear / Nervous: tense presence + tight dynamic compression
    "fear": "equalizer=f=3800:t=q:w=1.2:g=2.0,acompressor=threshold=-16dB:ratio=3.0:attack=10:release=70,alimiter=limit=-0.5dB",
    # Serious / Authoritative: solid low resonance + steady broadcast leveling
    "serious": "equalizer=f=180:t=q:w=1.0:g=2.0,acompressor=threshold=-16dB:ratio=3.0:attack=15:release=100,alimiter=limit=-0.5dB",
    # Curious / Inquisitive: light bright articulation + clarity
    "curious": "equalizer=f=3400:t=q:w=1.2:g=2.0,alimiter=limit=-0.5dB",
}


def apply_emotion(src: Path, dst: Path, emotion: str) -> None:
    filter_chain = EMOTION_FILTERS.get(emotion)
    if not filter_chain:
        dst.write_bytes(src.read_bytes())
        return
    run_ffmpeg("-i", str(src), "-ac", "1", "-ar", "22050", "-af", filter_chain,
               "-c:a", "pcm_s16le", str(dst))


# Name -> FFmpeg filter chain. Input is always mono wav at 44.1 kHz.
EFFECTS = {
    # Metallic robotic cyborg: FFT denoise + tuned flanger + modulated tremolo ring + studio compression
    "robot": "afftdn=nf=-20,highpass=f=120,lowpass=f=4500,flanger=delay=2.5:depth=2:regen=55:width=80:speed=8,tremolo=f=40:d=0.8,aecho=0.8:0.75:12:0.45,equalizer=f=1800:t=q:w=2:g=5,acompressor=threshold=-16dB:ratio=6,alimiter=limit=-1dB",
    # 8-bit cyber glitch vocoder: noise sharpening crystalizer + linear bitcrusher + lo-fi slap echo
    "digital": "afftdn=nf=-20,crystalizer=i=2,acrusher=bits=9:mix=0.6:mode=lin,aecho=0.8:0.65:18:0.35,equalizer=f=3200:t=q:w=1.8:g=6,treble=g=3,acompressor=threshold=-16dB:ratio=4,alimiter=limit=-1dB",
    # Broadcast vocal polish: FFT mic denoise + warmth EQ + presence shine + subtle stereo chorus + optical compressor
    "smooth_ai": "afftdn=nf=-25,highpass=f=80,equalizer=f=220:t=q:w=1.2:g=2,equalizer=f=4000:t=q:w=1.5:g=3.5,treble=g=3:f=9000,crystalizer=i=1.5,chorus=0.6:0.8:22:0.25:0.3:1.2,acompressor=threshold=-20dB:ratio=3.5:attack=10:release=100,alimiter=limit=-1dB",
    # Cinematic deep announcer: pitch drop + virtual bass sub-harmonics + cinema compressor
    "deep": "afftdn=nf=-20,asetrate=35280,aresample=44100,atempo=1.25,bass=g=10:f=100,virtualbass,equalizer=f=2500:t=q:w=1.2:g=2.5,acompressor=threshold=-18dB:ratio=5,alimiter=limit=-1dB",
    # Bright energetic formant: pitch transposition + high clarity boost + vocal leveling
    "high": "afftdn=nf=-20,asetrate=52920,aresample=44100,atempo=0.833,treble=g=5:f=6000,crystalizer=i=2,equalizer=f=3000:t=q:w=1.5:g=4,acompressor=threshold=-16dB:ratio=4,alimiter=limit=-1dB",
}


def apply_effect(src: Path, dst: Path, effect: str) -> None:
    if effect not in EFFECTS:
        raise AudioError(f"Unknown effect '{effect}'.")
    run_ffmpeg("-i", str(src), "-ac", "1", "-ar", "44100", "-af", EFFECTS[effect],
               "-c:a", "pcm_s16le", str(dst))


def encode(src_wav: Path, dst: Path, fmt: str) -> None:
    if fmt == "wav":
        dst.write_bytes(src_wav.read_bytes())
    elif fmt == "mp3":
        run_ffmpeg("-i", str(src_wav), "-codec:a", "libmp3lame", "-q:a", "3", str(dst))
    else:
        raise AudioError(f"Unsupported format '{fmt}'.")
