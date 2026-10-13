"""Core logic, independent of the web framework so it is easy to test."""
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import audio_utils as au
from engines import VOICES, pick_engine, synth_segment, synth_segment_pcm

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


def expand_currencies(text: str) -> str:
    """Expand currency symbols into natural spoken English."""
    def _dollar_sub(m):
        amt = m.group(1).replace(",", "")
        if "." in amt:
            dollars, cents = amt.split(".", 1)
            cents = cents[:2].ljust(2, "0")
            c_int = int(cents)
            d_int = int(dollars) if dollars else 0
            if d_int == 0 and c_int > 0:
                return f"{c_int} cents"
            elif c_int > 0:
                return f"{dollars} dollars and {c_int} cents"
            return f"{dollars} dollars"
        return f"{amt} dollars"

    text = re.sub(r"\$(\d+(?:,\d{3})*(?:\.\d+)?)", _dollar_sub, text)
    text = re.sub(r"€(\d+(?:,\d{3})*(?:\.\d+)?)", r"\1 euros", text)
    text = re.sub(r"£(\d+(?:,\d{3})*(?:\.\d+)?)", r"\1 pounds", text)
    text = re.sub(r"₹(\d+(?:,\d{3})*(?:\.\d+)?)", r"\1 rupees", text)
    text = re.sub(r"¥(\d+(?:,\d{3})*(?:\.\d+)?)", r"\1 yen", text)
    return text


