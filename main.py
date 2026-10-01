"""AI Voice Studio backend. Run: uvicorn main:app --reload then open http://localhost:8000"""
import datetime
import json
import os
import platform
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import service
from audio_utils import EFFECTS, AudioError
from engines import VOICES, VOICES_DIR, pick_engine

BASE = Path(__file__).parent
STATIC = BASE / "static"
OUTPUTS_DIR = BASE / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
METADATA_FILE = OUTPUTS_DIR / "metadata.json"

MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB, matches the UI
ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".mp4", ".aac", ".flac"}

app = FastAPI(title="AI Voice Studio")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Runtime settings
RUNTIME_SETTINGS = {
    "engine": "auto",
    "default_voice": "Aria",
    "default_speed": 1.0,
    "default_format": "mp3",
    "pause_duration": 0.6,
}


def _load_metadata() -> list[dict]:
    if not METADATA_FILE.exists():
        return []
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_metadata(records: list[dict]):
    METADATA_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _record_output(result: service.AudioResult, title: str, kind: str, voice_or_effect: str) -> dict:
    file_id = f"{int(datetime.datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"
    filename = f"{kind}_{file_id}.{result.fmt}"
    file_path = OUTPUTS_DIR / filename
    file_path.write_bytes(result.data)

    record = {
        "id": file_id,
        "filename": filename,
        "title": title[:80] + ("…" if len(title) > 80 else ""),
        "full_text": title if kind == "tts" else "",
        "kind": kind,  # "tts" or "vts"
        "voice_or_effect": voice_or_effect,
        "format": result.fmt,
        "duration": round(result.duration, 2),
        "size": len(result.data),
        "created_at": datetime.datetime.now().strftime("%b %d, %Y, %I:%M %p"),
        "timestamp": int(datetime.datetime.now().timestamp()),
        "url": f"/api/files/{file_id}/audio",
    }

    records = _load_metadata()
    records.insert(0, record)
    _save_metadata(records)
    return record


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=service.MAX_CHARS)
    voice: str = "Aria"
    speed: float = 1.0
    format: str = "mp3"
    pause_duration: float | None = None


class SettingsUpdate(BaseModel):
    engine: str | None = None
    default_voice: str | None = None
    default_speed: float | None = None
    default_format: str | None = None
    pause_duration: float | None = None


