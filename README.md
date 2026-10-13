# 🎙️ Text2Voice – AI Voice Studio

A web app for converting **Text to Speech (TTS)** and changing your voice (**Voice to Speech**) using free, offline AI voice models.

I built this project as a student with the help of AI tools to learn how **Python (FastAPI)**, **audio processing**, and **frontend web design** work together in a real full-stack project.

---

## 💡 About the Project

Most AI voice websites charge money or need paid API keys. I wanted to see if I could build a free version that runs on open-source voice models and has a cool custom UI.

While building this, I learned how to:
- Create backend APIs using **FastAPI**
- Connect a plain **HTML / CSS / JavaScript** frontend to a Python backend
- Use offline TTS models like **Piper TTS** and **Kokoro**
- Process and convert audio files (MP3 / WAV) using **FFmpeg**
- Handle user logins, guest sessions, and automatic file cleanup using **SQLite**

---

## ✨ What It Can Do

- **Text to Speech**: Type any text, choose from 8 different AI voices (`Aria`, `Luna`, `Zoe`, `Ethan`, `Adam`, `Noah`, `Nova`, `Echo`), change the speed, and download the audio as MP3 or WAV.
- **Voice to Speech (Voice Changer)**: Upload an audio file or record directly from your mic, pick a target voice or sound effect (`Robot`, `Deep`, `High Pitch`, `Smooth AI`, `Digital`), and adjust similarity/clarity sliders.
- **Voice Library**: Listen to a quick preview of each voice before using it.
- **My Files & Guest Privacy**:
  - Logged-in users can save and manage their generated audio files.
  - If you use the website as a **Guest**, your generated audio files are automatically deleted when you close the tab so the server doesn't run out of storage or RAM.
- **Settings**: Change default voice, audio quality, speed, and auto-play preferences.

---

## 🛠️ Tech Stack

- **Backend**: Python, FastAPI, SQLite
- **Voice & Audio**: Piper TTS, Kokoro ONNX, FFmpeg (`imageio-ffmpeg`)
- **Frontend**: HTML, CSS, Vanilla JavaScript

---

## 🚀 How to Run Locally

### 1. Clone the repository
```bash
git clone https://github.com/rishabh-py3/Text2voice.git
cd Text2voice
```

### 2. Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```

### 3. Install required packages
```bash
pip install -r requirements.txt
```

### 4. Download the voice models
```bash
./setup_voices.sh
```

### 5. Run the app
```bash
uvicorn main:app --reload --port 8000
```

Then open **http://localhost:8000** in your browser.

---

## 📂 Project Files

```text
Text2voice/
├── main.py            # Main FastAPI server and API routes
├── service.py         # Handles text-to-speech and voice changer logic
├── engines.py         # Loads the AI voice models (Piper / Kokoro)
├── audio_utils.py     # Audio effects and MP3/WAV conversion
├── db.py              # SQLite database for users and saved files
├── static/
│   ├── index.html     # Website UI
│   └── app.js         # Frontend JavaScript logic
├── voices/            # Downloaded AI voice model files
└── requirements.txt   # Python dependencies
```

---

## ☁️ Deploying on Render

This project includes a `render.yaml` file so it can be deployed on [Render](https://render.com) (Free Tier):
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## 👤 Author

**Rishabh Kumar Sah**
- GitHub: [@rishabh-py3](https://github.com/rishabh-py3)
- Project Link: [github.com/rishabh-py3/Text2voice](https://github.com/rishabh-py3/Text2voice)

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
