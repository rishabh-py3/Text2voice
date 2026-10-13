"""AI Voice Studio backend with Multi-User Authentication and Private File Scoping.
Run: uvicorn main:app --reload then open http://localhost:8000
"""
import datetime
import os
import platform
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import service
from audio_utils import EFFECTS, AudioError, get_ffmpeg_bin
from engines import VOICES, VOICES_DIR, clear_runtime_caches, pick_engine

BASE = Path(__file__).parent
STATIC = BASE / "static"
OUTPUTS_DIR = BASE / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

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
    "default_similarity": 0.85,
    "output_quality": "high",
    "auto_play": True,
    "auto_download": False,
    "show_tips": False,
}



@app.on_event("startup")
def on_startup():
    db.init_db()
    try:
        # Clean up any leftover guest audio files from previous runs
        db.cleanup_stale_guests(max_idle_seconds=60)
    except Exception:
        pass
    try:
        from engines import preload_voices
        preload_voices()
    except Exception:
        pass


# ---------------- Session & Auth Helpers ----------------

def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    if request.headers.get("X-Session-Token"):
        return request.headers.get("X-Session-Token")
    if "token" in request.query_params:
        return request.query_params["token"]
    if request.cookies.get("session_token"):
        return request.cookies.get("session_token")
    return None


def get_current_session(request: Request) -> dict:
    """Retrieve existing session from Header, Cookie, or Query Param, or create a guest session."""
    token = _extract_token(request)
    session = db.get_session(token) if token else None
    if not session:
        new_token, guest_info = db.create_guest_session()
        session = {
            "token": new_token,
            "user_id": guest_info["id"],
            "username": guest_info["username"],
            "is_guest": True,
            "is_new": True,
        }
    return session


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,  # 30 days
        httponly=False,
        samesite="lax",
    )
    response.headers["X-Session-Token"] = token


def _record_output(result: service.AudioResult, title: str, kind: str, voice_or_effect: str, user_id: str) -> dict:
    # Periodically purge inactive guest data to prevent disk overload
    try:
        db.cleanup_stale_guests(max_idle_seconds=900)
    except Exception:
        pass

    file_id = f"{int(datetime.datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"
    filename = f"{kind}_{file_id}.{result.fmt}"
    file_path = OUTPUTS_DIR / filename
    file_path.write_bytes(result.data)

    created_at = datetime.datetime.now().strftime("%b %d, %Y, %I:%M %p")
    timestamp = int(datetime.datetime.now().timestamp())

    rec = db.save_file_record(
        file_id=file_id,
        user_id=user_id,
        filename=filename,
        title=title,
        full_text=title if kind == "tts" else "",
        kind=kind,
        voice_or_effect=voice_or_effect,
        fmt=result.fmt,
        duration=result.duration,
        size=len(result.data),
        created_at=created_at,
        timestamp=timestamp,
    )

    if user_id.startswith("guest_"):
        try:
            db.enforce_guest_file_limit(user_id, max_files=10)
        except Exception:
            pass

    return rec


class AuthRequest(BaseModel):
    username: str
    password: str
    guest_token: str | None = None


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
    default_similarity: float | None = None
    output_quality: str | None = None
    auto_play: bool | None = None
    auto_download: bool | None = None
    show_tips: bool | None = None



def _audio_response(result: service.AudioResult, name: str, file_id: str | None = None, token: str | None = None) -> Response:
    headers = {
        "X-Audio-Duration": f"{result.duration:.2f}",
        "Content-Disposition": f'inline; filename="{name}.{result.fmt}"',
        "Cache-Control": "no-store",
    }
    if file_id:
        headers["X-File-Id"] = file_id
    if token:
        headers["X-Session-Token"] = token
    return Response(
        content=result.data,
        media_type=result.mimetype,
        headers=headers,
    )


@app.get("/")
def index():
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )


@app.get("/api/health")
def health():
    try:
        engine = pick_engine()
    except AudioError as e:
        engine = f"unavailable: {e}"
    return {
        "ok": True,
        "engine": engine,
        "ffmpeg": bool(get_ffmpeg_bin()),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


# ---------------- Authentication & Guest Cleanup Endpoints ----------------

@app.post("/api/guest/cleanup")
async def guest_cleanup(request: Request):
    """Automatically invoked via navigator.sendBeacon / keepalive fetch when a Guest user
    closes the website tab/window. Immediately deletes all their generated audio files from
    disk, removes their guest DB rows, and frees temporary RAM caches.
    """
    token = _extract_token(request)
    if not token:
        try:
            body = await request.json()
            if isinstance(body, dict):
                token = body.get("token")
        except Exception:
            pass

    deleted_files = 0
    if token:
        sess = db.get_session(token)
        if sess and (sess.get("is_guest") or str(sess.get("user_id", "")).startswith("guest_")):
            deleted_files = db.cleanup_guest_session_and_files(sess["user_id"], token=token)

    try:
        db.cleanup_stale_guests(max_idle_seconds=900)
        clear_runtime_caches(evict_models=False)
    except Exception:
        pass

    return {"ok": True, "deleted_files": deleted_files}


@app.get("/api/auth/me")
def auth_me(request: Request, response: Response):
    session = get_current_session(request)
    if session.get("is_new"):
        set_session_cookie(response, session["token"])
    return {
        "ok": True,
        "token": session["token"],
        "user": {
            "id": session["user_id"],
            "username": session["username"],
            "is_guest": session["is_guest"],
        }
    }


@app.post("/api/auth/register")
def auth_register(req: AuthRequest, request: Request, response: Response):
    try:
        user = db.create_user(req.username, req.password)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Migrate guest files into new permanent account
    current_session = get_current_session(request)
    if current_session.get("is_guest"):
        db.migrate_guest_files(current_session["user_id"], user["id"])
        db.delete_session(current_session["token"])
    if req.guest_token:
        guest_sess = db.get_session(req.guest_token)
        if guest_sess and guest_sess.get("is_guest"):
            db.migrate_guest_files(guest_sess["user_id"], user["id"])
            db.delete_session(req.guest_token)

    token = db.create_session(user["id"], user["username"], is_guest=False)
    set_session_cookie(response, token)
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "is_guest": False,
        }
    }


@app.post("/api/auth/login")
def auth_login(req: AuthRequest, request: Request, response: Response):
    user = db.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")

    # Migrate current guest session files if any into user account
    current_session = get_current_session(request)
    if current_session.get("is_guest"):
        db.migrate_guest_files(current_session["user_id"], user["id"])
        db.delete_session(current_session["token"])
    if req.guest_token:
        guest_sess = db.get_session(req.guest_token)
        if guest_sess and guest_sess.get("is_guest"):
            db.migrate_guest_files(guest_sess["user_id"], user["id"])
            db.delete_session(req.guest_token)

    token = db.create_session(user["id"], user["username"], is_guest=False)
    set_session_cookie(response, token)
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "is_guest": False,
        }
    }


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    token = _extract_token(request)
    if token:
        sess = db.get_session(token)
        if sess and sess.get("is_guest"):
            db.cleanup_guest_session_and_files(sess["user_id"], token=token)
        else:
            db.delete_session(token)

    new_token, guest_info = db.create_guest_session()
    set_session_cookie(response, new_token)
    return {
        "ok": True,
        "token": new_token,
        "user": guest_info,
    }



# ---------------- Synthesis Endpoints ----------------

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
            "tags": v.get("tags", [v.get("tone", "Natural")]),
            "description": v.get("description", "Natural sounding speech synthesis voice."),
            "model": v["piper"],
            "sample_url": f"/api/voices/{name}/sample",
        })
    return res