def _audio_response(result: service.AudioResult, name: str, file_id: str | None = None) -> Response:
    headers = {
        "X-Audio-Duration": f"{result.duration:.2f}",
        "Content-Disposition": f'inline; filename="{name}.{result.fmt}"',
        "Cache-Control": "no-store",
    }
    if file_id:
        headers["X-File-Id"] = file_id
    return Response(
        content=result.data,
        media_type=result.mimetype,
        headers=headers,
    )


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    try:
        engine = pick_engine()
    except AudioError as e:
        engine = f"unavailable: {e}"
    return {
        "ok": True,
        "engine": engine,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


@app.get("/api/voices")
def voices():
    res = []
    for name, v in VOICES.items():
        res.append({
            "name": name,
            "type": v["gender"],
            "gender": v["gender"],
            "accent": v.get("accent", "American (US)"),
            "tone": v.get("tone", "Natural"),
            "description": v.get("description", "Natural sounding speech synthesis voice."),
            "model": v["piper"],
            "sample_url": f"/api/voices/{name}/sample",
        })
    return res


@app.get("/api/effects")
def effects():
    descriptions = {
        "robot": "Metallic robotic resonator with modulated harmonics",
        "digital": "8-bit glitch bitcrusher & lo-fi synthetic crunch",
        "smooth_ai": "Studio multi-voice chorus with warm dynamic compression",
        "deep": "Sub-bass resonant transposition for cinematic announcer tone",
        "high": "Fast formant transposition for bright & energetic cartoon tone",
    }
    return [
        {"id": k, "name": k.replace("_", " ").title(), "description": descriptions.get(k, "Audio filter")}
        for k in EFFECTS.keys()
    ]


@app.post("/api/text-to-speech")
def text_to_speech(req: TTSRequest):
    pause_sec = req.pause_duration if req.pause_duration is not None else RUNTIME_SETTINGS.get("pause_duration", 0.6)
    try:
        result = service.synthesize(req.text, req.voice, req.speed, req.format, pause_seconds=pause_sec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except AudioError as e:
        raise HTTPException(503, str(e))

    rec = _record_output(result, req.text, "tts", req.voice)
    return _audio_response(result, f"{req.voice}-voice", file_id=rec["id"])


_sample_cache: dict[str, service.AudioResult] = {}


@app.get("/api/voices/{name}/sample")
def voice_sample(name: str):
    if name not in VOICES:
        raise HTTPException(404, "Unknown voice")
    if name not in _sample_cache:
        try:
            _sample_cache[name] = service.synthesize(
                f"Hi, I'm {name}. Welcome to AI Voice Studio. This is how I sound.",
                name, 1.0, "mp3"
            )
        except AudioError as e:
            raise HTTPException(503, str(e))
    return _audio_response(_sample_cache[name], f"{name}-sample")


@app.post("/api/voice-convert")
async def voice_convert(
    file: UploadFile = File(...),
    effect: str = Form("robot"),
    format: str = Form("mp3"),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext and ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'.")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 10MB.")
    if not data:
        raise HTTPException(400, "Empty file.")
    try:
        result = service.convert_voice(data, file.filename or "recording.webm", effect, format)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except AudioError as e:
        raise HTTPException(422, f"Could not process that audio: {e}")

    title = file.filename or f"recording-{datetime.datetime.now().strftime('%H%M%S')}"
    rec = _record_output(result, title, "vts", effect)
    return _audio_response(result, "converted-voice", file_id=rec["id"])


# ---------------- Files Management ----------------

@app.get("/api/files")
def list_files():
    return _load_metadata()


@app.get("/api/files/{file_id}/audio")
def get_file_audio(file_id: str):
    records = _load_metadata()
    match = next((r for r in records if r["id"] == file_id), None)
    if not match:
        raise HTTPException(404, "File not found")
    path = OUTPUTS_DIR / match["filename"]
    if not path.exists():
        raise HTTPException(404, "File missing from disk")
    media_type = "audio/mpeg" if match["format"] == "mp3" else "audio/wav"
    return FileResponse(
        path,
        media_type=media_type,
        filename=match["filename"],
        headers={"Content-Disposition": f'inline; filename="{match["filename"]}"'},
    )


@app.get("/api/files/{file_id}/download")
def download_file(file_id: str):
    records = _load_metadata()
    match = next((r for r in records if r["id"] == file_id), None)
    if not match:
        raise HTTPException(404, "File not found")
    path = OUTPUTS_DIR / match["filename"]
    if not path.exists():
        raise HTTPException(404, "File missing from disk")
    media_type = "audio/mpeg" if match["format"] == "mp3" else "audio/wav"
    return FileResponse(
        path,
        media_type=media_type,
        filename=match["filename"],
        headers={"Content-Disposition": f'attachment; filename="{match["filename"]}"'},
    )


@app.delete("/api/files/{file_id}")
def delete_file(file_id: str):
    records = _load_metadata()
    match = next((r for r in records if r["id"] == file_id), None)
    if not match:
        raise HTTPException(404, "File not found")
    path = OUTPUTS_DIR / match["filename"]
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    records = [r for r in records if r["id"] != file_id]
    _save_metadata(records)
    return {"ok": True, "deleted": file_id}


@app.post("/api/files/clear")
def clear_files():
    for f in OUTPUTS_DIR.glob("*.*"):
        if f.name != "metadata.json":
            try:
                f.unlink()
            except OSError:
                pass
    _save_metadata([])
    return {"ok": True}


# ---------------- Settings API ----------------

@app.get("/api/settings")
def get_settings():
    try:
        active_engine = pick_engine()
    except AudioError as e:
        active_engine = f"error: {e}"

    voices_info = []
    for k, v in VOICES.items():
        onnx_file = VOICES_DIR / f"{v['piper']}.onnx"
        voices_info.append({
            "name": k,
            "piper_model": v["piper"],
            "installed": onnx_file.exists(),
            "size_mb": round(onnx_file.stat().st_size / (1024 * 1024), 1) if onnx_file.exists() else 0,
        })

    records = _load_metadata()
    total_bytes = sum(r.get("size", 0) for r in records)

    return {
        "engine": RUNTIME_SETTINGS["engine"],
        "active_engine": active_engine,
        "available_engines": ["auto", "piper", "say", "dummy"],
        "default_voice": RUNTIME_SETTINGS["default_voice"],
        "default_speed": RUNTIME_SETTINGS["default_speed"],
        "default_format": RUNTIME_SETTINGS["default_format"],
        "pause_duration": RUNTIME_SETTINGS["pause_duration"],
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "installed_voices": voices_info,
        "files_count": len(records),
        "files_size_bytes": total_bytes,
    }


@app.post("/api/settings")
def update_settings(update: SettingsUpdate):
    if update.engine is not None:
        RUNTIME_SETTINGS["engine"] = update.engine
        if update.engine == "auto":
            os.environ.pop("TTS_ENGINE", None)
        else:
            os.environ["TTS_ENGINE"] = update.engine
    if update.default_voice is not None:
        if update.default_voice in VOICES:
            RUNTIME_SETTINGS["default_voice"] = update.default_voice
    if update.default_speed is not None:
        if 0.5 <= update.default_speed <= 2.0:
            RUNTIME_SETTINGS["default_speed"] = update.default_speed
    if update.default_format is not None:
        if update.default_format in ("mp3", "wav"):
            RUNTIME_SETTINGS["default_format"] = update.default_format
    if update.pause_duration is not None:
        if 0.0 <= update.pause_duration <= 5.0:
            RUNTIME_SETTINGS["pause_duration"] = update.pause_duration
            service.PAUSE_SECONDS = update.pause_duration

    return {"ok": True, "settings": RUNTIME_SETTINGS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

