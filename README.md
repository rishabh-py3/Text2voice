# AI Voice Studio – backend

FastAPI backend for your `index.html`. It serves the UI and provides:

| Endpoint | What it does |
|---|---|
| `POST /api/text-to-speech` | `{text, voice, speed, format}` -> audio file. `[pause]` in the text inserts a 0.6s silence |
| `POST /api/voice-convert` | multipart `file` + `effect` (+ `format`) -> your recording with a robot / AI effect |
| `GET /api/voices/{name}/sample` | short sample for the ▶ button on each voice card |
| `GET /api/voices`, `/api/effects`, `/api/health` | lists + a quick status check |

## Setup (Mac)

```bash
brew install ffmpeg
cd voice-studio
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp /path/to/your/index.html static/index.html
# connect the UI to the backend (adds one line before </body>)
sed -i '' 's#</body>#<script src="/static/app.js"></script>\n</body>#' static/index.html
```

### Pick a TTS engine
- **Quickest on a Mac:** do nothing. With no voice files installed the backend automatically uses the built-in macOS `say` voices.
- **Better, free, works anywhere (Piper):** run `./setup_voices.sh` once. Piper is then used automatically.
- Force one with `TTS_ENGINE=piper|say|dummy` (`dummy` just plays tones, for testing the UI).

### Run
```bash
uvicorn main:app --reload
```
Open **http://localhost:8000** (not the file directly, or the API calls and the microphone won't work).
Check `http://localhost:8000/api/health` to see which engine is active.

## Files
- `main.py` – HTTP endpoints and validation (10MB upload limit, 5000 chars)
- `service.py` – the TTS and conversion logic
- `engines.py` – Piper / macOS `say` / dummy engines and the Aria-Ethan-Nova voice mapping
- `audio_utils.py` – FFmpeg helpers and the effect presets
- `static/app.js` – front-end wiring (generate, play, download, record, upload, convert, speed/format panel)

## Notes
- "Voice Cloning" in the UI currently applies **effects** (robot, digital, smooth AI, deep, high) to your recording. It does not copy anyone's voice. Real AI voice conversion (RVC, OpenVoice, or a hosted API) would be a new engine behind `/api/voice-convert`.
- No login, rate limiting or file cleanup beyond per-request temp folders yet. Add those before putting it on the internet.
