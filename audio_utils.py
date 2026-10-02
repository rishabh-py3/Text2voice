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


# Emotion acoustic prosody filters (Preserves pitch/identity, uses tempo, EQ, dynamics)
EMOTION_FILTERS = {
    # Whisper / Soft: cut body frequencies, boost extreme highs, low volume, no cracking
    "whisper": "highpass=f=2000,treble=g=8,volume=0.4",
    # Sad / Melancholic: slower, muffled/darker EQ, softer
    "sad": "atempo=0.85,lowpass=f=3000,volume=0.8",
    # Excited / Cheerful: faster, brighter, dynamic
    "excited": "atempo=1.15,treble=g=5,compand=attacks=0:points=-80/-80|-20/-20|0/-5",
    # Angry / Aggressive: slightly faster, harsh compression, loud
    "angry": "atempo=1.1,compand=attacks=0:points=-80/-80|-15/-5|0/-3,treble=g=3,volume=1.2",
    # Calm / Relaxed: slower, soft high-cut
    "calm": "atempo=0.9,lowpass=f=6000,volume=0.9",
    # Dramatic / Epic: slightly slower, subtle echo for space
    "dramatic": "atempo=0.9,aecho=0.8:0.8:40:0.1",
    # Fear / Nervous: faster, thin sounding (cut lows), trembling vibrato
    "fear": "atempo=1.1,highpass=f=500,vibrato=f=8:d=0.3",
    # Serious / Authoritative: very flat EQ, deliberate pace, strong compression for authority
    "serious": "atempo=0.95,compand=attacks=0:points=-80/-80|-20/-20|0/-5",
    # Curious / Inquisitive: slightly faster, bright and airy
    "curious": "atempo=1.05,highpass=f=300,treble=g=3",
}


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 22050) -> bytes:
    """Generate in-memory 16-bit mono WAV bytes in microseconds."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def filter_pcm(pcm_bytes: bytes, emotion: str) -> bytes:
    """Apply an acoustic emotion filter to raw PCM bytes in memory."""
    filter_chain = EMOTION_FILTERS.get(emotion)
    if not filter_chain:
        return pcm_bytes
    cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "pipe:0",
           "-af", filter_chain, "-f", "s16le", "pipe:1"]
    proc = subprocess.run(cmd, input=pcm_bytes, capture_output=True)
    if proc.returncode != 0:
        return pcm_bytes
    return proc.stdout


def encode_pcm_to_audio(pcm_bytes: bytes, fmt: str = "mp3", emotion: str = "neutral") -> bytes:
    """Single-pass in-memory stream: applies emotion acoustic filter and encodes to target format directly."""
    filter_chain = EMOTION_FILTERS.get(emotion)
    if fmt == "wav" and not filter_chain:
        return pcm_to_wav_bytes(pcm_bytes, SAMPLE_RATE)

    cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "pipe:0"]
    if filter_chain:
        cmd.extend(["-af", filter_chain])
    if fmt == "mp3":
        cmd.extend(["-codec:a", "libmp3lame", "-q:a", "3", "-f", "mp3", "pipe:1"])
    else:
        cmd.extend(["-codec:a", "pcm_s16le", "-f", "wav", "pipe:1"])

    proc = subprocess.run(cmd, input=pcm_bytes, capture_output=True)
    if proc.returncode != 0:
        raise AudioError(f"Audio encoding failed: {proc.stderr.decode()[-300:]}")
    return proc.stdout


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