def humanize_text(text: str, emotion: str = "neutral") -> str:
    """Normalize text for natural, human-like speech synthesis.
    - Never deletes real English words like 'period' or 'comma'.
    - Converts spoken dictation commands only when bracketed: [period], [full stop], [comma].
    - Expands currencies ($50 -> 50 dollars), percentages (20% -> 20 percent), and titles (Dr. -> Doctor).
    - Preserves internal contraction apostrophes (don't, it's, we'll, I'm) and possessives.
    - Applies emotion-aware prosody punctuation (e.g. sad uses soft '.', excited uses '!').
    """
    if not text:
        return ""

    # 1. Protect intentional [pause] tags with token
    text = re.sub(r"(?i)\[\s*(?:pause|silence)\s*\]", " SPEECHPAUSETOKEN ", text)

    # 2. Only convert explicit dictation bracketed commands to punctuation
    text = re.sub(r"(?i)[\[\(]\s*(?:full\s*stop|full-stop|fullstop|period)\s*[\]\)]", ".", text)
    text = re.sub(r"(?i)[\[\(]\s*comma\s*[\]\)]", ",", text)
    text = re.sub(r"(?i)[\[\(]\s*(?:question\s*mark)\s*[\]\)]", "?", text)
    text = re.sub(r"(?i)[\[\(]\s*(?:exclamation\s*(?:mark|point))\s*[\]\)]", "!", text)
    text = re.sub(r"(?i)[\[\(]\s*(?:ellipsis|dot\s*dot\s*dot)\s*[\]\)]", "...", text)
    text = re.sub(r"(?i)[\[\(]\s*(?:semi\s*colon|semicolon)\s*[\]\)]", ";", text)

    # 3. Strip any residual emotion tag brackets so they are never spoken aloud
    text = re.sub(r"\[[a-zA-Z_\-]+\]", " ", text)

    # 4. Currencies & percentages
    text = expand_currencies(text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", text)

    # 5. Common abbreviations & titles
    abbrevs = [
        (r"\bDr\.(?=\s+[A-Z])", "Doctor"),
        (r"\bMr\.(?=\s+[A-Z])", "Mister"),
        (r"\bMrs\.(?=\s+[A-Z])", "Missus"),
        (r"\bMs\.(?=\s+[A-Z])", "Ms"),
        (r"\bProf\.(?=\s+[A-Z])", "Professor"),
        (r"\bSt\.(?=\s+[A-Z])", "Saint"),
        (r"\bvs\.(?=\s+)", "versus"),
        (r"\betc\.(?=[,\s.]|$)", "etcetera"),
        (r"\be\.g\.,?", "for example,"),
        (r"\bi\.e\.,?", "that is,"),
        (r"\bapprox\.(?=\s+\d)", "approximately"),
    ]
    for pat, rep in abbrevs:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)

    # 6. Natural spoken substitutions for symbols
    text = re.sub(r"(?i)\band/or\b", "and or", text)
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"(\b\w+)\s*/\s*(\w+\b)", r"\1 or \2", text)
    text = re.sub(r"#(\d+)", r"number \1", text)
    text = re.sub(r"#([a-zA-Z])", r"\1", text)
    text = re.sub(r"[\u2022\u25aa\u25ab\u25e6\u2013\u2014]+", ", ", text)
    text = re.sub(r"[/\\|~^*_`]+", " ", text)

    # 7. Protect contractions and possessives (don't, it's, we'll, I'm, John's)
    text = re.sub(r"(\w)['\’](\w)", r"\1CONTRACTIONAPOS\2", text)
    text = re.sub(r"[\(\)\[\]\{\}\"“”«»`]", " ", text)
    text = text.replace("CONTRACTIONAPOS", "'")

    # 8. Punctuation spacing & repetitive cleanup
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

    # 9. Emotion-aware prosody punctuation
    if emotion in ("sad", "whisper", "calm"):
        # Soften shouting marks to sorrowful or quiet intimate cadence
        text = re.sub(r"!+", ".", text)
    elif emotion == "excited":
        # Ensure sentence triggers neural rising pitch inflection
        if text.endswith("."):
            text = text[:-1] + "!"
    elif emotion == "curious":
        if text.endswith((".", "!")):
            text = text[:-1] + "?"

    # Restore [pause] tags
    text = re.sub(r"SPEECHPAUSETOKEN", "[pause]", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text and text[-1] not in ".!?":
        text += "."

    return text


EMOTION_TAGS = {
    "laugh": ["laugh", "laughter", "giggle", "cackle", "ha"],
    "chuckle": ["chuckle", "snicker", "smirk", "heh"],
    "sigh": ["sigh", "breath", "exhale", "relief"],
    "gasp": ["gasp", "shock", "surprise", "pant"],
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

    # Determine emotions across speech segments
    speech_items = [item for item in script if item[0] == "speech"]
    emotions_used = set(item[1][1] for item in speech_items)
    is_single_emotion = len(emotions_used) <= 1
    dominant_emotion = next(iter(emotions_used)) if emotions_used else "neutral"

    silence_bytes = b"\x00\x00" * int(au.SAMPLE_RATE * max(0.05, pause_seconds))
    pcm_segments = []

    for item in script:
        kind = item[0]
        if kind == "pause":
            pcm_segments.append(silence_bytes)
        elif kind == "speech":
            txt, emotion = item[1]
            clean = humanize_text(txt, emotion=emotion)
            if clean and any(c.isalnum() for c in clean):
                pcm = synth_segment_pcm(clean, voice, engine, speed=speed, emotion=emotion)
                if not is_single_emotion and emotion != "neutral":
                    # For mixed emotions in a script, apply acoustic shaping per segment
                    pcm = au.filter_pcm(pcm, emotion)
                pcm_segments.append(pcm)

    if not pcm_segments or not any(s != silence_bytes for s in pcm_segments):
        raise ValueError("No speakable audio could be generated.")

    all_pcm = b"".join(pcm_segments)
    filter_emotion = dominant_emotion if is_single_emotion else "neutral"
    audio_data = au.encode_pcm_to_audio(all_pcm, fmt=fmt, emotion=filter_emotion)
    duration = len(all_pcm) / (au.SAMPLE_RATE * 2.0)
    return AudioResult(audio_data, fmt, duration)


def convert_voice(
    upload: bytes,
    filename: str,
    effect: str = "robot",
    fmt: str = "mp3",
    target_voice: str | None = None,
    similarity: float = 0.85,
    stability: float = 0.70,
    clarity: float = 0.80,
) -> AudioResult:
    if effect not in au.EFFECTS:
        raise ValueError(f"Unknown effect '{effect}'.")
    if fmt not in ("mp3", "wav"):
        raise ValueError("Format must be mp3 or wav.")

    suffix = Path(filename).suffix.lower() or ".webm"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{suffix}"
        src.write_bytes(upload)
        audio_bytes, duration = au.convert_voice_single_pass(
            src,
            effect,
            fmt,
            target_voice=target_voice,
            similarity=similarity,
            stability=stability,
            clarity=clarity,
        )
        return AudioResult(audio_bytes, fmt, duration)