@app.get("/api/effects")
def effects():
    descriptions = {
        "none": "Direct AI voice persona formant & timbre match",
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
def text_to_speech(req: TTSRequest, request: Request, response: Response):
    session = get_current_session(request)
    if session.get("is_new"):
        set_session_cookie(response, session["token"])

    pause_sec = req.pause_duration if req.pause_duration is not None else RUNTIME_SETTINGS.get("pause_duration", 0.6)
    try:
        result = service.synthesize(req.text, req.voice, req.speed, req.format, pause_seconds=pause_sec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except AudioError as e:
        raise HTTPException(503, str(e))

    rec = _record_output(result, req.text, "tts", req.voice, user_id=session["user_id"])
    return _audio_response(result, f"{req.voice}-voice", file_id=rec["id"], token=session["token"])


_sample_cache: dict[str, service.AudioResult] = {}


@app.get("/api/voices/{name}/sample")
def voice_sample(name: str):
    if name not in VOICES:
        raise HTTPException(404, "Unknown voice")
    if name not in _sample_cache:
        try:
            if name == "Adam":
                sample_text = "Hey everyone! Let me show you how to use the text-to-speech feature on Instagram Reels. Thanks for watching!"
            else:
                sample_text = f"Hi, I'm {name}. Welcome to AI Voice Studio. This is how I sound."
            _sample_cache[name] = service.synthesize(
                sample_text,
                name, 1.0, "mp3"
            )
        except AudioError as e:
            raise HTTPException(503, str(e))
    return _audio_response(_sample_cache[name], f"{name}-sample")


@app.post("/api/voice-convert")
async def voice_convert(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    effect: str = Form("robot"),
    format: str = Form("mp3"),
    target_voice: str = Form("Aria"),
    similarity: float = Form(0.85),
    stability: float = Form(0.70),
    clarity: float = Form(0.80),
):
    session = get_current_session(request)
    if session.get("is_new"):
        set_session_cookie(response, session["token"])

    ext = Path(file.filename or "").suffix.lower()
    if ext and ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'.")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 10MB.")
    if not data:
        raise HTTPException(400, "Empty file.")
    try:
        result = service.convert_voice(
            data,
            file.filename or "recording.webm",
            effect=effect,
            fmt=format,
            target_voice=target_voice,
            similarity=similarity,
            stability=stability,
            clarity=clarity,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except AudioError as e:
        raise HTTPException(422, f"Could not process that audio: {e}")

    title = file.filename or f"Voice conversion ({target_voice})"
    label = target_voice if effect == "none" else f"{target_voice} ({effect.replace('_', ' ').title()})"
    rec = _record_output(result, title, "vts", label, user_id=session["user_id"])
    return _audio_response(result, "converted-voice", file_id=rec["id"], token=session["token"])


# ---------------- Private User Files Management ----------------

@app.get("/api/files")
def list_files(request: Request, response: Response):
    session = get_current_session(request)
    if session.get("is_new"):
        set_session_cookie(response, session["token"])
    return db.list_user_files(session["user_id"])


@app.get("/api/files/{file_id}/audio")
def get_file_audio(file_id: str, request: Request):
    session = get_current_session(request)
    match = db.get_file_record(file_id, user_id=session["user_id"])
    if not match:
        raise HTTPException(404, "File not found or private")
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
def download_file(file_id: str, request: Request):
    session = get_current_session(request)
    match = db.get_file_record(file_id, user_id=session["user_id"])
    if not match:
        raise HTTPException(404, "File not found or private")
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
def delete_file(file_id: str, request: Request):
    session = get_current_session(request)
    filename = db.delete_user_file(file_id, session["user_id"])
    if not filename:
        raise HTTPException(404, "File not found or private")
    path = OUTPUTS_DIR / filename
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    return {"ok": True, "deleted": file_id}


@app.post("/api/files/clear")
def clear_files(request: Request):
    session = get_current_session(request)
    filenames = db.clear_all_user_files(session["user_id"])
    for fname in filenames:
        path = OUTPUTS_DIR / fname
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    return {"ok": True}


# ---------------- Settings API ----------------

@app.get("/api/settings")
def get_settings(request: Request):
    session = get_current_session(request)
    try:
        active_engine = pick_engine()
    except AudioError as e:
        active_engine = f"error: {e}"

    voices_info = []
    seen_models = set()
    for k, v in VOICES.items():
        if v["piper"] in seen_models and k not in ("Aria", "Ethan", "Nova", "Adam"):
            continue
        seen_models.add(v["piper"])
        onnx_file = VOICES_DIR / f"{v['piper']}.onnx"
        voices_info.append({
            "name": k,
            "piper_model": v["piper"],
            "installed": onnx_file.exists(),
            "size_mb": round(onnx_file.stat().st_size / (1024 * 1024), 1) if onnx_file.exists() else 0,
        })

    records = db.list_user_files(session["user_id"])
    total_bytes = sum(r.get("size", 0) for r in records)

    return {
        "engine": RUNTIME_SETTINGS["engine"],
        "active_engine": active_engine,
        "available_engines": ["auto", "chatterbox", "kokoro", "piper", "say", "dummy"],
        "default_voice": RUNTIME_SETTINGS["default_voice"],
        "default_speed": RUNTIME_SETTINGS["default_speed"],
        "default_format": RUNTIME_SETTINGS["default_format"],
        "pause_duration": RUNTIME_SETTINGS["pause_duration"],
        "default_similarity": RUNTIME_SETTINGS["default_similarity"],
        "output_quality": RUNTIME_SETTINGS["output_quality"],
        "auto_play": RUNTIME_SETTINGS["auto_play"],
        "auto_download": RUNTIME_SETTINGS["auto_download"],
        "show_tips": RUNTIME_SETTINGS["show_tips"],
        "ffmpeg": bool(get_ffmpeg_bin()),
        "installed_voices": voices_info,
        "files_count": len(records),
        "files_size_bytes": total_bytes,
        "user": {
            "id": session["user_id"],
            "username": session["username"],
            "is_guest": session["is_guest"],
        }
    }


@app.post("/api/settings")
def update_settings(update: SettingsUpdate):
    if update.engine is not None:
        RUNTIME_SETTINGS["engine"] = update.engine
        if update.engine == "auto":
            os.environ.pop("TTS_ENGINE", None)
        else:
            os.environ["TTS_ENGINE"] = update.engine
        _sample_cache.clear()
        clear_runtime_caches(evict_models=True)

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
    if update.default_similarity is not None:
        if 0.0 <= update.default_similarity <= 1.0:
            RUNTIME_SETTINGS["default_similarity"] = update.default_similarity
    if update.output_quality is not None:
        RUNTIME_SETTINGS["output_quality"] = update.output_quality
    if update.auto_play is not None:
        RUNTIME_SETTINGS["auto_play"] = update.auto_play
    if update.auto_download is not None:
        RUNTIME_SETTINGS["auto_download"] = update.auto_download
    if update.show_tips is not None:
        RUNTIME_SETTINGS["show_tips"] = update.show_tips

    return {"ok": True, "settings": RUNTIME_SETTINGS}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
