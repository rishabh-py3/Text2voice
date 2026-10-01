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


EMOTION_TAGS = {
    "excited": ["excited", "happy", "cheerful", "joy", "enthusiastic", "thrilled"],
    "sad": ["sad", "sorrow", "gloomy", "depressed", "melancholy", "crying"],
    "angry": ["angry", "furious", "mad", "shouting", "aggressive"],
    "whisper": ["whisper", "whispering", "soft", "quiet", "secret"],
    "calm": ["calm", "relaxed", "peaceful", "soothing", "gentle"],
    "dramatic": ["dramatic", "epic", "cinematic", "storyteller"],
    "fear": ["fear", "scared", "nervous", "terrified", "trembling", "anxious"],
    "serious": ["serious", "formal", "grave", "authoritative"],
    "curious": ["curious", "inquisitive", "puzzled"],
}

ALIAS_TO_EMO = {}
for emo, aliases in EMOTION_TAGS.items():
    for a in aliases:
        ALIAS_TO_EMO[a] = emo

TAG_RE = re.compile(r"\[([a-zA-Z_\-]+)\]")


def parse_speech_script(text: str) -> list[tuple[str, any]]:
    """Parse text with inline emotion tags [excited] and pauses [pause] into structured segments.
    Supports both postfix (e.g. 'happy birthday[excited]') and prefix (e.g. '[excited] happy birthday!').
    Returns a list of ('pause', None) or ('speech', (text, emotion)).
    """
    tokens = []
    last_idx = 0
    for m in TAG_RE.finditer(text):
        start, end = m.span()
        tag = m.group(1).lower().strip()
        if start > last_idx:
            raw_text = text[last_idx:start]
            if raw_text:
                tokens.append(("text", raw_text))
        tokens.append(("tag", tag))
        last_idx = end
    if last_idx < len(text):
        raw_text = text[last_idx:]
        if raw_text:
            tokens.append(("text", raw_text))

    items = []
    current_emo = "neutral"
    has_prefix_emo = False

    i = 0
    n = len(tokens)
    while i < n:
        kind, val = tokens[i]
        if kind == "tag":
            if val in ("pause", "silence"):
                items.append(("pause", None))
                has_prefix_emo = False
                i += 1
            elif val in ALIAS_TO_EMO:
                current_emo = ALIAS_TO_EMO[val]
                has_prefix_emo = True
                i += 1
            elif val in ("neutral", "normal", "reset"):
                current_emo = "neutral"
                has_prefix_emo = True
                i += 1
            else:
                items.append(("speech", (f"[{val}]", current_emo)))
                has_prefix_emo = False
                i += 1
        elif kind == "text":
            txt = val.strip()
            if not has_prefix_emo and i + 1 < n and tokens[i+1][0] == "tag" and tokens[i+1][1] in ALIAS_TO_EMO:
                # Postfix tag without an explicit prefix tag: e.g. "happy birthday[excited]"
                emo = ALIAS_TO_EMO[tokens[i+1][1]]
                if txt:
                    items.append(("speech", (txt, emo)))
                current_emo = emo
                has_prefix_emo = False
                i += 2
            else:
                if txt:
                    items.append(("speech", (txt, current_emo)))
                has_prefix_emo = False
                i += 1

    return items


def synthesize(text: str, voice: str, speed: float = 1.0, fmt: str = "mp3", pause_seconds: float = PAUSE_SECONDS) -> AudioResult:
    if not text or not text.strip():
        raise ValueError("Please provide text to speak.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"Text is too long (max {MAX_CHARS} characters).")
    if voice not in VOICES:
        raise ValueError(f"Unknown voice '{voice}'.")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Speed must be between 0.5 and 2.0.")
    if fmt not in ("mp3", "wav"):
        raise ValueError("Format must be mp3 or wav.")

    script = parse_speech_script(text)
    if not any(item[0] == "speech" for item in script):
        raise ValueError("Text contains no speakable words.")

    engine = pick_engine()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        seg_files = []
        for i, item in enumerate(script):
            kind = item[0]
            if kind == "pause":
                silence_wav = tmp / f"pause_{i}.wav"
                au.generate_silence(pause_seconds, silence_wav)
                seg_files.append(silence_wav)
            elif kind == "speech":
                txt, emotion = item[1]
                clean = humanize_text(txt)
                if clean and any(c.isalnum() for c in clean):
                    seg_wav = tmp / f"speech_{i}.wav"
                    synth_segment(clean, voice, engine, seg_wav, speed=speed, emotion=emotion)
                    seg_files.append(seg_wav)

        if not seg_files:
            raise ValueError("No speakable audio could be generated.")

        joined, final = tmp / "joined.wav", tmp / f"out.{fmt}"
        au.concat_wavs(seg_files, joined)
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
