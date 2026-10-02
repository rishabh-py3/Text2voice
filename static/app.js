/* ============================================================
   AI Voice Studio – Frontend Application Logic
   ============================================================ */

(() => {
  "use strict";

  /* ---------- DOM SELECTORS & STATE ---------- */
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  // Audio Playback State
  const activeAudios = new Set();
  function stopAllAudio() {
    activeAudios.forEach((a) => {
      try {
        a.pause();
      } catch (e) {}
    });
    activeAudios.clear();
    $$(".playing").forEach((el) => el.classList.remove("playing"));
    if (playBtn) playBtn.textContent = "▶";
    if (vtsPlayBtn) vtsPlayBtn.textContent = "▶";
  }

  function registerAudio(audio) {
    audio.addEventListener("play", () => {
      activeAudios.forEach((a) => {
        if (a !== audio) {
          try {
            a.pause();
          } catch (e) {}
        }
      });
      activeAudios.clear();
      activeAudios.add(audio);
    });
    audio.addEventListener("pause", () => activeAudios.delete(audio));
    audio.addEventListener("ended", () => activeAudios.delete(audio));
  }

  // Toast Notification
  const toast = $("#toast");
  const toastMsg = $("#toastMessage");
  const toastIcon = $("#toastIcon");
  let toastTimeout = null;

  function showToast(message, isError = false) {
    if (!toast) return;
    toastMsg.textContent = message;
    toastIcon.textContent = isError ? "⚠️" : "✓";
    toast.style.borderColor = isError ? "#e23b3b" : "var(--green)";
    toast.classList.add("show");
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toast.classList.remove("show");
    }, 3200);
  }

  const fmtTime = (s) => {
    if (!isFinite(s) || isNaN(s)) return "0:00";
    const m = Math.floor(s / 60);
    const sec = String(Math.floor(s % 60)).padStart(2, "0");
    return `${m}:${sec}`;
  };

  function downloadBlobOrUrl(blobOrUrl, filename) {
    if (!blobOrUrl) return;
    let url = blobOrUrl;
    let isObjectUrl = false;
    if (blobOrUrl instanceof Blob || blobOrUrl instanceof File) {
      url = URL.createObjectURL(blobOrUrl);
      isObjectUrl = true;
    }
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = url;
    a.download = filename || "audio.mp3";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      try {
        document.body.removeChild(a);
      } catch (e) {}
      if (isObjectUrl) URL.revokeObjectURL(url);
    }, 1200);
  }

  /* ---------- 0. AUTHENTICATION & PRIVATE SESSION ---------- */
  let currentUser = null;
  const TOKEN_KEY = "voice_studio_token";

  function getStoredToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setStoredToken(token) {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  function getAuthHeaders(extra = {}) {
    const headers = { ...extra };
    const token = getStoredToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
      headers["X-Session-Token"] = token;
    }
    return headers;
  }

  function saveTokenFromResponse(res) {
    if (!res || !res.headers) return;
    const token = res.headers.get("X-Session-Token");
    if (token) {
      setStoredToken(token);
    }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  const topbarAuth = $("#topbarAuth");
  const authModal = $("#authModal");
  const closeAuthModalBtn = $("#closeAuthModalBtn");
  const authTabLogin = $("#authTabLogin");
  const authTabRegister = $("#authTabRegister");
  const loginForm = $("#loginForm");
  const registerForm = $("#registerForm");
  const loginError = $("#loginError");
  const registerError = $("#registerError");
  const loginUsername = $("#loginUsername");
  const loginPassword = $("#loginPassword");
  const registerUsername = $("#registerUsername");
  const registerPassword = $("#registerPassword");
  const filesPrivacyTitle = $("#filesPrivacyTitle");
  const filesPrivacySub = $("#filesPrivacySub");
  const filesGuestPrompt = $("#filesGuestPrompt");
  const filesSignInPromptBtn = $("#filesSignInPromptBtn");

  function openAuthModal(mode = "login") {
    if (!authModal) return;
    authModal.classList.add("active");
    if (loginError) loginError.style.display = "none";
    if (registerError) registerError.style.display = "none";
    if (mode === "register" && authTabRegister) {
      authTabRegister.click();
    } else if (authTabLogin) {
      authTabLogin.click();
    }
  }

  function closeAuthModal() {
    if (authModal) authModal.classList.remove("active");
  }

  if (closeAuthModalBtn) {
    closeAuthModalBtn.addEventListener("click", closeAuthModal);
  }
  if (authModal) {
    authModal.addEventListener("click", (e) => {
      if (e.target === authModal) closeAuthModal();
    });
  }

  if (authTabLogin && authTabRegister) {
    authTabLogin.addEventListener("click", () => {
      authTabLogin.classList.add("active");
      authTabRegister.classList.remove("active");
      loginForm.style.display = "flex";
      registerForm.style.display = "none";
      loginError.style.display = "none";
      loginUsername.focus();
    });

    authTabRegister.addEventListener("click", () => {
      authTabRegister.classList.add("active");
      authTabLogin.classList.remove("active");
      registerForm.style.display = "flex";
      loginForm.style.display = "none";
      registerError.style.display = "none";
      registerUsername.focus();
    });
  }

  if (filesSignInPromptBtn) {
    filesSignInPromptBtn.addEventListener("click", () => openAuthModal("login"));
  }

  function renderAuthState() {
    if (!topbarAuth) return;
    if (currentUser && !currentUser.is_guest) {
      // Logged in user
      topbarAuth.innerHTML = `
        <div class="auth-badge user">
          <span>👤</span>
          <span>${escapeHtml(currentUser.username)}</span>
          <span class="auth-dot" title="Authenticated"></span>
        </div>
        <button class="auth-logout-btn" id="authLogoutBtn">Log Out</button>
      `;
      const logoutBtn = $("#authLogoutBtn");
      if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);

      if (filesPrivacyTitle) filesPrivacyTitle.textContent = `Private Vault (${currentUser.username})`;
      if (filesPrivacySub) filesPrivacySub.textContent = "Your audio files are permanently saved to your account and only visible to you.";
      if (filesGuestPrompt) filesGuestPrompt.style.display = "none";
    } else {
      // Guest
      topbarAuth.innerHTML = `
        <div class="auth-badge">
          <span>👤</span>
          <span>Guest</span>
        </div>
        <button class="auth-open-btn" id="openAuthModalBtn">🔑 Sign In / Register</button>
      `;
      const openBtn = $("#openAuthModalBtn");
      if (openBtn) openBtn.addEventListener("click", () => openAuthModal("login"));

      if (filesPrivacyTitle) filesPrivacyTitle.textContent = "Private Session Vault";
      if (filesPrivacySub) filesPrivacySub.textContent = "Audio files are private to your current browser session. Sign in to keep them permanently!";
      if (filesGuestPrompt) filesGuestPrompt.style.display = "block";
    }
  }

  async function checkAuthSession() {
    try {
      const res = await fetch("/api/auth/me", { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        currentUser = data.user;
        if (data.token) setStoredToken(data.token);
      }
    } catch (e) {
      console.warn("Auth check error:", e);
    }
    renderAuthState();
  }

  // Handle Login
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      loginError.style.display = "none";
      const submitBtn = $("#loginSubmitBtn");
      submitBtn.disabled = true;
      submitBtn.textContent = "Signing in…";

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: getAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            username: loginUsername.value.trim(),
            password: loginPassword.value,
            guest_token: getStoredToken(),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Login failed");

        setStoredToken(data.token);
        currentUser = data.user;
        renderAuthState();
        closeAuthModal();
        loginForm.reset();
        showToast(`Welcome back, ${currentUser.username}!`);
        loadFiles();
      } catch (err) {
        loginError.textContent = err.message;
        loginError.style.display = "block";
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Sign In";
      }
    });
  }

  // Handle Register
  if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      registerError.style.display = "none";
      const submitBtn = $("#registerSubmitBtn");
      submitBtn.disabled = true;
      submitBtn.textContent = "Creating account…";

      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: getAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            username: registerUsername.value.trim(),
            password: registerPassword.value,
            guest_token: getStoredToken(),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Registration failed");

        setStoredToken(data.token);
        currentUser = data.user;
        renderAuthState();
        closeAuthModal();
        registerForm.reset();
        showToast(`Account created! Welcome, ${currentUser.username}.`);
        loadFiles();
      } catch (err) {
        registerError.textContent = err.message;
        registerError.style.display = "block";
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Create Free Account";
      }
    });
  }

  // Handle Logout
  async function handleLogout() {
    if (!confirm("Are you sure you want to log out?")) return;
    try {
      const res = await fetch("/api/auth/logout", {
        method: "POST",
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      if (data.token) setStoredToken(data.token);
      currentUser = data.user;
      renderAuthState();
      showToast("Logged out. Switched to private guest session.");
      loadFiles();
    } catch (err) {
      showToast("Error during logout", true);
    }
  }

  /* ---------- 1. NAVIGATION & TAB SWITCHING ---------- */
  const tabTitles = {
    tts: {
      title: "Text to Speech",
      desc: "Type anything and convert it to a natural sounding AI voice.",
    },
    vts: {
      title: "Voice to Speech",
      desc: "Record or upload your audio to transform it into AI character voices and speech effects.",
    },
    files: {
      title: "My Files",
      desc: "Manage, preview, and download your generated audio files.",
    },
    voices: {
      title: "Voice Library",
      desc: "Explore natural AI voices for your text and speech projects.",
    },
    settings: {
      title: "Settings",
      desc: "Configure speech engines, audio output defaults, and application preferences.",
    },
  };

  function switchTab(tabKey) {
    if (!tabTitles[tabKey]) tabKey = "tts";

    $$(".nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tabKey);
    });

    $$(".tab-view").forEach((view) => {
      view.classList.toggle("active", view.id === `tab-${tabKey}`);
    });

    const info = tabTitles[tabKey];
    if (info) {
      $("#topbarTitle").textContent = info.title;
      $("#topbarDesc").textContent = info.desc;
    }

    window.location.hash = tabKey;

    // Trigger tab-specific refresh
    if (tabKey === "files") loadFiles();
    if (tabKey === "voices") loadVoiceLibrary();
    if (tabKey === "settings") loadSettings();
  }

  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Handle URL hash on initial load
  const initialHash = window.location.hash.replace("#", "");
  if (tabTitles[initialHash]) {
    switchTab(initialHash);
  }

  /* ---------- 2. THEME SWITCHER ---------- */
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("voice_studio_theme", theme);
    const isDark = theme === "dark";
    $("#themeLabel").innerHTML = isDark ? "☾ &nbsp; Dark Mode" : "☼ &nbsp; Light Mode";
    const themeSelect = $("#settingsThemeSelect");
    if (themeSelect) themeSelect.value = theme;
  }

  const savedTheme = localStorage.getItem("voice_studio_theme") || "light";
  applyTheme(savedTheme);

  $("#themeToggleBtn").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    applyTheme(current === "dark" ? "light" : "dark");
  });

  /* ---------- 3. TEXT TO SPEECH (TTS) ---------- */
  const textInput = $("#textInput");
  const counter = $("#counter");
  const clearBtn = $("#clearBtn");
  const insertPauseBtn = $("#insertPauseBtn");
  const generateBtn = $("#generateBtn");
  const speedRange = $("#speedRange");
  const speedVal = $("#speedVal");
  const formatSelect = $("#formatSelect");
  const pauseRange = $("#pauseRange");
  const pauseVal = $("#pauseVal");
  const advToggle = $("#advToggle");
  const advPanel = $("#advPanel");
  const advArrow = $("#advancedArrow");

  let selectedVoice = "Aria";

  // Text counter
  textInput.addEventListener("input", () => {
    counter.textContent = `${textInput.value.length} / 5000`;
  });

  // Clear text
  clearBtn.addEventListener("click", () => {
    textInput.value = "";
    counter.textContent = "0 / 5000";
    textInput.focus();
  });

  // Insert pause tag
  insertPauseBtn.addEventListener("click", () => {
    const start = textInput.selectionStart || 0;
    const end = textInput.selectionEnd || 0;
    const tag = " [pause] ";
    textInput.value = textInput.value.substring(0, start) + tag + textInput.value.substring(end);
    textInput.focus();
    textInput.selectionStart = textInput.selectionEnd = start + tag.length;
    counter.textContent = `${textInput.value.length} / 5000`;
  });

  // Insert emotion tags
  $$(".emotion-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const tag = chip.dataset.tag || "[excited]";
      const start = textInput.selectionStart || 0;
      const end = textInput.selectionEnd || 0;
      const val = textInput.value;
      const needsLeadingSpace = start > 0 && val[start - 1] !== " " && val[start - 1] !== "[";
      const insertStr = (needsLeadingSpace ? " " : "") + tag + " ";
      textInput.value = val.substring(0, start) + insertStr + val.substring(end);
      textInput.focus();
      textInput.selectionStart = textInput.selectionEnd = start + insertStr.length;
      counter.textContent = `${textInput.value.length} / 5000`;
    });
  });

  // Voice selector in TTS
  function setupTtsVoiceButtons() {
    $$("#ttsVoiceList .voice[data-voice]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        if (e.target.closest(".voice-play")) return; // handled separately
        $$("#ttsVoiceList .voice").forEach((v) => v.classList.remove("selected"));
        btn.classList.add("selected");
        selectedVoice = btn.dataset.voice;
      });
    });
  }
  setupTtsVoiceButtons();

  $("#exploreMoreVoicesBtn").addEventListener("click", () => switchTab("voices"));

  // Voice card sample buttons
  $$(".voice-play").forEach((playIcon) => {
    playIcon.addEventListener("click", (e) => {
      e.stopPropagation();
      const vName = playIcon.dataset.sample;
      if (!vName) return;
      stopAllAudio();
      playIcon.textContent = "⏳";
      const sampleAudio = new Audio(`/api/voices/${encodeURIComponent(vName)}/sample`);
      registerAudio(sampleAudio);
      sampleAudio.play()
        .then(() => {
          playIcon.textContent = "⏸";
        })
        .catch(() => {
          playIcon.textContent = "▶";
        });
      sampleAudio.addEventListener("ended", () => (playIcon.textContent = "▶"));
      sampleAudio.addEventListener("pause", () => (playIcon.textContent = "▶"));
    });
  });

  // Advanced settings sliders
  advToggle.addEventListener("click", () => {
    const isOpen = advPanel.classList.toggle("open");
    advArrow.textContent = isOpen ? "⌃" : "⌄";
  });

  speedRange.addEventListener("input", (e) => {
    speedVal.textContent = `${Number(e.target.value).toFixed(2).replace(/0$/, "")}x`;
  });

  pauseRange.addEventListener("input", (e) => {
    pauseVal.textContent = `${Number(e.target.value).toFixed(1)}s`;
  });

  // TTS Output Player
  const ttsPlayer = new Audio();
  registerAudio(ttsPlayer);
  let ttsAudioUrl = null;
  let ttsCurrentExt = "mp3";

  const waveVisual = $("#waveVisual");
  const currentTimeLabel = $("#currentTime");
  const totalDurationLabel = $("#totalDuration");
  const progressBar = $("#progressBar");
  const progressInner = $("#progressInner");
  const playBtn = $("#playBtn");
  const downloadBtn = $("#downloadBtn");
  const outputStatusPill = $("#outputStatusPill");

  function loadTtsAudio(blob, ext, duration) {
    if (ttsAudioUrl) URL.revokeObjectURL(ttsAudioUrl);
    ttsAudioUrl = URL.createObjectURL(blob);
    ttsCurrentExt = ext;
    ttsPlayer.src = ttsAudioUrl;
    currentTimeLabel.textContent = "0:00";
    totalDurationLabel.textContent = fmtTime(duration || 0);
    progressInner.style.width = "0%";
    outputStatusPill.textContent = "Generated ✓";
    stopAllAudio();
    ttsPlayer.play().catch(() => {});
  }

  ttsPlayer.addEventListener("timeupdate", () => {
    currentTimeLabel.textContent = fmtTime(ttsPlayer.currentTime);
    if (ttsPlayer.duration) {
      progressInner.style.width = `${(ttsPlayer.currentTime / ttsPlayer.duration) * 100}%`;
    }
  });

  ttsPlayer.addEventListener("loadedmetadata", () => {
    if (isFinite(ttsPlayer.duration)) {
      totalDurationLabel.textContent = fmtTime(ttsPlayer.duration);
    }
  });

  ttsPlayer.addEventListener("play", () => {
    playBtn.textContent = "⏸";
    waveVisual.classList.add("playing");
  });

  ttsPlayer.addEventListener("pause", () => {
    playBtn.textContent = "▶";
    waveVisual.classList.remove("playing");
  });

  ttsPlayer.addEventListener("ended", () => {
    playBtn.textContent = "▶";
    waveVisual.classList.remove("playing");
  });

  progressBar.addEventListener("click", (e) => {
    if (!ttsPlayer.duration) return;
    const rect = progressBar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    ttsPlayer.currentTime = ratio * ttsPlayer.duration;
  });

  playBtn.addEventListener("click", () => {
    if (!ttsAudioUrl) {
      showToast("Generate a voice first", true);
      return;
    }
    ttsPlayer.paused ? ttsPlayer.play() : ttsPlayer.pause();
  });

  downloadBtn.addEventListener("click", () => {
    if (!ttsAudioUrl) {
      showToast("Generate a voice first", true);
      return;
    }
    downloadBlobOrUrl(ttsAudioUrl, `ai-voice-${selectedVoice.toLowerCase()}.${ttsCurrentExt}`);
    showToast("Downloading audio…");
  });

  function setButtonLoading(btn, labelText) {
    if (!btn) return "";
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.classList.add("btn-loading-active");
    btn.innerHTML = `
      <div class="btn-content-overlay">
        <div class="btn-soundwave-anim">
          <span></span>
          <span></span>
          <span></span>
          <span></span>
          <span></span>
        </div>
        <span>${escapeHtml(labelText || "Generating Voice…")}</span>
      </div>
    `;
    return origHTML;
  }

  function restoreButton(btn, origHTML) {
    if (!btn) return;
    btn.disabled = false;
    btn.classList.remove("btn-loading-active");
    if (origHTML) btn.innerHTML = origHTML;
  }

  // Generate TTS Action
  generateBtn.addEventListener("click", async () => {
    const text = textInput.value.trim();
    if (!text) {
      showToast("Please enter some text to generate speech", true);
      textInput.focus();
      return;
    }

    const emotionMatch = text.match(/\[([a-zA-Z0-9_\-\s]+)\]/);
    const labelText = emotionMatch ? `Generating [${emotionMatch[1].trim()}] Voice…` : "Generating Voice…";
    const origHTML = setButtonLoading(generateBtn, labelText);
    outputStatusPill.textContent = "Generating…";

    try {
      const res = await fetch("/api/text-to-speech", {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          text,
          voice: selectedVoice,
          speed: parseFloat(speedRange.value),
          format: formatSelect.value,
          pause_duration: parseFloat(pauseRange.value),
        }),
      });
      saveTokenFromResponse(res);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Speech generation failed");
      }

      const dur = parseFloat(res.headers.get("X-Audio-Duration")) || 0;
      const blob = await res.blob();
      loadTtsAudio(blob, formatSelect.value, dur);
      showToast("Voice generated successfully!");
    } catch (err) {
      showToast(err.message, true);
      outputStatusPill.textContent = "Error";
    } finally {
      restoreButton(generateBtn, origHTML);
    }
  });

  // Quick Voice Converter in TTS Right Column
  const quickDropZone = $("#quickDropZone");
  const quickFileInput = $("#quickFileInput");
  const quickRecLabel = $("#quickRecLabel");
  const quickRecordBtn = $("#quickRecordBtn");
  const quickBrowseBtn = $("#quickBrowseBtn");
  const quickEffectSelect = $("#quickEffectSelect");
  const quickConvertBtn = $("#quickConvertBtn");
  const quickDownloadRecBtn = $("#quickDownloadRecBtn");
  let quickPendingFile = null;
  let quickMediaRecorder = null;
  let quickRecChunks = [];

  function setQuickAudioFile(file, label) {
    quickPendingFile = file;
    quickRecLabel.textContent = `Ready: ${label || file.name}`;
    quickConvertBtn.disabled = false;
    if (quickDownloadRecBtn) quickDownloadRecBtn.style.display = "block";
  }

  if (quickBrowseBtn) {
    quickBrowseBtn.addEventListener("click", () => quickFileInput.click());
  }

  quickDropZone.addEventListener("click", (e) => {
    // Avoid double trigger if clicking buttons inside card
    if (e.target.closest("button") || e.target.closest("select")) return;
    quickFileInput.click();
  });

  quickFileInput.addEventListener("change", () => {
    if (quickFileInput.files.length) {
      const f = quickFileInput.files[0];
      if (f.size > 10 * 1024 * 1024) return showToast("File exceeds 10MB limit", true);
      setQuickAudioFile(f, f.name);
    }
  });

  ["dragenter", "dragover"].forEach((eName) => {
    quickDropZone.addEventListener(eName, (e) => {
      e.preventDefault();
      quickDropZone.style.borderColor = "var(--green)";
      quickDropZone.style.background = "var(--green-light)";
    });
  });
  ["dragleave", "drop"].forEach((eName) => {
    quickDropZone.addEventListener(eName, (e) => {
      e.preventDefault();
      quickDropZone.style.borderColor = "var(--border)";
      quickDropZone.style.background = "var(--paper)";
    });
  });
  quickDropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length) {
      const f = files[0];
      if (f.size > 10 * 1024 * 1024) return showToast("File exceeds 10MB limit", true);
      setQuickAudioFile(f, f.name);
    }
  });

  // Quick microphone recording
  if (quickRecordBtn) {
    quickRecordBtn.addEventListener("click", async () => {
      if (quickMediaRecorder && quickMediaRecorder.state === "recording") {
        quickMediaRecorder.stop();
        return;
      }

      if (!navigator.mediaDevices?.getUserMedia) {
        showToast("Microphone access is not supported in this browser", true);
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        quickRecChunks = [];
        quickMediaRecorder = new MediaRecorder(stream);

        quickMediaRecorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) quickRecChunks.push(e.data);
        };

        quickMediaRecorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          quickRecordBtn.textContent = "🎙 Live Record";
          quickRecordBtn.style.background = "";
          quickRecordBtn.style.color = "";

          const mime = quickMediaRecorder.mimeType || "audio/webm";
          const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
          const blob = new Blob(quickRecChunks, { type: mime });
          const recFile = new File([blob], `quick_recording.${ext}`, { type: mime });
          setQuickAudioFile(recFile, "Microphone Recording");
          showToast("Microphone audio captured!");
        };

        quickMediaRecorder.start();
        quickRecordBtn.textContent = "⏹ Stop Rec";
        quickRecordBtn.style.background = "#fee2e2";
        quickRecordBtn.style.color = "#dc2626";
        quickRecLabel.textContent = "Recording in progress…";
      } catch (err) {
        showToast("Microphone permission was denied. Check browser permissions.", true);
      }
    });
  }

  // Quick download recorded/uploaded audio
  if (quickDownloadRecBtn) {
    quickDownloadRecBtn.addEventListener("click", () => {
      if (!quickPendingFile) return showToast("No audio file available to download", true);
      const filename = quickPendingFile.name || `recording-${Date.now()}.webm`;
      downloadBlobOrUrl(quickPendingFile, filename);
      showToast("Downloading audio file…");
    });
  }

  quickConvertBtn.addEventListener("click", async () => {
    if (!quickPendingFile) return;
    const origHTML = setButtonLoading(quickConvertBtn, "Applying Effect…");
    try {
      const form = new FormData();
      form.append("file", quickPendingFile);
      form.append("effect", quickEffectSelect.value);
      form.append("format", formatSelect.value);

      const res = await fetch("/api/voice-convert", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      saveTokenFromResponse(res);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Conversion failed");
      }
      const dur = parseFloat(res.headers.get("X-Audio-Duration")) || 0;
      const blob = await res.blob();
      loadTtsAudio(blob, formatSelect.value, dur);
      showToast("Voice effect applied!");
    } catch (err) {
      showToast(err.message, true);
    } finally {
      restoreButton(quickConvertBtn, origHTML);
    }
  });

  /* ---------- 4. DEDICATED VOICE TO SPEECH (VTS) ---------- */
  const vtsRecordBtn = $("#vtsRecordBtn");
  const vtsTimer = $("#vtsTimer");
  const vtsStatusLabel = $("#vtsStatusLabel");
  const vtsDropZone = $("#vtsDropZone");
  const vtsFileInput = $("#vtsFileInput");
  const vtsUploadText = $("#vtsUploadText");
  const vtsInputBadge = $("#vtsInputBadge");
  const vtsInputPreviewRow = $("#vtsInputPreviewRow");
  const vtsInputAudio = $("#vtsInputAudio");
  const vtsClearInputBtn = $("#vtsClearInputBtn");
  const vtsFormatSelect = $("#vtsFormatSelect");
  const vtsConvertBtn = $("#vtsConvertBtn");

  const vtsOutputStatus = $("#vtsOutputStatus");
  const vtsWaveVisual = $("#vtsWaveVisual");
  const vtsCurrentTime = $("#vtsCurrentTime");
  const vtsProgressBar = $("#vtsProgressBar");
  const vtsProgressInner = $("#vtsProgressInner");
  const vtsTotalDuration = $("#vtsTotalDuration");
  const vtsPlayBtn = $("#vtsPlayBtn");
  const vtsDownloadBtn = $("#vtsDownloadBtn");
  const vtsGoToFilesBtn = $("#vtsGoToFilesBtn");

  let vtsPendingFile = null;
  let vtsSelectedEffect = "robot";
  let vtsMediaRecorder = null;
  let vtsRecChunks = [];
  let vtsTimerInterval = null;
  let vtsRecordStartTime = 0;

  // Effect selector
  $$("#vtsEffectsGrid .effect-item").forEach((card) => {
    card.addEventListener("click", () => {
      $$("#vtsEffectsGrid .effect-item").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      vtsSelectedEffect = card.dataset.effect;
    });
  });

  // Set input audio file
  function setVtsInputFile(file, label) {
    vtsPendingFile = file;
    vtsInputBadge.textContent = "Audio Loaded ✓";
    vtsUploadText.textContent = `File: ${file.name || label}`;
    vtsConvertBtn.disabled = false;

    // Show audio preview
    vtsInputPreviewRow.style.display = "block";
    const objectUrl = URL.createObjectURL(file);
    vtsInputAudio.src = objectUrl;
    registerAudio(vtsInputAudio);
  }

  function clearVtsInput() {
    vtsPendingFile = null;
    vtsInputBadge.textContent = "No Audio Loaded";
    vtsUploadText.textContent = "Or drop audio file here to upload";
    vtsConvertBtn.disabled = true;
    vtsInputPreviewRow.style.display = "none";
    vtsInputAudio.src = "";
    vtsTimer.textContent = "00:00";
    vtsStatusLabel.textContent = "Click microphone to start recording";
  }
  vtsClearInputBtn.addEventListener("click", clearVtsInput);

  const vtsDownloadRecordingBtn = $("#vtsDownloadRecordingBtn");
  if (vtsDownloadRecordingBtn) {
    vtsDownloadRecordingBtn.addEventListener("click", () => {
      if (!vtsPendingFile) {
        showToast("No recording available to download", true);
        return;
      }
      const filename = vtsPendingFile.name || `recording-${Date.now()}.webm`;
      downloadBlobOrUrl(vtsPendingFile, filename);
      showToast("Downloading recorded audio…");
    });
  }

  // File Upload & Drag-and-Drop
  vtsDropZone.addEventListener("click", () => vtsFileInput.click());
  vtsFileInput.addEventListener("change", () => {
    if (vtsFileInput.files.length) {
      const f = vtsFileInput.files[0];
      if (f.size > 10 * 1024 * 1024) return showToast("File exceeds 10MB limit", true);
      setVtsInputFile(f, f.name);
    }
  });

  ["dragenter", "dragover"].forEach((eName) => {
    vtsDropZone.addEventListener(eName, (e) => {
      e.preventDefault();
      vtsDropZone.style.borderColor = "var(--green)";
      vtsDropZone.style.background = "var(--green-light)";
    });
  });
  ["dragleave", "drop"].forEach((eName) => {
    vtsDropZone.addEventListener(eName, (e) => {
      e.preventDefault();
      vtsDropZone.style.borderColor = "var(--border)";
      vtsDropZone.style.background = "var(--paper)";
    });
  });
  vtsDropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length) {
      const f = files[0];
      if (f.size > 10 * 1024 * 1024) return showToast("File exceeds 10MB limit", true);
      setVtsInputFile(f, f.name);
    }
  });

  // Microphone Recording
  vtsRecordBtn.addEventListener("click", async () => {
    if (vtsMediaRecorder && vtsMediaRecorder.state === "recording") {
      vtsMediaRecorder.stop();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      showToast("Microphone access is not supported in this browser", true);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      vtsRecChunks = [];
      vtsMediaRecorder = new MediaRecorder(stream);

      vtsMediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) vtsRecChunks.push(e.data);
      };

      vtsMediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(vtsTimerInterval);
        vtsRecordBtn.classList.remove("recording");
        vtsRecordBtn.textContent = "🎙";
        vtsStatusLabel.textContent = "Recording saved ✓ (Click to re-record)";

        const mime = vtsMediaRecorder.mimeType || "audio/webm";
        const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(vtsRecChunks, { type: mime });
        const recFile = new File([blob], `my_recording.${ext}`, { type: mime });
        setVtsInputFile(recFile, "Microphone Recording");
        showToast("Voice recorded successfully!");
      };

      vtsMediaRecorder.start();
      vtsRecordStartTime = Date.now();
      vtsRecordBtn.classList.add("recording");
      vtsRecordBtn.textContent = "⏹";
      vtsStatusLabel.textContent = "Recording in progress… click to stop";

      vtsTimerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - vtsRecordStartTime) / 1000);
        vtsTimer.textContent = fmtTime(elapsed);
      }, 500);
    } catch (err) {
      showToast("Microphone permission was blocked. Check browser settings or upload a file.", true);
    }
  });

  // VTS Output Player
  const vtsPlayer = new Audio();
  registerAudio(vtsPlayer);
  let vtsAudioUrl = null;
  let vtsCurrentExt = "mp3";

  function loadVtsOutputAudio(blob, ext, duration) {
    if (vtsAudioUrl) URL.revokeObjectURL(vtsAudioUrl);
    vtsAudioUrl = URL.createObjectURL(blob);
    vtsCurrentExt = ext;
    vtsPlayer.src = vtsAudioUrl;
    vtsCurrentTime.textContent = "0:00";
    vtsTotalDuration.textContent = fmtTime(duration || 0);
    vtsProgressInner.style.width = "0%";
    vtsOutputStatus.textContent = "Converted ✓";
    stopAllAudio();
    vtsPlayer.play().catch(() => {});
  }

  vtsPlayer.addEventListener("timeupdate", () => {
    vtsCurrentTime.textContent = fmtTime(vtsPlayer.currentTime);
    if (vtsPlayer.duration) {
      vtsProgressInner.style.width = `${(vtsPlayer.currentTime / vtsPlayer.duration) * 100}%`;
    }
  });

  vtsPlayer.addEventListener("loadedmetadata", () => {
    if (isFinite(vtsPlayer.duration)) {
      vtsTotalDuration.textContent = fmtTime(vtsPlayer.duration);
    }
  });

  vtsPlayer.addEventListener("play", () => {
    vtsPlayBtn.textContent = "⏸";
    vtsWaveVisual.classList.add("playing");
  });

  vtsPlayer.addEventListener("pause", () => {
    vtsPlayBtn.textContent = "▶";
    vtsWaveVisual.classList.remove("playing");
  });

  vtsPlayer.addEventListener("ended", () => {
    vtsPlayBtn.textContent = "▶";
    vtsWaveVisual.classList.remove("playing");
  });

  vtsProgressBar.addEventListener("click", (e) => {
    if (!vtsPlayer.duration) return;
    const rect = vtsProgressBar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    vtsPlayer.currentTime = ratio * vtsPlayer.duration;
  });

  vtsPlayBtn.addEventListener("click", () => {
    if (!vtsAudioUrl) {
      showToast("Convert your voice first", true);
      return;
    }
    vtsPlayer.paused ? vtsPlayer.play() : vtsPlayer.pause();
  });

  vtsDownloadBtn.addEventListener("click", () => {
    if (!vtsAudioUrl) {
      showToast("Convert your voice first", true);
      return;
    }
    downloadBlobOrUrl(vtsAudioUrl, `voice-transformed-${vtsSelectedEffect}.${vtsCurrentExt}`);
    showToast("Downloading audio…");
  });

  vtsGoToFilesBtn.addEventListener("click", () => switchTab("files"));

  // VTS Conversion Trigger
  vtsConvertBtn.addEventListener("click", async () => {
    if (!vtsPendingFile) {
      showToast("Please record audio or upload a file first", true);
      return;
    }

    const origHTML = setButtonLoading(vtsConvertBtn, "Transforming Voice…");
    vtsOutputStatus.textContent = "Processing…";

    try {
      const form = new FormData();
      form.append("file", vtsPendingFile);
      form.append("effect", vtsSelectedEffect);
      form.append("format", vtsFormatSelect.value);

      const res = await fetch("/api/voice-convert", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      saveTokenFromResponse(res);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Voice conversion failed");
      }

      const dur = parseFloat(res.headers.get("X-Audio-Duration")) || 0;
      const blob = await res.blob();
      loadVtsOutputAudio(blob, vtsFormatSelect.value, dur);
      showToast("Voice transformed successfully!");
    } catch (err) {
      showToast(err.message, true);
      vtsOutputStatus.textContent = "Error";
    } finally {
      restoreButton(vtsConvertBtn, origHTML);
    }
  });

  /* ---------- 5. MY FILES MANAGEMENT ---------- */
  const filesListContainer = $("#filesListContainer");
  const filesSearchInput = $("#filesSearchInput");
  const clearAllFilesBtn = $("#clearAllFilesBtn");
  let allFiles = [];
  let currentFileFilter = "all";

  async function loadFiles() {
    filesListContainer.innerHTML = '<div style="padding: 30px; text-align: center; color: var(--muted);">Loading files…</div>';
    try {
      const res = await fetch("/api/files", { headers: getAuthHeaders() });
      saveTokenFromResponse(res);
      if (!res.ok) throw new Error("Failed to load files");
      allFiles = await res.json();
      renderFiles();
    } catch (err) {
      filesListContainer.innerHTML = `<div class="empty-state">Failed to load saved files: ${err.message}</div>`;
    }
  }

  function renderFiles() {
    const query = (filesSearchInput.value || "").toLowerCase().trim();
    const filtered = allFiles.filter((f) => {
      if (currentFileFilter === "tts" && f.kind !== "tts") return false;
      if (currentFileFilter === "vts" && f.kind !== "vts") return false;
      if (query) {
        const matchTitle = (f.title || "").toLowerCase().includes(query);
        const matchKind = (f.voice_or_effect || "").toLowerCase().includes(query);
        if (!matchTitle && !matchKind) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      filesListContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📂</div>
          <h3 style="font-size: 18px; margin-bottom: 8px;">No audio files found</h3>
          <p style="color: var(--muted); font-size: 14px; margin-bottom: 20px;">
            ${allFiles.length === 0 ? "You haven't generated any audio files yet. Try generating speech from the Text to Speech tab!" : "No files match your search criteria."}
          </p>
          ${allFiles.length === 0 ? '<button class="small-button" id="emptyGenerateBtn" style="height: 42px; padding: 0 20px; font-weight: 600;">〽 Generate Voice Now</button>' : ""}
        </div>
      `;
      const btn = $("#emptyGenerateBtn");
      if (btn) btn.addEventListener("click", () => switchTab("tts"));
      return;
    }

    const token = getStoredToken();
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : "";

    filesListContainer.innerHTML = "";
    filtered.forEach((file) => {
      const isTts = file.kind === "tts";
      const badgeIcon = isTts ? "🔊" : "⚡";
      const sizeKb = file.size ? `${(file.size / 1024).toFixed(1)} KB` : "";
      const downloadUrl = `/api/files/${file.id}/download${tokenQuery}`;
      const audioUrl = `/api/files/${file.id}/audio${tokenQuery}`;

      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <div class="file-left">
          <div class="file-badge">${badgeIcon}</div>
          <div class="file-info">
            <div class="file-title" title="${file.title || file.filename}">${file.title || file.filename}</div>
            <div class="file-meta">
              <span><strong>${isTts ? "Voice: " + file.voice_or_effect : "Effect: " + file.voice_or_effect}</strong></span>
              <span>•</span>
              <span>${fmtTime(file.duration)}</span>
              <span>•</span>
              <span>${(file.format || "mp3").toUpperCase()}</span>
              <span>•</span>
              <span>${file.created_at || ""}</span>
              ${sizeKb ? `<span>•</span><span>${sizeKb}</span>` : ""}
            </div>
          </div>
        </div>

        <div class="file-actions">
          <button class="file-btn file-play-btn" data-audio-url="${audioUrl}">▶ Play</button>
          <a href="${downloadUrl}" download="${file.filename}" class="file-btn" style="text-decoration: none;">↓ Download</a>
          ${file.full_text ? `<button class="file-btn file-load-btn" data-text="${encodeURIComponent(file.full_text)}">Load in Studio</button>` : ""}
          <button class="file-btn delete file-delete-btn" data-id="${file.id}">🗑</button>
        </div>
      `;

      // Play handler
      const playItemBtn = item.querySelector(".file-play-btn");
      playItemBtn.addEventListener("click", () => {
        stopAllAudio();
        const aud = new Audio(audioUrl);
        registerAudio(aud);
        playItemBtn.textContent = "⏸ Pause";
        aud.play().catch(() => (playItemBtn.textContent = "▶ Play"));
        aud.addEventListener("pause", () => (playItemBtn.textContent = "▶ Play"));
        aud.addEventListener("ended", () => (playItemBtn.textContent = "▶ Play"));
      });

      // Load in Studio
      const loadBtn = item.querySelector(".file-load-btn");
      if (loadBtn) {
        loadBtn.addEventListener("click", () => {
          const rawText = decodeURIComponent(loadBtn.dataset.text);
          textInput.value = rawText;
          counter.textContent = `${rawText.length} / 5000`;
          if (file.voice_or_effect) {
            selectedVoice = file.voice_or_effect;
            $$("#ttsVoiceList .voice").forEach((v) => {
              v.classList.toggle("selected", v.dataset.voice === selectedVoice);
            });
          }
          switchTab("tts");
          showToast("Loaded text into Text to Speech studio");
        });
      }

      // Delete handler
      const delBtn = item.querySelector(".file-delete-btn");
      delBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to delete this audio file?")) return;
        try {
          const res = await fetch(`/api/files/${file.id}`, {
            method: "DELETE",
            headers: getAuthHeaders(),
          });
          if (!res.ok) throw new Error("Delete failed");
          allFiles = allFiles.filter((f) => f.id !== file.id);
          renderFiles();
          showToast("File deleted");
        } catch (err) {
          showToast(err.message, true);
        }
      });

      filesListContainer.appendChild(item);
    });
  }

  // Filter tabs in My Files
  $$("[data-file-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("[data-file-filter]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentFileFilter = btn.dataset.fileFilter;
      renderFiles();
    });
  });

  filesSearchInput.addEventListener("input", renderFiles);

  clearAllFilesBtn.addEventListener("click", async () => {
    if (!allFiles.length) return showToast("No files to clear", true);
    if (!confirm("Are you sure you want to delete ALL your saved audio files? This cannot be undone.")) return;
    try {
      const res = await fetch("/api/files/clear", {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("Failed to clear files");
      allFiles = [];
      renderFiles();
      showToast("All your saved files cleared");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  /* ---------- 6. VOICE LIBRARY ---------- */
  const voicesGridContainer = $("#voicesGridContainer");
  const voicesSearchInput = $("#voicesSearchInput");
  let allVoices = [];
  let currentVoiceFilter = "all";

  async function loadVoiceLibrary() {
    voicesGridContainer.innerHTML = '<div style="padding: 30px; text-align: center; color: var(--muted);">Loading voices…</div>';
    try {
      const res = await fetch("/api/voices");
      if (!res.ok) throw new Error("Failed to load voices");
      allVoices = await res.json();
      renderVoiceLibrary();
    } catch (err) {
      voicesGridContainer.innerHTML = `<div class="empty-state">Failed to load voices: ${err.message}</div>`;
    }
  }

  function renderVoiceLibrary() {
    const query = (voicesSearchInput.value || "").toLowerCase().trim();
    const filtered = allVoices.filter((v) => {
      if (currentVoiceFilter !== "all" && v.gender !== currentVoiceFilter) return false;
      if (query) {
        const matchName = (v.name || "").toLowerCase().includes(query);
        const matchDesc = (v.description || "").toLowerCase().includes(query);
        const matchAccent = (v.accent || "").toLowerCase().includes(query);
        if (!matchName && !matchDesc && !matchAccent) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      voicesGridContainer.innerHTML = `
        <div class="empty-state" style="grid-column: 1/-1;">
          <h3 style="font-size: 18px; margin-bottom: 8px;">No voices found</h3>
          <p style="color: var(--muted); font-size: 14px;">Try a different search or filter category.</p>
        </div>
      `;
      return;
    }

    voicesGridContainer.innerHTML = "";
    filtered.forEach((voice) => {
      const card = document.createElement("div");
      card.className = "card lib-card";
      card.innerHTML = `
        <div>
          <div class="lib-card-top">
            <div class="lib-avatar">${voice.name.charAt(0)}</div>
            <div class="lib-tags">
              <span class="lib-tag">${voice.gender}</span>
              <span class="lib-tag">${voice.accent}</span>
              <span class="lib-tag">${voice.tone}</span>
            </div>
          </div>
          <h3>${voice.name}</h3>
          <p>${voice.description}</p>
        </div>

        <div class="lib-card-actions">
          <button class="file-btn lib-play-btn" style="flex: 1;" data-voice="${voice.name}">▶ Play Sample</button>
          <button class="small-button lib-use-btn" style="flex: 1.3; font-weight: 600; border-color: var(--green); color: var(--green-dark);" data-voice="${voice.name}">Use in Studio →</button>
        </div>
      `;

      // Sample play
      const sampleBtn = card.querySelector(".lib-play-btn");
      sampleBtn.addEventListener("click", () => {
        stopAllAudio();
        sampleBtn.textContent = "⏳ Loading…";
        const sampleAud = new Audio(voice.sample_url);
        registerAudio(sampleAud);
        sampleAud.play()
          .then(() => (sampleBtn.textContent = "⏸ Pause"))
          .catch(() => (sampleBtn.textContent = "▶ Play Sample"));
        sampleAud.addEventListener("pause", () => (sampleBtn.textContent = "▶ Play Sample"));
        sampleAud.addEventListener("ended", () => (sampleBtn.textContent = "▶ Play Sample"));
      });

      // Use voice
      const useBtn = card.querySelector(".lib-use-btn");
      useBtn.addEventListener("click", () => {
        selectedVoice = voice.name;
        $$("#ttsVoiceList .voice").forEach((v) => {
          v.classList.toggle("selected", v.dataset.voice === voice.name);
        });
        switchTab("tts");
        showToast(`Selected "${voice.name}" for Text to Speech`);
      });

      voicesGridContainer.appendChild(card);
    });
  }

  $$("[data-voice-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("[data-voice-filter]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentVoiceFilter = btn.dataset.voiceFilter;
      renderVoiceLibrary();
    });
  });

  voicesSearchInput.addEventListener("input", renderVoiceLibrary);

  /* ---------- 7. SETTINGS ---------- */
  const settingsEngineSelect = $("#settingsEngineSelect");
  const settingsEngineStatus = $("#settingsEngineStatus");
  const settingsFfmpegStatus = $("#settingsFfmpegStatus");
  const settingsDefaultVoice = $("#settingsDefaultVoice");
  const settingsDefaultFormat = $("#settingsDefaultFormat");
  const settingsDefaultSpeed = $("#settingsDefaultSpeed");
  const settingsSpeedVal = $("#settingsSpeedVal");
  const settingsPauseDuration = $("#settingsPauseDuration");
  const settingsPauseVal = $("#settingsPauseVal");
  const settingsVoicesList = $("#settingsVoicesList");
  const settingsThemeSelect = $("#settingsThemeSelect");
  const settingsStorageText = $("#settingsStorageText");
  const settingsClearStorageBtn = $("#settingsClearStorageBtn");
  const saveSettingsBtn = $("#saveSettingsBtn");

  settingsDefaultSpeed.addEventListener("input", (e) => {
    settingsSpeedVal.textContent = `${Number(e.target.value).toFixed(2).replace(/0$/, "")}x`;
  });

  settingsPauseDuration.addEventListener("input", (e) => {
    settingsPauseVal.textContent = `${Number(e.target.value).toFixed(1)}s`;
  });

  async function loadSettings() {
    try {
      const res = await fetch("/api/settings", { headers: getAuthHeaders() });
      saveTokenFromResponse(res);
      if (!res.ok) throw new Error("Could not load settings");
      const data = await res.json();

      settingsEngineSelect.value = data.engine || "auto";
      settingsEngineStatus.textContent = `● Active: ${data.active_engine}`;
      settingsFfmpegStatus.textContent = data.ffmpeg ? "● Installed & Operational ✓" : "⚠️ Not Installed";
      settingsFfmpegStatus.style.background = data.ffmpeg ? "var(--green-light)" : "#fee2e2";
      settingsFfmpegStatus.style.color = data.ffmpeg ? "var(--green-dark)" : "#dc2626";

      const engineNameEl = $("#engineName");
      if (engineNameEl) engineNameEl.textContent = `${data.active_engine.toUpperCase()} AI Engine`;

      settingsDefaultVoice.value = data.default_voice || "Aria";
      settingsDefaultFormat.value = data.default_format || "mp3";
      settingsDefaultSpeed.value = data.default_speed || 1.0;
      settingsSpeedVal.textContent = `${Number(data.default_speed || 1.0).toFixed(2).replace(/0$/, "")}x`;
      settingsPauseDuration.value = data.pause_duration || 0.6;
      settingsPauseVal.textContent = `${Number(data.pause_duration || 0.6).toFixed(1)}s`;

      settingsThemeSelect.value = document.documentElement.getAttribute("data-theme") || "light";
      const totalMb = (data.files_size_bytes / (1024 * 1024)).toFixed(2);
      settingsStorageText.textContent = `${data.files_count} files (${totalMb} MB) in outputs/`;

      // Render installed neural models
      settingsVoicesList.innerHTML = "";
      (data.installed_voices || []).forEach((v) => {
        const row = document.createElement("div");
        row.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: var(--paper); border: 1px solid var(--border); border-radius: 8px; font-size: 13.5px;";
        row.innerHTML = `
          <div>
            <strong>${v.name}</strong> (${v.piper_model}${v.kokoro_voice ? ' • Kokoro: ' + v.kokoro_voice : ''})
            <div style="font-size: 11.5px; color: var(--muted);">${v.size_mb} MB Onnx Neural Model</div>
          </div>
          <span class="badge-status">${v.installed ? "Installed ✓" : "Missing ✕"}</span>
        `;
        settingsVoicesList.appendChild(row);
      });
    } catch (err) {
      showToast("Error loading settings: " + err.message, true);
    }
  }

  settingsClearStorageBtn.addEventListener("click", async () => {
    if (!confirm("Clear all output audio files from disk?")) return;
    try {
      await fetch("/api/files/clear", { method: "POST" });
      loadSettings();
      showToast("Storage cleared");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  saveSettingsBtn.addEventListener("click", async () => {
    saveSettingsBtn.disabled = true;
    saveSettingsBtn.innerHTML = "⏳ Saving…";
    try {
      const payload = {
        engine: settingsEngineSelect.value,
        default_voice: settingsDefaultVoice.value,
        default_speed: parseFloat(settingsDefaultSpeed.value),
        default_format: settingsDefaultFormat.value,
        pause_duration: parseFloat(settingsPauseDuration.value),
      };

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error("Could not update settings");

      // Apply theme change if modified in settings
      applyTheme(settingsThemeSelect.value);

      // Sync settings to TTS controls
      speedRange.value = payload.default_speed;
      speedVal.textContent = `${payload.default_speed}x`;
      formatSelect.value = payload.default_format;
      pauseRange.value = payload.pause_duration;
      pauseVal.textContent = `${payload.pause_duration}s`;
      selectedVoice = payload.default_voice;
      $$("#ttsVoiceList .voice").forEach((v) => {
        v.classList.toggle("selected", v.dataset.voice === selectedVoice);
      });

      showToast("Settings saved successfully!");
      loadSettings();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      saveSettingsBtn.disabled = false;
      saveSettingsBtn.innerHTML = "✓ Save Settings";
    }
  });

  // Initial auth session check and status check
  checkAuthSession();

  fetch("/api/health")
    .then((r) => r.json())
    .then((d) => {
      if (d.ok) {
        const engineNameEl = $("#engineName");
        if (engineNameEl) engineNameEl.textContent = `${d.engine.toUpperCase()} AI Engine`;
      }
    })
    .catch(() => {});
})();
