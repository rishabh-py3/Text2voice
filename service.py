"""Core logic, independent of the web framework so it is easy to test."""
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import audio_utils as au
from engines import VOICES, pick_engine, synth_segment

MAX_CHARS = 5000
PAUSE_SECONDS = 0.6
PAUSE_RE = re.compile(r"\[pause\]", re.IGNORECASE)


@dataclass
class AudioResult:
    data: bytes
    fmt: str
    duration: float

    @property
    def mimetype(self) -> str:
        return "audio/mpeg" if self.fmt == "mp3" else "audio/wav"


def humanize_text(text: str) -> str:
    """Normalize text for natural, human-like speech synthesis.
    - Strips or humanizes symbols that TTS engines vocalize literally (e.g. '/', '*', '#', '&', quotes, brackets, bullets).
    - Converts spoken punctuation commands like 'full stop', 'fullstop', 'period', 'comma', 'question mark'
      into natural sentence terminators (.) and pauses so the voice pauses/stops naturally instead of speaking symbol names.
    - Preserves internal contraction apostrophes like don't, it's, we'll, I'm.
    - Ensures clean sentence-ending cadence so the voice stops talking cleanly.
    """
    if not text:
        return ""

    # 1. Protect intentional [pause] tags with alphanumeric token
    text = re.sub(r"(?i)\[\s*(?:pause|silence)\s*\]", " SPEECHPAUSETOKEN ", text)

    # 2. Normalize spoken punctuation words (dictation / speech-to-text / verbal commands)
    text = re.sub(r"(?i)[\[\(]\s*(?:full\s*stop|full-stop|fullstop|period)\s*[\]\)]", " . ", text)
    text = re.sub(r"(?i)(?<=[.!?])\s*(?:full\s*stop|full-stop|fullstop)\s*\.?", "", text)
    text = re.sub(r"(?i)\b(?:full\s*stop|full-stop|fullstop)\s*\.?", ".", text)

    text = re.sub(r"(?i)(?<=\?)\s*(?:question\s*mark)\s*\??", "", text)
    text = re.sub(r"(?i)\b(?:question\s*mark)\s*\??", "?", text)

    text = re.sub(r"(?i)(?<=!)\s*(?:exclamation\s*(?:mark|point))\s*!?", "", text)
    text = re.sub(r"(?i)\b(?:exclamation\s*(?:mark|point))\s*!?", "!", text)

    text = re.sub(r"(?i)\b(?:semi\s*colon|semicolon)\b", ";", text)
    text = re.sub(r"(?i)\b(?:dot\s*dot\s*dot|ellipsis)\b", "...", text)
    text = re.sub(r"(?i)\bcomma\b(?=[,\s]|$)", ",", text)
    text = re.sub(r"(?i)\bperiod\b(?=[.\s]|$)", ".", text)

    # 3. Humanize symbols that TTS engines read out literally (like "slash", "asterisk", "hash", etc.)
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"(\w)\s*/\s*(\w)", r"\1 or \2", text)
    text = re.sub(r"[/\\|~^]", ", ", text)
    text = re.sub(r"[*_`]+", " ", text)
    text = re.sub(r"#(\d+)", r"number \1", text)
    text = re.sub(r"#([a-zA-Z])", r"\1", text)
    text = re.sub(r"#+", " ", text)
    text = re.sub(r"[\u2022\u25aa\u25ab\u25e6\u2013\u2014]+", ", ", text)

    # Protect internal contraction apostrophes (don't, it's, we'll, I'm) while removing quotes/brackets
    text = re.sub(r"(\w)\x27(\w)", r"\g<1>CONTRACTIONAPOSTROPHE\g<2>", text)
    text = re.sub(r"[\(\)\[\]\{\}\"\x27“”‘’«»]", " ", text)
    text = text.replace("CONTRACTIONAPOSTROPHE", "'")

    # 4. Normalize punctuation spacing & repetitive marks
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r",{2,}", ",", text)

    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"\.[,;:]+", ".", text)
    text = re.sub(r",\.", ".", text)
    text = re.sub(r"([.,!?;:])([A-Za-z0-9])", r"\1 \2", text)

    # Restore [pause] tags
    text = re.sub(r"SPEECHPAUSETOKEN", "[pause]", text)
    text = re.sub(r"[ \t]+", " ", text).strip()

    # Ensure sentence has ending punctuation so voice stops naturally
    if text and text[-1] not in ".!?":
        text += "."

    return text


def synthesize(text: str, voice: str, speed: float = 1.0, fmt: str = "mp3", pause_seconds: float = PAUSE_SECONDS) -> AudioResult:
    text = humanize_text(text)
    if not text or not any(c.isalnum() for c in text):
        raise ValueError("Text contains no speakable words.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"Text is too long (max {MAX_CHARS} characters).")
    if voice not in VOICES:
        raise ValueError(f"Unknown voice '{voice}'.")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Speed must be between 0.5 and 2.0.")
    if fmt not in ("mp3", "wav"):
        raise ValueError("Format must be mp3 or wav.")

    parts = [p.strip() for p in PAUSE_RE.split(text) if p.strip()]
    if not parts:
        raise ValueError("Text only contains pauses.")

    engine = pick_engine()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        seg_files = []
        for i, part in enumerate(parts):
            seg = tmp / f"seg{i}.wav"
            synth_segment(part, voice, engine, seg, speed=speed)
            seg_files.append(seg)

        joined, final = tmp / "joined.wav", tmp / f"out.{fmt}"
        au.concat_with_pauses(seg_files, pause_seconds, joined)
        # Note: synth_segment already synthesized speech at the exact target speed
        # using the engine's native phoneme length-scale / rate, avoiding atempo artifacts.
        au.encode(joined, final, fmt)
        return AudioResult(final.read_bytes(), fmt, au.wav_duration(joined))


def convert_voice(upload: bytes, filename: str, effect: str, fmt: str = "mp3") -> AudioResult:
    if effect not in au.EFFECTS:
        raise ValueError(f"Unknown effect '{effect}'.")
    if fmt not in ("mp3", "wav"):
        raise ValueError("Format must be mp3 or wav.")

    suffix = Path(filename).suffix.lower() or ".webm"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / f"in{suffix}"
        src.write_bytes(upload)
        processed, final = tmp / "fx.wav", tmp / f"out.{fmt}"
        au.apply_effect(src, processed, effect)
        au.encode(processed, final, fmt)
        return AudioResult(final.read_bytes(), fmt, au.wav_duration(processed))
