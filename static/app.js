/* ============================================================
   AI Voice Studio – Frontend Application Logic (v4.0)
   ============================================================ */

(() => {
  "use strict";

  /* ---------- DOM SELECTORS & STATE ---------- */
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  // Runtime Preferences (synced with /api/settings)
  let appPrefs = {
    auto_play: true,
    auto_download: false,
    show_tips: false,
    output_quality: "high",
    default_similarity: 0.85,
  };

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
    const vtsInBtn = $("#vtsPreviewInputPlayBtn");
    if (vtsInBtn) vtsInBtn.textContent = "▶";
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
    toast.style.borderColor = isError ? "var(--red)" : "var(--lime)";
    toast.classList.add("show");
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toast.classList.remove("show");
    }, 3200);
  }

  const fmtTime = (s) => {
    if (!isFinite(s) || isNaN(s) || s < 0) return "0:00";
    const m = Math.floor(s / 60);
    const sec = String(Math.floor(s % 60)).padStart(2, "0");
    return `${m}:${sec}`;
  };

  function fmtRelativeTime(timestampSec, fallbackStr) {
    if (!timestampSec) return fallbackStr || "";
    const diff = Math.max(0, Math.floor(Date.now() / 1000) - Number(timestampSec));
    if (diff < 60) return "Just now";
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
    return fallbackStr || `${Math.floor(diff / 86400)}d ago`;
  }

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
      topbarAuth.innerHTML = `
        <div class="auth-badge user">
          <span class="auth-avatar-circle">👤</span>
          <span>${escapeHtml(currentUser.username)}</span>
          <span class="auth-dot" title="Authenticated"></span>
        </div>
        <button class="auth-logout-btn" id="authLogoutBtn" type="button">LOG OUT</button>
      `;
      const logoutBtn = $("#authLogoutBtn");
      if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);

      if (filesPrivacyTitle) filesPrivacyTitle.textContent = `PRIVATE VAULT (${currentUser.username.toUpperCase()})`;
      if (filesPrivacySub) filesPrivacySub.textContent = "Your audio files are permanently saved to your account and only visible to you.";
      if (filesGuestPrompt) filesGuestPrompt.style.display = "none";
    } else {
      topbarAuth.innerHTML = `
        <div class="auth-badge">
          <span class="auth-avatar-circle">👤</span>
          <span>GUEST</span>
        </div>
        <button class="auth-open-btn" id="openAuthModalBtn" type="button">
          <span>SIGN IN</span>
          <span class="arrow-lime">→</span>
        </button>
      `;
      const openBtn = $("#openAuthModalBtn");
      if (openBtn) openBtn.addEventListener("click", () => openAuthModal("login"));

      if (filesPrivacyTitle) filesPrivacyTitle.textContent = "PRIVATE SESSION VAULT";
      if (filesPrivacySub) filesPrivacySub.textContent = "Your files are private to this browser session and auto-delete when you close the website.";
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
      submitBtn.textContent = "SIGNING IN…";

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
        submitBtn.textContent = "SIGN IN →";
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
      submitBtn.textContent = "CREATING ACCOUNT…";

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
        submitBtn.textContent = "CREATE FREE ACCOUNT →";
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
      showToast("Logged out. Switched to temporary guest session.");
      loadFiles();
    } catch (err) {
      showToast("Error during logout", true);
    }
  }

  /* ---------- 1. NAVIGATION & TAB SWITCHING ---------- */
  const tabTitles = {
    tts: {
      title: "TEXT TO SPEECH",
      desc: "Convert your text into ultra-realistic AI voice.",
    },
    vts: {
      title: "VOICE TO SPEECH",
      desc: "Upload or record your voice and convert it using AI voices.",
    },
    files: {
      title: "MY FILES",
      desc: "Manage, preview, and download your generated audio files.",
    },
    voices: {
      title: "VOICE LIBRARY",
      desc: "Explore our collection of AI voices.",
    },
    settings: {
      title: "SETTINGS",
      desc: "Configure your preferences and defaults.",
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

    if (tabKey === "files") loadFiles();
    if (tabKey === "voices") loadVoiceLibrary();
    if (tabKey === "settings") loadSettings();
  }

  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  const brandLogo = $("#sidebarBrandLogo");
  if (brandLogo) {
    brandLogo.addEventListener("click", () => switchTab("tts"));
  }

  const initialHash = window.location.hash.replace("#", "");
  if (tabTitles[initialHash]) {
    switchTab(initialHash);
  }

  /* ---------- 2. THEME SWITCHER ---------- */
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("voice_studio_theme", theme);
    const isDark = theme === "dark";
    $("#themeLabel").innerHTML = isDark ? "☾ &nbsp; DARK MODE" : "☼ &nbsp; LIGHT MODE";
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
  let vtsTargetVoice = "Aria";

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

  function playVoiceSample(vName, triggerEl) {
    if (!vName) return;
    stopAllAudio();
    if (triggerEl) triggerEl.textContent = "⏳";
    const sampleAudio = new Audio(`/api/voices/${encodeURIComponent(vName)}/sample`);
    registerAudio(sampleAudio);
    sampleAudio
      .play()
      .then(() => {
        if (triggerEl) triggerEl.textContent = "⏸";
      })
      .catch(() => {
        if (triggerEl) triggerEl.textContent = "▶";
      });
    sampleAudio.addEventListener("ended", () => {
      if (triggerEl) triggerEl.textContent = "▶";
    });
    sampleAudio.addEventListener("pause", () => {
      if (triggerEl) triggerEl.textContent = "▶";
    });
  }

  function selectStudioVoice(voiceName, genderLabel = "AI") {
    selectedVoice = voiceName;
    let found = false;
    $$("#ttsVoiceList .voice[data-voice]").forEach((btn) => {
      const isMatch = btn.dataset.voice === voiceName;
      btn.classList.toggle("selected", isMatch);
      if (isMatch) found = true;
    });
    if (!found) {
      const firstCard = $("#ttsVoiceList .voice[data-voice]");
      if (firstCard) {
        firstCard.dataset.voice = voiceName;
        firstCard.querySelector(".voice-name").textContent = voiceName.toUpperCase();
        firstCard.querySelector(".voice-type").textContent = genderLabel;
        const playSpan = firstCard.querySelector(".voice-play");
        if (playSpan) playSpan.dataset.sample = voiceName;
        $$("#ttsVoiceList .voice[data-voice]").forEach((v) => v.classList.remove("selected"));
        firstCard.classList.add("selected");
      }
    }
  }

  // Voice selector in TTS
  function setupTtsVoiceButtons() {
    $$("#ttsVoiceList .voice[data-voice]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        if (e.target.closest(".voice-play")) return;
        $$("#ttsVoiceList .voice[data-voice]").forEach((v) => v.classList.remove("selected"));
        btn.classList.add("selected");
        selectedVoice = btn.dataset.voice;
      });
    });
  }
  setupTtsVoiceButtons();

  // Voice selector in VTS
  function setupVtsVoiceButtons() {
    $$("#vtsVoiceList .voice[data-vts-voice]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        if (e.target.closest(".voice-play")) return;
        $$("#vtsVoiceList .voice[data-vts-voice]").forEach((v) => v.classList.remove("selected"));
        btn.classList.add("selected");
        vtsTargetVoice = btn.dataset.vtsVoice;
      });
    });
  }
  setupVtsVoiceButtons();

  $("#exploreMoreVoicesBtn").addEventListener("click", () => switchTab("voices"));
  const vtsExploreBtn = $("#vtsExploreVoicesBtn");
  if (vtsExploreBtn) vtsExploreBtn.addEventListener("click", () => switchTab("voices"));

  // Voice card sample buttons
  $$(".voice-play").forEach((playIcon) => {
    playIcon.addEventListener("click", (e) => {
      e.stopPropagation();
      playVoiceSample(playIcon.dataset.sample, playIcon);
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
    outputStatusPill.textContent = "GENERATED ✓";
    stopAllAudio();
    if (appPrefs.auto_play !== false) {
      ttsPlayer.play().catch(() => {});
    }
    if (appPrefs.auto_download) {
      downloadBlobOrUrl(ttsAudioUrl, `ai-voice-${selectedVoice.toLowerCase()}.${ttsCurrentExt}`);
    }
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
          <span></span><span></span><span></span><span></span><span></span>
        </div>
        <span>${escapeHtml(labelText || "GENERATING VOICE…")}</span>
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

    const origHTML = setButtonLoading(generateBtn, "GENERATING VOICE…");
    outputStatusPill.textContent = "GENERATING…";

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
      outputStatusPill.textContent = "ERROR";
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
    quickRecLabel.textContent = `READY: ${label || file.name}`;
    quickConvertBtn.disabled = false;
    if (quickDownloadRecBtn) quickDownloadRecBtn.style.display = "block";
  }

  if (quickBrowseBtn) {
    quickBrowseBtn.addEventListener("click", () => quickFileInput.click());
  }

  quickDropZone.addEventListener("click", (e) => {
    if (e.target.closest("button") || e.target.closest("select")) return;
    if (quickRecordBtn) {
      quickRecordBtn.click();
    } else {
      quickFileInput.click();
    }
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
      quickDropZone.style.borderColor = "var(--ink)";
      quickDropZone.style.background = "var(--green-light)";
    });
  });
  ["dragleave", "drop"].forEach((eName) => {
    quickDropZone.addEventListener(eName, (e) => {
      e.preventDefault();
      quickDropZone.style.borderColor = "";
      quickDropZone.style.background = "";
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
          quickRecordBtn.textContent = "🎙 LIVE RECORD";
          quickRecordBtn.style.background = "";
          quickRecordBtn.style.color = "";

          const mime = quickMediaRecorder.mimeType || "audio/webm";
          const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
          const blob = new Blob(quickRecChunks, { type: mime });
          const recFile = new File([blob], `quick_recording.${ext}`, { type: mime });
          setQuickAudioFile(recFile, "MIC RECORDING");
          showToast("Microphone audio captured!");
        };

        quickMediaRecorder.start();
        quickRecordBtn.textContent = "⏹ STOP REC";
        quickRecordBtn.style.background = "var(--red)";
        quickRecordBtn.style.color = "#fff";
        quickRecLabel.textContent = "RECORDING IN PROGRESS…";
      } catch (err) {
        showToast("Microphone permission was denied. Check browser permissions.", true);
      }
    });
  }

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
    const origHTML = setButtonLoading(quickConvertBtn, "…");
    try {
      const form = new FormData();
      form.append("file", quickPendingFile);
      form.append("effect", quickEffectSelect.value);
      form.append("format", formatSelect.value);
      form.append("target_voice", selectedVoice);

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
      showToast("Voice converted!");
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
  const vtsLoadedFileName = $("#vtsLoadedFileName");
  const vtsLoadedDuration = $("#vtsLoadedDuration");
  const vtsPreviewInputPlayBtn = $("#vtsPreviewInputPlayBtn");
  const vtsClearInputBtn = $("#vtsClearInputBtn");
  const vtsEffectSelect = $("#vtsEffectSelect");
  const vtsFormatSelect = $("#vtsFormatSelect");
  const vtsConvertBtn = $("#vtsConvertBtn");

  const vtsSimilarityRange = $("#vtsSimilarityRange");
  const vtsSimilarityVal = $("#vtsSimilarityVal");
  const vtsStabilityRange = $("#vtsStabilityRange");
  const vtsStabilityVal = $("#vtsStabilityVal");
  const vtsClarityRange = $("#vtsClarityRange");
  const vtsClarityVal = $("#vtsClarityVal");

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

  if (vtsSimilarityRange) {
    vtsSimilarityRange.addEventListener("input", (e) => {
      vtsSimilarityVal.textContent = Number(e.target.value).toFixed(2);
    });
  }
  if (vtsStabilityRange) {
    vtsStabilityRange.addEventListener("input", (e) => {
      vtsStabilityVal.textContent = Number(e.target.value).toFixed(2);
    });
  }
  if (vtsClarityRange) {
    vtsClarityRange.addEventListener("input", (e) => {
      vtsClarityVal.textContent = Number(e.target.value).toFixed(2);
    });
  }

  // Sync Effect Dropdown & Effect Grid Cards
  function setVtsEffect(effectName) {
    vtsSelectedEffect = effectName;
    if (vtsEffectSelect) vtsEffectSelect.value = effectName;
    $$("#vtsEffectsGrid .effect-item").forEach((c) => {
      c.classList.toggle("selected", c.dataset.effect === effectName);
    });
  }

  if (vtsEffectSelect) {
    vtsEffectSelect.addEventListener("change", (e) => {
      setVtsEffect(e.target.value);
    });
  }

  $$("#vtsEffectsGrid .effect-item").forEach((card) => {
    card.addEventListener("click", () => {
      setVtsEffect(card.dataset.effect);
    });
  });

  // Set input audio file
  function setVtsInputFile(file, label) {
    vtsPendingFile = file;
    vtsInputBadge.textContent = "AUDIO LOADED ✓";
    vtsUploadText.textContent = `File: ${file.name || label}`;
    if (vtsLoadedFileName) vtsLoadedFileName.textContent = file.name || label || "my_voice_sample.wav";
    vtsConvertBtn.disabled = false;

    vtsInputPreviewRow.style.display = "block";
    const objectUrl = URL.createObjectURL(file);
    vtsInputAudio.src = objectUrl;
    registerAudio(vtsInputAudio);
  }

  vtsInputAudio.addEventListener("loadedmetadata", () => {
    if (vtsLoadedDuration && isFinite(vtsInputAudio.duration)) {
      vtsLoadedDuration.textContent = fmtTime(vtsInputAudio.duration);
    }
  });

  if (vtsPreviewInputPlayBtn) {
    vtsPreviewInputPlayBtn.addEventListener("click", () => {
      if (!vtsInputAudio.src) return;
      if (vtsInputAudio.paused) {
        stopAllAudio();
        vtsInputAudio.play().catch(() => {});
        vtsPreviewInputPlayBtn.textContent = "⏸";
      } else {
        vtsInputAudio.pause();
        vtsPreviewInputPlayBtn.textContent = "▶";
      }
    });
    vtsInputAudio.addEventListener("ended", () => (vtsPreviewInputPlayBtn.textContent = "▶"));
    vtsInputAudio.addEventListener("pause", () => (vtsPreviewInputPlayBtn.textContent = "▶"));
  }

  function clearVtsInput() {
    vtsPendingFile = null;
    vtsInputBadge.textContent = "NO AUDIO LOADED";
    vtsUploadText.textContent = "or drag & drop audio file";
    vtsConvertBtn.disabled = true;
    vtsInputPreviewRow.style.display = "none";
    vtsInputAudio.src = "";
    vtsTimer.textContent = "00:00";
    vtsStatusLabel.textContent = "CLICK TO RECORD";
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
  vtsDropZone.addEventListener("click", (e) => {
    if (e.target.closest("#vtsRecordBtn")) return;
    vtsFileInput.click();
  });

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
      vtsDropZone.style.borderColor = "var(--ink)";
      vtsDropZone.style.background = "var(--green-light)";
    });
  });
  ["dragleave", "drop"].forEach((eName) => {
    vtsDropZone.addEventListener(eName, (e) => {
      e.preventDefault();
      vtsDropZone.style.borderColor = "";
      vtsDropZone.style.background = "";
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
  vtsRecordBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
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

      vtsMediaRecorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) vtsRecChunks.push(ev.data);
      };

      vtsMediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(vtsTimerInterval);
        vtsRecordBtn.classList.remove("recording");
        vtsRecordBtn.textContent = "🎙";
        vtsStatusLabel.textContent = "RECORDING SAVED ✓";

        const mime = vtsMediaRecorder.mimeType || "audio/webm";
        const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(vtsRecChunks, { type: mime });
        const recFile = new File([blob], `my_voice_sample.${ext}`, { type: mime });
        setVtsInputFile(recFile, "Microphone Recording");
        showToast("Voice recorded successfully!");
      };

      vtsMediaRecorder.start();
      vtsRecordStartTime = Date.now();
      vtsRecordBtn.classList.add("recording");
      vtsRecordBtn.textContent = "⏹";
      vtsStatusLabel.textContent = "RECORDING… CLICK TO STOP";

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
    vtsOutputStatus.textContent = "CONVERTED ✓";
    stopAllAudio();
    if (appPrefs.auto_play !== false) {
      vtsPlayer.play().catch(() => {});
    }
    if (appPrefs.auto_download) {
      downloadBlobOrUrl(vtsAudioUrl, `voice-transformed-${vtsTargetVoice.toLowerCase()}.${vtsCurrentExt}`);
    }
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
    downloadBlobOrUrl(vtsAudioUrl, `voice-transformed-${vtsTargetVoice.toLowerCase()}-${vtsSelectedEffect}.${vtsCurrentExt}`);
    showToast("Downloading audio…");
  });

  vtsGoToFilesBtn.addEventListener("click", () => switchTab("files"));

  // VTS Conversion Trigger
  vtsConvertBtn.addEventListener("click", async () => {
    if (!vtsPendingFile) {
      showToast("Please record audio or upload a file first", true);
      return;
    }

    const origHTML = setButtonLoading(vtsConvertBtn, "TRANSFORMING VOICE…");
    vtsOutputStatus.textContent = "PROCESSING…";

    try {
      const form = new FormData();
      form.append("file", vtsPendingFile);
      form.append("effect", vtsSelectedEffect);
      form.append("format", vtsFormatSelect.value);
      form.append("target_voice", vtsTargetVoice);
      if (vtsSimilarityRange) form.append("similarity", vtsSimilarityRange.value);
      if (vtsStabilityRange) form.append("stability", vtsStabilityRange.value);
      if (vtsClarityRange) form.append("clarity", vtsClarityRange.value);

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
      vtsOutputStatus.textContent = "ERROR";
    } finally {
      restoreButton(vtsConvertBtn, origHTML);
    }
  });

  /* ---------- 5. MY FILES MANAGEMENT ---------- */
  const filesListContainer = $("#filesListContainer");
  const filesSearchInput = $("#filesSearchInput");
  const clearAllFilesBtn = $("#clearAllFilesBtn");
  const filesTotalCountLabel = $("#filesTotalCountLabel");
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
      filesListContainer.innerHTML = `<div class="empty-state">Failed to load saved files: ${escapeHtml(err.message)}</div>`;
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

    if (filesTotalCountLabel) {
      filesTotalCountLabel.textContent = `${filtered.length} ${filtered.length === 1 ? "file" : "files"}`;
    }

    if (filtered.length === 0) {
      filesListContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size: 32px; margin-bottom: 10px;">📂</div>
          <h3 style="font-size: 15px; margin-bottom: 6px; text-transform: uppercase;">No audio files found</h3>
          <p style="color: var(--muted); font-size: 12px; margin-bottom: 18px;">
            ${allFiles.length === 0 ? "You haven't generated any audio files yet." : "No files match your search filter."}
          </p>
          ${allFiles.length === 0 ? '<button class="small-button" id="emptyGenerateBtn" type="button">GENERATE VOICE NOW →</button>' : ""}
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
      const typeLabel = isTts ? "TTS" : "VC";
      const downloadUrl = `/api/files/${file.id}/download${tokenQuery}`;
      const audioUrl = `/api/files/${file.id}/audio${tokenQuery}`;
      const relTime = fmtRelativeTime(file.timestamp, file.created_at);

      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <div class="file-name-cell">
          <button class="file-play-circle file-play-btn" type="button" title="Play">▶</button>
          <div class="file-title" title="${escapeHtml(file.title || file.filename)}">${escapeHtml(file.title || file.filename)}</div>
        </div>
        <div>${typeLabel}</div>
        <div>${escapeHtml(file.voice_or_effect || "Aria")}</div>
        <div>${escapeHtml((file.format || "mp3").toUpperCase())}</div>
        <div>${fmtTime(file.duration)}</div>
        <div style="color: var(--muted);">${escapeHtml(relTime)}</div>
        <div class="file-actions">
          ${file.full_text ? `<button class="file-icon-btn file-load-btn" type="button" data-text="${encodeURIComponent(file.full_text)}" title="Load text in Studio">↺</button>` : ""}
          <a href="${downloadUrl}" download="${escapeHtml(file.filename)}" class="file-icon-btn" title="Download">↓</a>
          <button class="file-icon-btn delete file-delete-btn" type="button" data-id="${escapeHtml(file.id)}" title="Delete">🗑</button>
        </div>
      `;

      // Play handler
      const playItemBtn = item.querySelector(".file-play-btn");
      playItemBtn.addEventListener("click", () => {
        stopAllAudio();
        const aud = new Audio(audioUrl);
        registerAudio(aud);
        playItemBtn.textContent = "⏸";
        aud.play().catch(() => (playItemBtn.textContent = "▶"));
        aud.addEventListener("pause", () => (playItemBtn.textContent = "▶"));
        aud.addEventListener("ended", () => (playItemBtn.textContent = "▶"));
      });

      // Load in Studio
      const loadBtn = item.querySelector(".file-load-btn");
      if (loadBtn) {
        loadBtn.addEventListener("click", () => {
          const rawText = decodeURIComponent(loadBtn.dataset.text);
          textInput.value = rawText;
          counter.textContent = `${rawText.length} / 5000`;
          if (file.voice_or_effect) {
            selectStudioVoice(file.voice_or_effect);
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
      showToast("All saved files cleared");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  /* ---------- 6. VOICE LIBRARY ---------- */
  const voicesGridContainer = $("#voicesGridContainer");
  const voicesSearchInput = $("#voicesSearchInput");
  const voicesSortSelect = $("#voicesSortSelect");
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
      voicesGridContainer.innerHTML = `<div class="empty-state">Failed to load voices: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderVoiceLibrary() {
    const query = (voicesSearchInput.value || "").toLowerCase().trim();
    let filtered = allVoices.filter((v) => {
      if (currentVoiceFilter !== "all" && v.gender !== currentVoiceFilter) return false;
      if (query) {
        const matchName = (v.name || "").toLowerCase().includes(query);
        const matchDesc = (v.description || "").toLowerCase().includes(query);
        const matchTone = (v.tone || "").toLowerCase().includes(query);
        if (!matchName && !matchDesc && !matchTone) return false;
      }
      return true;
    });

    if (voicesSortSelect && voicesSortSelect.value === "name") {
      filtered = [...filtered].sort((a, b) => a.name.localeCompare(b.name));
    }

    if (filtered.length === 0) {
      voicesGridContainer.innerHTML = `
        <div class="empty-state" style="grid-column: 1/-1;">
          <h3 style="font-size: 16px; margin-bottom: 6px;">No voices found</h3>
          <p style="color: var(--muted); font-size: 12.5px;">Try a different search or filter category.</p>
        </div>
      `;
      return;
    }

    voicesGridContainer.innerHTML = "";
    filtered.forEach((voice) => {
      const tags = Array.isArray(voice.tags) && voice.tags.length ? voice.tags : [voice.tone || "Natural"];
      const card = document.createElement("div");
      card.className = "card lib-card";
      card.style.cursor = "pointer";
      card.innerHTML = `
        <div>
          <h3>${escapeHtml(voice.name)}</h3>
          <div class="lib-gender-sub">${escapeHtml(voice.gender)}</div>
          <div class="lib-tags">
            ${tags.map((t) => `<span class="lib-tag">${escapeHtml(t)}</span>`).join("")}
          </div>
        </div>

        <div class="lib-card-bottom">
          <div class="lib-wave-preview" aria-hidden="true">
            <span style="height:6px"></span><span style="height:14px"></span><span style="height:22px"></span><span style="height:10px"></span><span style="height:18px"></span><span style="height:24px"></span><span style="height:12px"></span><span style="height:16px"></span><span style="height:8px"></span><span style="height:14px"></span><span style="height:6px"></span>
          </div>
          <button class="lib-play-circle lib-play-btn" type="button" title="Play sample">▶</button>
        </div>
      `;

      // Sample play button
      const sampleBtn = card.querySelector(".lib-play-btn");
      sampleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        playVoiceSample(voice.name, sampleBtn);
      });

      // Clicking card selects voice in Studio
      card.addEventListener("click", () => {
        selectStudioVoice(voice.name, voice.gender);
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
  if (voicesSortSelect) voicesSortSelect.addEventListener("change", renderVoiceLibrary);

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
  const settingsDefaultSimilarity = $("#settingsDefaultSimilarity");
  const settingsSimilarityVal = $("#settingsSimilarityVal");
  const settingsOutputQuality = $("#settingsOutputQuality");
  const settingsAutoPlay = $("#settingsAutoPlay");
  const settingsAutoDownload = $("#settingsAutoDownload");
  const settingsShowTips = $("#settingsShowTips");
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

  if (settingsDefaultSimilarity) {
    settingsDefaultSimilarity.addEventListener("input", (e) => {
      settingsSimilarityVal.textContent = Number(e.target.value).toFixed(2);
    });
  }

  async function loadSettings() {
    try {
      const res = await fetch("/api/settings", { headers: getAuthHeaders() });
      saveTokenFromResponse(res);
      if (!res.ok) throw new Error("Could not load settings");
      const data = await res.json();

      settingsEngineSelect.value = data.engine || "auto";
      settingsEngineStatus.textContent = `● Active: ${data.active_engine}`;
      settingsFfmpegStatus.textContent = data.ffmpeg ? "● FFmpeg Ready ✓" : "⚠️ FFmpeg Missing";

      settingsDefaultVoice.value = data.default_voice || "Aria";
      settingsDefaultFormat.value = data.default_format || "mp3";
      settingsDefaultSpeed.value = data.default_speed || 1.0;
      settingsSpeedVal.textContent = `${Number(data.default_speed || 1.0).toFixed(2).replace(/0$/, "")}x`;
      settingsPauseDuration.value = data.pause_duration || 0.6;
      settingsPauseVal.textContent = `${Number(data.pause_duration || 0.6).toFixed(1)}s`;

      if (settingsDefaultSimilarity) {
        const sim = data.default_similarity ?? 0.85;
        settingsDefaultSimilarity.value = sim;
        settingsSimilarityVal.textContent = Number(sim).toFixed(2);
      }
      if (settingsOutputQuality && data.output_quality) {
        settingsOutputQuality.value = data.output_quality;
      }
      if (settingsAutoPlay) settingsAutoPlay.checked = data.auto_play !== false;
      if (settingsAutoDownload) settingsAutoDownload.checked = Boolean(data.auto_download);
      if (settingsShowTips) settingsShowTips.checked = Boolean(data.show_tips);

      appPrefs.auto_play = data.auto_play !== false;
      appPrefs.auto_download = Boolean(data.auto_download);
      appPrefs.show_tips = Boolean(data.show_tips);
      appPrefs.output_quality = data.output_quality || "high";
      appPrefs.default_similarity = data.default_similarity ?? 0.85;

      settingsThemeSelect.value = document.documentElement.getAttribute("data-theme") || "light";
      const totalMb = (data.files_size_bytes / (1024 * 1024)).toFixed(2);
      settingsStorageText.textContent = `${data.files_count} files (${totalMb} MB) in outputs/`;

      settingsVoicesList.innerHTML = "";
      (data.installed_voices || []).forEach((v) => {
        const row = document.createElement("div");
        row.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; background: var(--paper); border: 1px solid var(--border-subtle); font-size: 11.5px;";
        row.innerHTML = `
          <div>
            <strong>${escapeHtml(v.name)}</strong> (${escapeHtml(v.piper_model)})
            <div style="font-size: 10.5px; color: var(--muted);">${v.size_mb} MB ONNX Model</div>
          </div>
          <span class="badge-status">${v.installed ? "READY ✓" : "MISSING"}</span>
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
      await fetch("/api/files/clear", { method: "POST", headers: getAuthHeaders() });
      loadSettings();
      showToast("Storage cleared");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  saveSettingsBtn.addEventListener("click", async () => {
    const origHTML = saveSettingsBtn.innerHTML;
    saveSettingsBtn.disabled = true;
    saveSettingsBtn.innerHTML = "<span>SAVING…</span>";
    try {
      const payload = {
        engine: settingsEngineSelect.value,
        default_voice: settingsDefaultVoice.value,
        default_speed: parseFloat(settingsDefaultSpeed.value),
        default_format: settingsDefaultFormat.value,
        pause_duration: parseFloat(settingsPauseDuration.value),
        default_similarity: settingsDefaultSimilarity ? parseFloat(settingsDefaultSimilarity.value) : 0.85,
        output_quality: settingsOutputQuality ? settingsOutputQuality.value : "high",
        auto_play: settingsAutoPlay ? settingsAutoPlay.checked : true,
        auto_download: settingsAutoDownload ? settingsAutoDownload.checked : false,
        show_tips: settingsShowTips ? settingsShowTips.checked : false,
      };

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error("Could not update settings");

      applyTheme(settingsThemeSelect.value);

      // Sync settings to TTS & VTS controls
      speedRange.value = payload.default_speed;
      speedVal.textContent = `${payload.default_speed}x`;
      formatSelect.value = payload.default_format;
      vtsFormatSelect.value = payload.default_format;
      pauseRange.value = payload.pause_duration;
      pauseVal.textContent = `${payload.pause_duration}s`;
      if (vtsSimilarityRange) {
        vtsSimilarityRange.value = payload.default_similarity;
        vtsSimilarityVal.textContent = Number(payload.default_similarity).toFixed(2);
      }
      selectStudioVoice(payload.default_voice);

      appPrefs.auto_play = payload.auto_play;
      appPrefs.auto_download = payload.auto_download;
      appPrefs.show_tips = payload.show_tips;

      showToast("Settings saved successfully!");
      loadSettings();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      saveSettingsBtn.disabled = false;
      saveSettingsBtn.innerHTML = origHTML;
    }
  });

  // Automatic Guest Audio Cleanup on Website Close (Prevents Storage & RAM Overload)
  let guestCleanupSent = false;
  function triggerGuestCleanupOnClose() {
    if (guestCleanupSent) return;
    if (currentUser && !currentUser.is_guest) return; // Logged-in users keep their files
    const token = getStoredToken();
    if (!token) return;
    guestCleanupSent = true;

    if (ttsAudioUrl) {
      try { URL.revokeObjectURL(ttsAudioUrl); } catch (e) {}
      ttsAudioUrl = null;
    }
    if (vtsAudioUrl) {
      try { URL.revokeObjectURL(vtsAudioUrl); } catch (e) {}
      vtsAudioUrl = null;
    }

    const cleanupUrl = `/api/guest/cleanup?token=${encodeURIComponent(token)}`;
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify({ token })], { type: "application/json" });
        navigator.sendBeacon(cleanupUrl, blob);
      } else {
        fetch(cleanupUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Session-Token": token },
          body: JSON.stringify({ token }),
          keepalive: true,
        }).catch(() => {});
      }
    } catch (e) {}
    localStorage.removeItem(TOKEN_KEY);
  }

  window.addEventListener("pagehide", triggerGuestCleanupOnClose);
  window.addEventListener("beforeunload", triggerGuestCleanupOnClose);

  // Initial auth session check and settings sync
  checkAuthSession();
  loadSettings();
})();
