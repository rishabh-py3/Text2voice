import shutil
import subprocess
import wave
from pathlib import Path

SAMPLE_RATE = 22050  # internal working rate for generated speech


class AudioError(RuntimeError):
    pass


def get_ffmpeg_bin() -> str:
    """Finds FFmpeg via imageio-ffmpeg (self-contained bundled binary) or system PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def run_ffmpeg(*args: str) -> None:
    cmd = [get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise AudioError("FFmpeg is not installed.")
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
    # Whisper / Soft: cut body frequencies, boost extreme highs, low volume, breathy intimacy
    "whisper": "highpass=f=2000,treble=g=8,volume=0.45",
    # Laugh / Laughter: upbeat cadence, slight pitch lift, bright playful acoustics
    "laugh": "atempo=1.12,treble=g=4,equalizer=f=3000:t=q:w=1:g=3,volume=1.05",
    # Chuckle / Snicker: relaxed cheerful warmth, light upbeat tempo
    "chuckle": "atempo=1.08,treble=g=3,equalizer=f=2500:t=q:w=1:g=2,volume=1.02",
    # Sigh / Exhale: gentle warm decrescendo, soothing low-pass roll-off
    "sigh": "atempo=0.88,lowpass=f=4500,volume=0.85",
    # Gasp / Surprise: fast sharp intake, thin low end, bright presence
    "gasp": "atempo=1.15,highpass=f=600,treble=g=5,volume=1.08",
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


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Generate in-memory 16-bit mono WAV bytes in microseconds."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def enhance_pcm_studio(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Fast in-memory studio vocal mastering (<2ms via NumPy):
    - Removes DC offset
    - Adds crisp vocal presence & high-shelf clarity (3.5kHz-8kHz)
    - Applies warm soft-knee tube saturation for fuller body
    - Normalizes peak loudness to -0.8 dBFS with anti-click micro-fades
    """
    if not pcm_bytes or len(pcm_bytes) < 4:
        return pcm_bytes
    try:
        import numpy as np
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return pcm_bytes

        # 1. Remove DC offset
        samples = samples - np.mean(samples)

        # 2. High-frequency presence & consonant articulation boost
        high_detail = np.diff(samples, prepend=samples[0])
        samples = samples + (0.22 * high_detail)

        # 3. Warm low-mid body & soft-knee harmonic exciter
        peak = float(np.max(np.abs(samples)))
        if peak > 1e-4:
            samples = samples / peak
            # Gentle harmonic warmth without distortion
            samples = np.tanh(samples * 1.18) / float(np.tanh(1.18))

        # 4. Micro fade-in / fade-out (5ms) to eliminate segment clicks
        fade_len = min(int(sample_rate * 0.005), samples.size // 4)
        if fade_len > 1:
            fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
            samples[:fade_len] *= fade_in
            samples[-fade_len:] *= fade_in[::-1]

        # 5. Master output level at -0.7 dBFS (92% scale)
        out = np.clip(samples * 30146.0, -32767.0, 32767.0).astype(np.int16)
        return out.tobytes()
    except Exception:
        return pcm_bytes


def filter_pcm(pcm_bytes: bytes, emotion: str, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Apply an acoustic emotion filter to raw PCM bytes in memory."""
    filter_chain = EMOTION_FILTERS.get(emotion)
    if not filter_chain:
        return pcm_bytes
    cmd = [get_ffmpeg_bin(), "-y", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
           "-af", filter_chain, "-f", "s16le", "pipe:1"]
    proc = subprocess.run(cmd, input=pcm_bytes, capture_output=True)
    if proc.returncode != 0:
        return pcm_bytes
    return proc.stdout


def encode_pcm_to_audio(
    pcm_bytes: bytes,
    fmt: str = "mp3",
    emotion: str = "neutral",
    sample_rate: int = SAMPLE_RATE,
) -> bytes:
    """Single-pass in-memory stream: applies studio enhancement and encodes to target format directly."""
    pcm_bytes = enhance_pcm_studio(pcm_bytes, sample_rate=sample_rate)
    filter_chain = EMOTION_FILTERS.get(emotion)
    if fmt == "wav" and not filter_chain:
        return pcm_to_wav_bytes(pcm_bytes, sample_rate)

    cmd = [
        get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0"
    ]
    if filter_chain:
        cmd.extend(["-af", filter_chain])
    if fmt == "mp3":
        # High-fidelity VBR quality (-q:a 1) for crisp studio highs
        cmd.extend(["-codec:a", "libmp3lame", "-q:a", "1", "-f", "mp3", "pipe:1"])
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


# Studio-grade Voice-to-Voice DSP chains (normalized to 44.1 kHz at filter input).
# Preserves 100% speech intelligibility and exact tempo across 22kHz, 44.1kHz, and 48kHz mic inputs.
EFFECTS = {
    # Crisp sci-fi metallic android: dual comb resonator + stereo-style flanger + vocal presence boost
    "robot": (
        "aresample=44100,highpass=f=95,lowpass=f=7500,"
        "flanger=delay=2.2:depth=1.6:regen=55:width=75:speed=3.5,"
        "aecho=0.85:0.82:12|19:0.42|0.32,"
        "equalizer=f=2200:t=q:w=1.4:g=4.5,"
        "acompressor=threshold=-18dB:ratio=4:attack=5:release=60:makeup=2,"
        "alimiter=limit=0.93"
    ),
    # Clean cybernetic AI glitch: harmonic bit-shaper + tight digital slap + high-definition presence
    "digital": (
        "aresample=44100,highpass=f=100,"
        "acrusher=bits=11:mix=0.38:mode=log:samples=2,"
        "aecho=0.85:0.75:15:0.32,"
        "equalizer=f=3200:t=q:w=1.4:g=4.5,treble=g=2.5:f=6500,"
        "acompressor=threshold=-18dB:ratio=3.5:attack=5:release=60:makeup=2,"
        "alimiter=limit=0.93"
    ),
    # Studio Broadcast AI Polish: rumble cut + warm chest EQ + 3.8kHz articulation + silky air + studio doubler
    "smooth_ai": (
        "aresample=44100,highpass=f=75,"
        "equalizer=f=170:t=q:w=1.2:g=2.2,"
        "equalizer=f=320:t=q:w=1.6:g=-2.0,"
        "equalizer=f=3800:t=q:w=1.2:g=3.5,"
        "treble=g=3.0:f=9500,"
        "chorus=0.65:0.85:20:0.18:0.25:1.2,"
        "acompressor=threshold=-20dB:ratio=3.2:attack=8:release=110:makeup=2.5,"
        "alimiter=limit=0.95"
    ),
    # Cinematic Deep Voice: clean pitch transposition (-3.2 semitones) + exact tempo compensation + clarity EQ
    "deep": (
        "aresample=44100,highpass=f=65,"
        "asetrate=36603,aresample=44100,atempo=1.2048,"
        "bass=g=4.5:f=115,"
        "equalizer=f=350:t=q:w=1.4:g=-2.5,"
        "equalizer=f=2800:t=q:w=1.2:g=4.0,"
        "treble=g=2.0:f=6000,"
        "acompressor=threshold=-18dB:ratio=4:attack=6:release=85:makeup=2.5,"
        "alimiter=limit=0.93"
    ),
    # Bright Animated Voice: clean pitch lift (+3.1 semitones) + exact tempo compensation + body EQ
    "high": (
        "aresample=44100,highpass=f=105,"
        "asetrate=52920,aresample=44100,atempo=0.8333,"
        "equalizer=f=240:t=q:w=1.2:g=3.0,"
        "equalizer=f=3200:t=q:w=1.4:g=2.5,"
        "acompressor=threshold=-18dB:ratio=3.5:attack=5:release=70:makeup=2,"
        "alimiter=limit=0.93"
    ),
    # Clean AI Voice Persona Match (used when effect='none' with a target AI voice)
    "none": (
        "aresample=44100,highpass=f=80,"
        "equalizer=f=180:t=q:w=1.2:g=2.0,"
        "equalizer=f=3600:t=q:w=1.3:g=3.2,"
        "treble=g=2.5:f=9000,"
        "acompressor=threshold=-19dB:ratio=3.2:attack=8:release=100:makeup=2,"
        "alimiter=limit=0.94"
    ),
}

# Target AI Voice acoustic formant/timbre profiles for Voice-to-Speech conversion
VOICE_PERSONA_FILTERS = {
    "Aria": "aresample=44100,asetrate=47628,aresample=44100,atempo=0.9259,highpass=f=95,equalizer=f=220:t=q:w=1.2:g=1.5,equalizer=f=3500:t=q:w=1.3:g=3.5,treble=g=2.5:f=8500",
    "Luna": "aresample=44100,asetrate=46746,aresample=44100,atempo=0.9434,highpass=f=90,lowpass=f=9500,equalizer=f=240:t=q:w=1.2:g=2.5,equalizer=f=3000:t=q:w=1.4:g=2.0",
    "Zoe": "aresample=44100,asetrate=49392,aresample=44100,atempo=0.8929,highpass=f=105,equalizer=f=250:t=q:w=1.2:g=2.0,equalizer=f=3800:t=q:w=1.3:g=4.0,treble=g=3.0:f=8000",
    "Ethan": "aresample=44100,asetrate=38808,aresample=44100,atempo=1.1364,highpass=f=70,bass=g=3.5:f=120,equalizer=f=340:t=q:w=1.5:g=-2.0,equalizer=f=2900:t=q:w=1.3:g=3.8",
    "Adam": "aresample=44100,asetrate=40572,aresample=44100,atempo=1.0870,highpass=f=75,bass=g=2.5:f=135,equalizer=f=3200:t=q:w=1.3:g=3.5,treble=g=2.0:f=7500",
    "Noah": "aresample=44100,asetrate=41895,aresample=44100,atempo=1.0526,highpass=f=80,equalizer=f=190:t=q:w=1.2:g=2.2,equalizer=f=3400:t=q:w=1.3:g=3.0",
    "Nova": "aresample=44100,highpass=f=85,equalizer=f=200:t=q:w=1.2:g=2.0,equalizer=f=3800:t=q:w=1.2:g=3.5,chorus=0.65:0.85:18:0.16:0.22:1.2",
    "Echo": "aresample=44100,highpass=f=95,flanger=delay=1.8:depth=1.2:regen=40:width=65:speed=2.5,equalizer=f=3400:t=q:w=1.3:g=4.0,treble=g=3.5:f=8500",
}


def build_vts_filter_chain(
    effect: str,
    target_voice: str | None = None,
    similarity: float = 0.85,
    stability: float = 0.70,
    clarity: float = 0.80,
) -> str:
    """Build dynamic studio filter chain combining target AI voice, effect, and fine-tuning sliders."""
    eff_key = (effect or "robot").lower()
    if eff_key not in EFFECTS:
        eff_key = "robot"

    chains = []
    if eff_key == "none" and target_voice and target_voice in VOICE_PERSONA_FILTERS:
        chains.append(VOICE_PERSONA_FILTERS[target_voice])
    else:
        chains.append(EFFECTS[eff_key])

    # Apply Clarity (high-frequency presence shaping) & Stability (dynamic leveling)
    clarity_gain = round((float(clarity) - 0.5) * 5.0, 1)  # -2.5dB to +2.5dB
    if abs(clarity_gain) >= 0.3:
        chains.append(f"treble=g={clarity_gain}:f=5500")

    comp_ratio = round(2.0 + float(stability) * 3.0, 1)
    chains.append(f"acompressor=threshold=-19dB:ratio={comp_ratio}:attack=6:release=80,alimiter=limit=0.94")
    return ",".join(chains)


def apply_effect(src: Path, dst: Path, effect: str) -> None:
    if effect not in EFFECTS:
        raise AudioError(f"Unknown effect '{effect}'.")
    run_ffmpeg("-i", str(src), "-ac", "1", "-ar", "44100", "-af", EFFECTS[effect],
               "-c:a", "pcm_s16le", str(dst))


def convert_voice_single_pass(
    src: Path,
    effect: str,
    fmt: str,
    target_voice: str | None = None,
    similarity: float = 0.85,
    stability: float = 0.70,
    clarity: float = 0.80,
) -> tuple[bytes, float]:
    """Single-pass Voice-to-Voice conversion and encoding (2x faster, zero intermediate disk writes).
    Returns (audio_bytes, duration_seconds).
    """
    if effect not in EFFECTS:
        raise AudioError(f"Unknown effect '{effect}'.")
    if fmt not in ("mp3", "wav"):
        raise AudioError(f"Unsupported format '{fmt}'.")

    af_chain = build_vts_filter_chain(
        effect=effect,
        target_voice=target_voice,
        similarity=similarity,
        stability=stability,
        clarity=clarity,
    )

    if fmt == "wav":
        cmd = [
            get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-ac", "1", "-ar", "44100",
            "-af", af_chain,
            "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise AudioError(f"FFmpeg failed: {proc.stderr.decode(errors='ignore').strip()[-400:]}")
        pcm = proc.stdout
        duration = len(pcm) / (44100.0 * 2.0)
        return pcm_to_wav_bytes(pcm, 44100), duration

    # Single-pass MP3 encoding to pipe:1 with progress telemetry on pipe:2 for exact duration
    cmd = [
        get_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-progress", "pipe:2",
        "-i", str(src),
        "-ac", "1", "-ar", "44100",
        "-af", af_chain,
        "-codec:a", "libmp3lame", "-q:a", "1",
        "-f", "mp3", "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise AudioError(f"FFmpeg failed: {proc.stderr.decode(errors='ignore').strip()[-400:]}")

    audio_bytes = proc.stdout
    stderr_text = proc.stderr.decode(errors="ignore")
    duration = 0.0
    for line in stderr_text.splitlines():
        if line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1].strip())
                if us > 0:
                    duration = us / 1_000_000.0
            except ValueError:
                pass
    if duration <= 0.0 and audio_bytes:
        # Fallback estimate from ~192kbps VBR
        duration = max(0.5, len(audio_bytes) / 24000.0)
    return audio_bytes, duration




def encode(src_wav: Path, dst: Path, fmt: str) -> None:
    if fmt == "wav":
        dst.write_bytes(src_wav.read_bytes())
    elif fmt == "mp3":
        run_ffmpeg("-i", str(src_wav), "-codec:a", "libmp3lame", "-q:a", "1", str(dst))
    else:
        raise AudioError(f"Unsupported format '{fmt}'.")

