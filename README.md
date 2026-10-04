# 🎙️ Text2Voice – Studio-Grade AI Voice Platform

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Render](https://img.shields.io/badge/Render-Ready-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![Zero API Cost](https://img.shields.io/badge/API%20Cost-%240%20(100%25%20Offline)-brightgreen?style=for-the-badge)](https://github.com/rishabh-py3/Text2voice)

**An ultra-fast, 100% free, offline AI Voice Studio & Text-to-Speech platform with lifelike neural voices, zero cloud API fees, and instant audio effects.**

[Features](#-key-features) • [Quickstart](#-quickstart) • [Voice Models](#-studio-voice-lineup) • [Deployment](#-deployment-guide-render) • [API Reference](#-api-endpoints) • [Author](#-author)

</div>

---

## 🌟 Overview

**Text2Voice** is a modern, full-stack AI Voice Studio that brings studio-grade neural speech synthesis and audio transformation to your browser—completely offline. Powered by state-of-the-art open-weight models including **Kokoro-82M**, **Piper TTS**, and **Resemble AI Chatterbox**, Text2Voice generates expressive, human-like voiceovers without paying for recurring API subscriptions like ElevenLabs or OpenAI.

Designed with low-latency in-memory streaming, self-contained rootless audio processing, and aggressive memory optimization, Text2Voice effortlessly runs on local hardware or free-tier cloud containers (like Render’s 512MB RAM tier).

---

## ✨ Key Features

### 🧠 Dual / Multi-Engine Neural Architecture
* **Kokoro-82M (Studio Quality)**: High-fidelity StyleTTS 2 / ISTFTNet open-weights voice model offering natural human intonation and fluid word flow.
* **Piper TTS (Neural Fast)**: Ultra-lightweight ONNX neural engine delivering real-time synthesis (<150ms on standard CPUs) with <80MB RAM footprint.
* **Chatterbox TTS (Resemble AI - MIT)**: Integrated open-source zero-shot voice cloning model with paralinguistic support.
* **macOS Say Fallback**: Instant native system speech on macOS with zero setup required.
* **Smart Auto-Fallback**: Automatically selects the best available engine on your system with zero downtime.

### 🎭 Curated Studio Voice Personas
* **Adam** (*Male • Energetic & Friendly*): Young, upbeat, and natural social media tone tailored for Reels, YouTube Shorts, tutorials, and storytelling.
* **Aria** (*Female • Warm & Natural*): Articulate, gentle, and clear persona designed for narration, audiobooks, and explanatory videos.
* **Ethan** (*Male • Deep & Confident*): Resonant and authoritative voice tailored for podcasts, presentations, and announcements.
* **Nova** (*Neutral • Modern & Balanced*): Crisp, clean, and adaptive persona ideal for conversational dialogue and AI agents.

### ⚡ Voice Transformation & Sound FX
* Transform uploaded or recorded microphone audio into character voices:
  * 🤖 **Robot** (ring-modulated sci-fi effect)
  * 🪐 **Deep Pitch** (barytone cinematic voice)
  * 🎈 **High Pitch** (playful treble boost)
  * 🌐 **Smooth AI** (futuristic synthesized tone)
  * 💾 **Digital / Phone** (vintage band-pass communication channel)

### 🛠️ Self-Contained & Rootless Deployment
* **No `apt-get` or Root Required**: Automatically utilizes embedded, self-contained `imageio-ffmpeg` binaries. Runs on strict container environments without root permissions.
* **512MB RAM Friendly**: Engineered with strict single-model RAM retention and lazy model eviction to prevent Out-of-Memory (OOM) crashes on Render Free Tier.
* **Clean Text Normalization**: Automatically normalizes currencies (`$50` -> `50 dollars`), percentages (`25%` -> `25 percent`), acronyms, abbreviations (`Dr.` -> `Doctor`), and punctuation spacing.

---

## 🎧 Studio Voice Lineup

| Voice Name | Gender | Engine Match | Tone / Style | Best Suited For |
|---|---|---|---|---|
| **Adam** | Male | `am_adam` / `en_US-bryce-medium` | Energetic, Friendly & Expressive | Social Media Reels, Shorts, Explainer Videos |
| **Aria** | Female | `af_sarah` / `en_US-amy-medium` | Warm, Articulate & Smooth | Audiobooks, Tutorials, E-Learning |
| **Ethan** | Male | `am_michael` / `en_US-ryan-medium` | Deep, Resonant & Authoritative | Podcasts, Commercials, Presentations |
| **Nova** | Neutral | `bf_emma` / `en_US-lessac-medium` | Crisp, Balanced & Approachable | AI Assistants, Customer Support, Demos |

---

## 🚀 Quickstart

### 1. Clone the Repository
```bash
git clone https://github.com/rishabh-py3/Text2voice.git
cd Text2voice
```

### 2. Set Up Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Download Voice Models (Choose one or both)
* **Piper Fast Voices (~60MB each)**:
  ```bash
  ./setup_voices.sh
  ```
* **Kokoro Studio Voice Models (~310MB)**:
  ```bash
  ./setup_kokoro.sh
  ```
* *(Optional)* **Resemble AI Chatterbox TTS**:
  ```bash
  ./setup_chatterbox.sh
  ```

### 5. Start the Server
```bash
uvicorn main:app --reload --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser!

---

## ☁️ Deployment Guide (Render)

This repository is pre-configured for **1-click zero-config deployment on [Render](https://render.com)**.

### Deployment Steps:
1. Fork or push this repository to your GitHub account.
2. In the **Render Dashboard**, click **New +** -> **Web Service**.
3. Connect your **`Text2voice`** repository.
4. Render automatically configures using [`render.yaml`](render.yaml):
   * **Runtime**: `Python`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   * **Environment Variables**: `PYTHON_VERSION=3.11.9`
5. Click **Deploy Web Service**!

> **Note for Render Free Tier:**
> Text2Voice includes built-in memory eviction to run safely inside Render's 512MB RAM boundary. It automatically selects the optimal lightweight model to prevent memory crashes.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/text-to-speech` | Synthesizes text into high-quality audio (`{text, voice, speed, format, pause_duration}`) |
| `POST` | `/api/voice-convert` | Transforms uploaded audio with vocal effects (`file`, `effect`, `format`) |
| `GET` | `/api/voices` | Returns all available voices, metadata, and installation status |
| `GET` | `/api/voices/{name}/sample` | Streams a sample preview for any voice card |
| `GET` | `/api/settings` | Returns active engine, runtime configuration, and system telemetry |
| `POST` | `/api/settings` | Updates active engine (`auto`, `kokoro`, `piper`, `say`) or defaults |
| `GET` | `/api/files` | Lists user's generated audio files with duration and timestamp |
| `DELETE` | `/api/files/{id}` | Deletes a generated audio file |
| `GET` | `/api/health` | Returns health status and active TTS engine |

---

## 📁 Project Architecture

```plaintext
Text2voice/
├── main.py              # FastAPI application, REST endpoints, session auth, static mounting
├── service.py           # Core text humanizer, speech pipeline, and pause insertion
├── engines.py           # Multi-engine adapter (Kokoro-82M, Piper, Chatterbox, macOS Say)
├── audio_utils.py       # Rootless FFmpeg audio stream processing & vocal DSP effects
├── db.py                # SQLite database management for file history & user sessions
├── render.yaml          # Infrastructure-as-code deployment blueprint for Render
├── requirements.txt     # Python production dependencies (FastAPI, Piper, Kokoro, imageio-ffmpeg)
├── setup_voices.sh      # Automated downloader for Piper neural ONNX models
├── setup_kokoro.sh      # Automated downloader for Kokoro-82M model and voice weights
├── setup_chatterbox.sh  # Setup script for Resemble AI Chatterbox TTS
├── static/              # Modern glassmorphism frontend
│   ├── index.html       # Single-page studio interface with live visualizer
│   └── app.js           # Client-side audio recording, player, and API bindings
└── voices/              # Storage for offline neural model weights (.onnx)
```

---

## 👨‍💻 Author

**Rishabh Kumar Sah**
* GitHub: [@rishabh-py3](https://github.com/rishabh-py3)
* Repository: [rishabh-py3/Text2voice](https://github.com/rishabh-py3/Text2voice)

---

## 📄 License

This project is open-source and released under the **[MIT License](LICENSE)**.
Feel free to use, modify, and distribute for personal and commercial projects.
