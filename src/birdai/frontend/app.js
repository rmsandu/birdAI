// BirdAI Live Field ID Controller (Stitch UI + Multimodal API + Sightings Radar)
let currentRecord = null;
let currentImageFile = null;
let currentAudioFile = null;
let currentUser = null;
let currentMode = "hybrid";
let chatHistory = [];

document.addEventListener("DOMContentLoaded", () => {
  setupDialogLightDismissFallback();
  setupEventListeners();
  checkAuthStatus();
  syncContextChips();
});

// Fallback for browsers without native <dialog closedby="any"> support (e.g. Safari)
function setupDialogLightDismissFallback() {
  if (!("closedBy" in HTMLDialogElement.prototype)) {
    const outside = (e, dialog) => {
      const r = dialog.getBoundingClientRect();
      return (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      );
    };
    for (const dialog of document.querySelectorAll('dialog[closedby="any"]')) {
      let pressedOutside = false;
      dialog.addEventListener("pointerdown", (e) => {
        pressedOutside = outside(e, dialog);
      });
      dialog.addEventListener("pointerup", (e) => {
        if (pressedOutside && outside(e, dialog)) dialog.close();
      });
    }
  }
}

function getAuthToken() {
  return localStorage.getItem("birdai_token");
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem("birdai_token", token);
  } else {
    localStorage.removeItem("birdai_token");
  }
}

function getAuthHeaders(extraHeaders = {}) {
  const token = getAuthToken();
  if (token) {
    return { ...extraHeaders, Authorization: `Bearer ${token}` };
  }
  return extraHeaders;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function checkAuthStatus() {
  const token = getAuthToken();
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const userBadge = document.getElementById("user-profile-badge");
  const emailDisplay = document.getElementById("user-email-display");
  const initialsEl = document.getElementById("user-avatar-initials");

  if (!token) {
    currentUser = null;
    if (btnOpenAuth) btnOpenAuth.style.display = "inline-flex";
    if (userBadge) userBadge.style.display = "none";
    return;
  }

  try {
    const res = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      currentUser = await res.json();
      if (btnOpenAuth) btnOpenAuth.style.display = "none";
      if (userBadge) userBadge.style.display = "flex";
      if (emailDisplay) emailDisplay.textContent = currentUser.email;
      if (initialsEl) {
        const label = currentUser.full_name || currentUser.email || "U";
        initialsEl.textContent = label.trim().charAt(0).toUpperCase();
      }
    } else {
      setAuthToken(null);
      currentUser = null;
      if (btnOpenAuth) btnOpenAuth.style.display = "inline-flex";
      if (userBadge) userBadge.style.display = "none";
    }
  } catch (err) {
    currentUser = null;
    if (btnOpenAuth) btnOpenAuth.style.display = "inline-flex";
    if (userBadge) userBadge.style.display = "none";
  }
}

function setupEventListeners() {
  // Auth modal & forms
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const authModalClose = document.getElementById("auth-modal-close");
  const btnLogout = document.getElementById("btn-logout");
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  const formLogin = document.getElementById("form-login");
  const formRegister = document.getElementById("form-register");

  if (btnOpenAuth) btnOpenAuth.addEventListener("click", () => openAuthModal());
  if (authModalClose) authModalClose.addEventListener("click", closeAuthModal);
  if (btnLogout) btnLogout.addEventListener("click", handleLogout);

  if (tabLogin && tabRegister) {
    tabLogin.addEventListener("click", () => {
      tabLogin.classList.add("active");
      tabLogin.setAttribute("aria-selected", "true");
      tabRegister.classList.remove("active");
      tabRegister.setAttribute("aria-selected", "false");
      formLogin.style.display = "block";
      formRegister.style.display = "none";
      hideAuthErrors();
    });

    tabRegister.addEventListener("click", () => {
      tabRegister.classList.add("active");
      tabRegister.setAttribute("aria-selected", "true");
      tabLogin.classList.remove("active");
      tabLogin.setAttribute("aria-selected", "false");
      formRegister.style.display = "block";
      formLogin.style.display = "none";
      hideAuthErrors();
    });
  }

  if (formLogin) formLogin.addEventListener("submit", handleLoginSubmit);
  if (formRegister) formRegister.addEventListener("submit", handleRegisterSubmit);

  // Bottom Navigation & Quick Actions
  document.querySelectorAll(".bottom-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  const btnQuickSearch = document.getElementById("btn-quick-search");
  if (btnQuickSearch) btnQuickSearch.addEventListener("click", () => switchView("sightings"));

  const btnOpenResults = document.getElementById("btn-open-results");
  if (btnOpenResults) btnOpenResults.addEventListener("click", () => switchView("results"));

  const btnGoIdentify = document.getElementById("btn-go-identify");
  if (btnGoIdentify) btnGoIdentify.addEventListener("click", () => switchView("new"));

  const btnRefreshJournal = document.getElementById("btn-refresh-journal");
  if (btnRefreshJournal) btnRefreshJournal.addEventListener("click", loadJournal);

  // Capture Mode Switcher
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchCaptureMode(btn.dataset.mode));
  });

  // Viewfinder Zoom Controls
  document.querySelectorAll(".zoom-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".zoom-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const scale = parseFloat(btn.dataset.zoom || "1");
      const img = document.getElementById("image-preview");
      if (img) img.style.transform = `scale(${scale})`;
    });
  });

  // Field Context Drawer Toggle
  const toggleContext = (forceOpen = null) => {
    const drawer = document.getElementById("field-context-drawer");
    const btn = document.getElementById("btn-toggle-context");
    if (!drawer || !btn) return;
    const shouldOpen = forceOpen !== null ? forceOpen : drawer.hidden;
    drawer.hidden = !shouldOpen;
    btn.setAttribute("aria-expanded", String(shouldOpen));
    if (shouldOpen) {
      drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  const btnToggleContext = document.getElementById("btn-toggle-context");
  if (btnToggleContext) btnToggleContext.addEventListener("click", () => toggleContext());

  const headerLocBtn = document.getElementById("header-location-btn");
  if (headerLocBtn) headerLocBtn.addEventListener("click", () => {
    switchView("new");
    toggleContext(true);
  });

  ["chip-gps", "chip-time", "chip-context"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleContext(true);
      });
    }
  });

  // Live sync of context inputs to HUD chips
  ["location-text", "latitude", "longitude", "observation-date", "observation-time"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", syncContextChips);
  });

  // File Inputs & Dropzone
  const dropzone = document.getElementById("dropzone");
  const imageInput = document.getElementById("image-file-input");
  const audioInput = document.getElementById("audio-file-input");
  const btnImportPhoto = document.getElementById("btn-import-photo");
  const btnImportAudio = document.getElementById("btn-import-audio");

  if (btnImportPhoto && imageInput) {
    btnImportPhoto.addEventListener("click", () => imageInput.click());
  }
  if (btnImportAudio && audioInput) {
    btnImportAudio.addEventListener("click", () => audioInput.click());
  }

  if (dropzone) {
    dropzone.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      if (currentMode === "acoustic" && audioInput) {
        audioInput.click();
      } else if (imageInput) {
        imageInput.click();
      }
    });
    dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (currentMode === "acoustic" && audioInput) audioInput.click();
        else if (imageInput) imageInput.click();
      }
    });
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) {
        Array.from(e.dataTransfer.files).forEach(handleFileSelection);
      }
    });
  }

  if (imageInput) {
    imageInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) handleFileSelection(e.target.files[0]);
    });
  }

  if (audioInput) {
    audioInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) handleFileSelection(e.target.files[0]);
    });
  }

  const btnAudioPlay = document.getElementById("btn-audio-play");
  const audioEl = document.getElementById("audio-preview");
  if (btnAudioPlay && audioEl) {
    btnAudioPlay.addEventListener("click", (e) => {
      e.stopPropagation();
      if (audioEl.paused) {
        audioEl.play();
      } else {
        audioEl.pause();
      }
    });
    audioEl.addEventListener("play", () => {
      const bars = document.getElementById("spectrogram-bars");
      if (bars) bars.classList.add("active");
      btnAudioPlay.innerHTML = '<span class="material-symbols-outlined icon-xs">pause</span><span>Pause</span>';
    });
    audioEl.addEventListener("pause", () => {
      const bars = document.getElementById("spectrogram-bars");
      if (bars) bars.classList.remove("active");
      btnAudioPlay.innerHTML = '<span class="material-symbols-outlined icon-xs">play_arrow</span><span>Play</span>';
    });
  }

  const btnClearAudio = document.getElementById("btn-clear-audio");
  if (btnClearAudio) {
    btnClearAudio.addEventListener("click", () => {
      currentAudioFile = null;
      const container = document.getElementById("audio-preview-container");
      const audioPreview = document.getElementById("audio-preview");
      if (audioPreview) {
        audioPreview.pause();
        audioPreview.removeAttribute("src");
      }
      if (container) container.style.display = "none";
      const status = document.getElementById("audio-hud-status");
      const playBtn = document.getElementById("btn-audio-play");
      const score = document.getElementById("audio-hud-score");
      const importBtn = document.getElementById("btn-import-audio");
      if (status) status.textContent = "No audio clip attached";
      if (playBtn) playBtn.style.display = "none";
      if (score) score.textContent = "Ready";
      if (importBtn) importBtn.classList.remove("has-file");
      updateShutterState();
    });
  }

  // Geolocation
  const geoBtn = document.getElementById("btn-geolocation");
  if (geoBtn) geoBtn.addEventListener("click", requestBrowserLocation);

  // Main Shutter / Analyze Button
  const analyzeBtn = document.getElementById("btn-analyze");
  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", () => {
      if (!currentImageFile && !currentAudioFile) {
        if (currentMode === "acoustic" && audioInput) audioInput.click();
        else if (imageInput) imageInput.click();
        return;
      }
      submitObservation();
    });
  }

  // Correction Modal
  const modalClose = document.getElementById("modal-close");
  const btnSaveCorrection = document.getElementById("btn-save-correction");
  if (modalClose) modalClose.addEventListener("click", closeModal);
  if (btnSaveCorrection) btnSaveCorrection.addEventListener("click", submitCorrection);

  // Sightings Radar Chat
  const chatForm = document.getElementById("chat-form");
  if (chatForm) chatForm.addEventListener("submit", handleChatSubmit);
  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const input = document.getElementById("chat-input");
      if (input) {
        input.value = chip.dataset.query || chip.textContent;
        chatForm.requestSubmit();
      }
    });
  });
}

function switchCaptureMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });

  const reticle = document.getElementById("optical-reticle");
  const acousticHud = document.getElementById("acoustic-hud");
  const meterLabel = document.getElementById("hud-meter-label");
  const modeBadge = document.getElementById("banner-mode-badge");

  if (mode === "hybrid") {
    if (reticle) reticle.style.opacity = "1";
    if (acousticHud) acousticHud.style.display = "block";
    if (meterLabel) meterLabel.textContent = "Dual • Ready";
    if (modeBadge) modeBadge.textContent = "Dual-Modal";
  } else if (mode === "optic") {
    if (reticle) reticle.style.opacity = "1";
    if (acousticHud) acousticHud.style.display = "none";
    if (meterLabel) meterLabel.textContent = "Visual • EXIF";
    if (modeBadge) modeBadge.textContent = "Visual Only";
  } else {
    if (reticle) reticle.style.opacity = "0.25";
    if (acousticHud) acousticHud.style.display = "block";
    if (meterLabel) meterLabel.textContent = "Acoustic • 48kHz";
    if (modeBadge) modeBadge.textContent = "Bioacoustic";
  }
}

function syncContextChips() {
  const loc = document.getElementById("location-text")?.value.trim();
  const lat = document.getElementById("latitude")?.value.trim();
  const lng = document.getElementById("longitude")?.value.trim();
  const dateVal = document.getElementById("observation-date")?.value.trim();
  const timeVal = document.getElementById("observation-time")?.value.trim();

  const headerLoc = document.getElementById("header-location-text");
  const chipGps = document.getElementById("chip-gps-text");
  const chipTime = document.getElementById("chip-time-text");
  const chipContext = document.getElementById("chip-context-text");

  if (headerLoc) {
    headerLoc.textContent = loc || (lat && lng ? `${lat}, ${lng}` : "Set field location or GPS");
  }
  if (chipGps) {
    chipGps.textContent = lat && lng ? `${Number(lat).toFixed(4)}°, ${Number(lng).toFixed(4)}°` : "GPS Auto";
  }
  if (chipTime) {
    chipTime.textContent = dateVal || timeVal ? [dateVal, timeVal].filter(Boolean).join(" • ") : "EXIF Time";
  }
  if (chipContext) {
    chipContext.textContent = loc ? loc.split(",")[0] : "Field Context";
  }
}

function updateShutterState() {
  const caption = document.getElementById("shutter-caption");
  const icon = document.getElementById("shutter-icon");
  const ready = Boolean(currentImageFile || currentAudioFile);
  if (caption) caption.textContent = ready ? "Identify Now" : "Capture / Pick";
  if (icon) icon.textContent = ready ? "auto_awesome" : "lens";
}

function openAuthModal(noticeMessage = null) {
  const modal = document.getElementById("auth-modal");
  hideAuthErrors();
  if (noticeMessage) {
    const errEl = document.getElementById("login-error");
    if (errEl) {
      errEl.textContent = noticeMessage;
      errEl.style.display = "block";
    }
  }
  if (modal && !modal.open) modal.showModal();
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal && modal.open) modal.close();
  hideAuthErrors();
}

function hideAuthErrors() {
  const loginErr = document.getElementById("login-error");
  const regErr = document.getElementById("register-error");
  if (loginErr) loginErr.style.display = "none";
  if (regErr) regErr.style.display = "none";
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");

  const formData = new FormData();
  formData.append("username", email);
  formData.append("password", password);

  try {
    const res = await fetch("/api/auth/token", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "Invalid email or password.");
    }

    const data = await res.json();
    setAuthToken(data.access_token);
    await checkAuthStatus();
    closeAuthModal();

    const journalView = document.getElementById("journal-view");
    if (journalView && journalView.classList.contains("active")) {
      loadJournal();
    }
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = err.message;
      errorEl.style.display = "block";
    }
  }
}

async function handleRegisterSubmit(e) {
  e.preventDefault();
  const fullName = document.getElementById("register-name").value.trim();
  const email = document.getElementById("register-email").value.trim();
  const password = document.getElementById("register-password").value;
  const errorEl = document.getElementById("register-error");

  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: email,
        password: password,
        full_name: fullName || null,
      }),
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "Registration failed.");
    }

    const loginData = new FormData();
    loginData.append("username", email);
    loginData.append("password", password);

    const loginRes = await fetch("/api/auth/token", {
      method: "POST",
      body: loginData,
    });

    if (loginRes.ok) {
      const tokenPayload = await loginRes.json();
      setAuthToken(tokenPayload.access_token);
      await checkAuthStatus();
      closeAuthModal();
    }
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = err.message;
      errorEl.style.display = "block";
    }
  }
}

function handleLogout() {
  setAuthToken(null);
  currentUser = null;
  checkAuthStatus();
  const journalView = document.getElementById("journal-view");
  if (journalView && journalView.classList.contains("active")) {
    loadJournal();
  }
}

function handleFileSelection(file) {
  if (file.type.startsWith("image/") || /\.(jpe?g|png|heic|webp)$/i.test(file.name)) {
    currentImageFile = file;
    const objectUrl = URL.createObjectURL(file);
    const imgPreview = document.getElementById("image-preview");
    const container = document.getElementById("image-preview-container");
    const emptyEl = document.getElementById("viewfinder-empty");
    const matchThumb = document.getElementById("match-thumb");
    const lockText = document.getElementById("reticle-lock-text");
    const photoBtn = document.getElementById("btn-import-photo");

    if (imgPreview && container) {
      imgPreview.src = objectUrl;
      container.style.display = "block";
    }
    if (emptyEl) emptyEl.style.display = "none";
    if (matchThumb) matchThumb.src = objectUrl;
    if (lockText) lockText.textContent = `Lock: ${file.name}`;
    if (photoBtn) photoBtn.classList.add("has-file");

    extractPhotoMetadata(file);
    updateShutterState();
  } else if (file.type.startsWith("audio/") || /\.(wav|mp3|flac|ogg|m4a)$/i.test(file.name)) {
    currentAudioFile = file;
    const objectUrl = URL.createObjectURL(file);
    const audPreview = document.getElementById("audio-preview");
    const container = document.getElementById("audio-preview-container");
    const filenameLabel = document.getElementById("audio-filename-label");
    const hudStatus = document.getElementById("audio-hud-status");
    const playBtn = document.getElementById("btn-audio-play");
    const hudScore = document.getElementById("audio-hud-score");
    const audioBtn = document.getElementById("btn-import-audio");

    if (audPreview && container) {
      audPreview.src = objectUrl;
      container.style.display = "flex";
    }
    if (filenameLabel) filenameLabel.textContent = file.name;
    if (hudStatus) hudStatus.textContent = file.name;
    if (playBtn) playBtn.style.display = "inline-flex";
    if (hudScore) hudScore.textContent = "Loaded";
    if (audioBtn) audioBtn.classList.add("has-file");
    updateShutterState();
  }
}

async function extractPhotoMetadata(file) {
  const statusEl = document.getElementById("location-status");
  const bannerEl = document.getElementById("banner-status-text");
  if (statusEl) statusEl.textContent = "Scanning photo for EXIF GPS metadata…";
  if (bannerEl) bannerEl.textContent = "Scanning photo EXIF metadata…";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/extract-metadata", {
      method: "POST",
      body: formData,
    });
    if (res.ok) {
      const data = await res.json();
      if (data.observation_date) {
        document.getElementById("observation-date").value = data.observation_date;
      }
      if (data.observation_time) {
        document.getElementById("observation-time").value = data.observation_time;
      }
      if (data.has_gps) {
        if (data.location_text) {
          document.getElementById("location-text").value = data.location_text;
        }
        if (data.latitude != null) {
          document.getElementById("latitude").value = data.latitude;
        }
        if (data.longitude != null) {
          document.getElementById("longitude").value = data.longitude;
        }
        const msg = data.status || "✓ GPS coordinates extracted from photo metadata.";
        if (statusEl) statusEl.textContent = msg;
        if (bannerEl) bannerEl.textContent = msg;
      } else {
        const msg = data.status || "No GPS metadata found in photo.";
        if (statusEl) statusEl.textContent = msg;
        if (bannerEl) bannerEl.textContent = msg;
      }
      syncContextChips();
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "Photo metadata scan skipped.";
    if (bannerEl) bannerEl.textContent = "Multimodal Perception Ready • Gemini + Local Classifier";
  }
}

function requestBrowserLocation() {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }
  const statusEl = document.getElementById("location-status");
  const bannerEl = document.getElementById("banner-status-text");
  if (statusEl) statusEl.textContent = "Requesting GPS coordinates…";
  if (bannerEl) bannerEl.textContent = "Acquiring GPS coordinates…";

  navigator.geolocation.getCurrentPosition(
    (position) => {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      document.getElementById("latitude").value = lat.toFixed(5);
      document.getElementById("longitude").value = lng.toFixed(5);
      const msg = `GPS locked: ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      if (statusEl) statusEl.textContent = msg;
      if (bannerEl) bannerEl.textContent = msg;
      syncContextChips();
    },
    (err) => {
      if (statusEl) statusEl.textContent = `GPS error: ${err.message}`;
    }
  );
}

async function submitObservation() {
  if (!currentUser) {
    openAuthModal("Please sign in or create an account to save and analyze observations.");
    return;
  }

  if (!currentImageFile && !currentAudioFile) {
    alert("Please upload at least one bird photo or audio recording.");
    return;
  }

  const analyzeBtn = document.getElementById("btn-analyze");
  const resultsContainer = document.getElementById("results-container");
  const loadingContainer = document.getElementById("loading-container");
  const placeholder = document.getElementById("initial-placeholder");
  const trackingLabel = document.getElementById("hud-tracking-label");
  const bannerEl = document.getElementById("banner-status-text");
  const bars = document.getElementById("spectrogram-bars");

  if (analyzeBtn) analyzeBtn.disabled = true;
  if (resultsContainer) resultsContainer.style.display = "none";
  if (placeholder) placeholder.style.display = "none";
  if (loadingContainer) loadingContainer.style.display = "flex";
  if (trackingLabel) trackingLabel.textContent = "Analyzing…";
  if (bannerEl) bannerEl.textContent = "Running multimodal identification & checklist check…";
  if (bars) bars.classList.add("active");

  const formData = new FormData();
  if (currentImageFile) formData.append("image", currentImageFile);
  if (currentAudioFile) formData.append("audio", currentAudioFile);

  const locVal = document.getElementById("location-text").value.trim();
  if (locVal) formData.append("location_text", locVal);
  const latVal = document.getElementById("latitude").value;
  const lngVal = document.getElementById("longitude").value;
  if (latVal) formData.append("latitude", latVal);
  if (lngVal) formData.append("longitude", lngVal);

  const dateVal = document.getElementById("observation-date").value;
  const timeVal = document.getElementById("observation-time").value;
  if (dateVal) formData.append("observation_date", dateVal);
  if (timeVal) formData.append("observation_time", timeVal);

  const merlinSpecies = document.getElementById("merlin-species").value;
  const merlinNotes = document.getElementById("merlin-notes").value;
  if (merlinSpecies) formData.append("merlin_species", merlinSpecies);
  if (merlinNotes) formData.append("merlin_notes", merlinNotes);

  try {
    const res = await fetch("/api/observations", {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      openAuthModal("Session expired. Please sign in again.");
      return;
    }

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to analyze observation.");
    }

    currentRecord = await res.json();
    updateMatchDrawer(currentRecord);
    renderResults(currentRecord);
    if (bannerEl) bannerEl.textContent = "Identification complete • Tap Results for full evidence";
  } catch (err) {
    alert(`Analysis error: ${err.message}`);
    if (bannerEl) bannerEl.textContent = `Analysis error: ${err.message}`;
  } finally {
    if (analyzeBtn) analyzeBtn.disabled = false;
    if (loadingContainer) loadingContainer.style.display = "none";
    if (trackingLabel) trackingLabel.textContent = "AI Live Tracking";
    if (bars) bars.classList.remove("active");
  }
}

function updateMatchDrawer(record) {
  const commonEl = document.getElementById("match-common-name");
  const sciEl = document.getElementById("match-scientific-name");
  const pillEl = document.getElementById("match-confidence-pill");
  const checkEl = document.getElementById("match-check-badge");
  const plausEl = document.getElementById("match-plausibility-text");
  const lockText = document.getElementById("reticle-lock-text");
  const audioScore = document.getElementById("audio-hud-score");

  if (!record || !record.candidates || record.candidates.length === 0) {
    if (commonEl) commonEl.textContent = "No Confident Match";
    if (sciEl) sciEl.textContent = record?.suggested_next_action || "Try a clearer photo or audio clip";
    if (pillEl) pillEl.style.display = "none";
    if (checkEl) checkEl.style.display = "none";
    return;
  }

  const top = record.candidates[0];
  if (commonEl) commonEl.textContent = top.common_name;
  if (sciEl) sciEl.textContent = top.scientific_name || "Species candidate";
  if (pillEl) {
    pillEl.textContent = `${top.confidence_probability}% Match`;
    pillEl.style.display = "inline-flex";
  }
  if (checkEl) checkEl.style.display = "flex";
  if (lockText) lockText.textContent = `Lock: ${top.common_name}`;
  if (audioScore) audioScore.textContent = `Match: ${top.confidence_probability}%`;
  if (plausEl) {
    plausEl.textContent =
      top.contextual_evidence?.summary ||
      top.contextual_evidence?.plausibility_reason ||
      top.reason ||
      "Tap arrow for full multimodal breakdown";
  }
}

function renderResults(record) {
  const container = document.getElementById("results-container");
  const placeholder = document.getElementById("initial-placeholder");
  if (!container) return;

  const candidatesList = document.getElementById("candidates-list");
  candidatesList.innerHTML = "";
  if (placeholder) placeholder.style.display = "none";

  if (!record.candidates || record.candidates.length === 0) {
    candidatesList.innerHTML = `
      <div class="surface-card state-box">
        <p class="state-title">No species candidates resolved</p>
        <p class="state-sub">${escapeHtml(record.suggested_next_action || "Try another photo or clearer audio.")}</p>
      </div>
    `;
    container.style.display = "block";
    return;
  }

  record.candidates.forEach((cand, idx) => {
    const isTop = idx === 0;
    const card = document.createElement("div");
    card.className = `candidate-card ${isTop ? "top-rank" : ""}`;

    const conf = cand.confidence_probability;
    const confClass = conf >= 75 ? "high" : conf >= 40 ? "medium" : "low";

    const visualText = cand.visual_evidence
      ? `${cand.visual_evidence.reason || "Features evaluated from image."} (Model: ${cand.visual_evidence.model_name})`
      : "No visual evidence uploaded for this modality.";

    const audioText = cand.audio_evidence
      ? `${cand.audio_evidence.reason || "Call analyzed."} ${
          cand.audio_evidence.duration_seconds ? `· ${cand.audio_evidence.duration_seconds}s` : ""
        } ${
          cand.audio_evidence.merlin_suggestion
            ? `· Merlin: ${cand.audio_evidence.merlin_suggestion.species_name}`
            : ""
        }`
      : "No audio recording uploaded for this modality.";

    const contextText = cand.contextual_evidence
      ? `${cand.contextual_evidence.summary || cand.contextual_evidence.plausibility_reason} (Source: ${cand.contextual_evidence.source})`
      : cand.evidence
      ? cand.evidence.summary
      : "Contextual evidence unverified.";

    const verifiedMarkup = record.user_correction
      ? `<span class="verified-badge"><span class="material-symbols-outlined icon-xs">verified</span> Verified: ${escapeHtml(record.user_correction.confirmed_species)}</span>`
      : '<span style="font-size: 12px; color: var(--on-surface-variant);">Unverified</span>';

    card.innerHTML = `
      <div class="candidate-header">
        <div>
          <div class="species-name">${escapeHtml(cand.common_name)}</div>
          <div class="species-scientific">${escapeHtml(cand.scientific_name || "")}</div>
        </div>
        <div class="confidence-chip ${confClass}">
          <span>${conf}%</span>
          <span class="uncalibrated-note">Uncalibrated</span>
        </div>
      </div>
      <div class="candidate-reason">${escapeHtml(cand.reason || "Diagnostic features match observation.")}</div>

      <div class="evidence-section">
        <div class="evidence-tabs">
          <button type="button" class="tab-btn active" onclick="switchEvidenceTab(this, 'visual-${idx}')">Visual</button>
          <button type="button" class="tab-btn" onclick="switchEvidenceTab(this, 'audio-${idx}')">Audio</button>
          <button type="button" class="tab-btn" onclick="switchEvidenceTab(this, 'context-${idx}')">Context</button>
        </div>
        <div id="visual-${idx}" class="evidence-body">${escapeHtml(visualText)}</div>
        <div id="audio-${idx}" class="evidence-body" style="display: none;">${escapeHtml(audioText)}</div>
        <div id="context-${idx}" class="evidence-body" style="display: none;">${escapeHtml(contextText)}</div>
      </div>

      <div class="verify-footer">
        <div id="verify-status-${idx}">${verifiedMarkup}</div>
        <button type="button" class="btn-secondary" data-common="${escapeHtml(cand.common_name)}" data-sci="${escapeHtml(cand.scientific_name || "")}">
          Confirm / Correct
        </button>
      </div>
    `;

    const verifyBtn = card.querySelector(".verify-footer .btn-secondary");
    if (verifyBtn) {
      verifyBtn.addEventListener("click", () => {
        openCorrectionModal(cand.common_name, cand.scientific_name || "");
      });
    }

    candidatesList.appendChild(card);
  });

  container.style.display = "block";
}

window.switchEvidenceTab = function (btn, targetId) {
  const parent = btn.closest(".evidence-section");
  parent.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  parent.querySelectorAll(".evidence-body").forEach((el) => (el.style.display = "none"));
  btn.classList.add("active");
  const target = document.getElementById(targetId);
  if (target) target.style.display = "block";
};

window.openCorrectionModal = function (defaultSpecies, defaultSci) {
  const modal = document.getElementById("correction-modal");
  const input = document.getElementById("correct-species-input");
  const sciInput = document.getElementById("correct-sci-input");
  if (input) input.value = defaultSpecies;
  if (sciInput) sciInput.value = defaultSci;
  if (modal && !modal.open) modal.showModal();
};

function closeModal() {
  const modal = document.getElementById("correction-modal");
  if (modal && modal.open) modal.close();
}

async function submitCorrection() {
  if (!currentRecord) return;
  const species = document.getElementById("correct-species-input").value.trim();
  const sci = document.getElementById("correct-sci-input").value.trim();
  const notes = document.getElementById("correct-notes-input").value.trim();

  if (!species) {
    alert("Please enter the confirmed species name.");
    return;
  }

  try {
    const res = await fetch(`/api/observations/${currentRecord.id}/correct`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        confirmed_species: species,
        scientific_name: sci || null,
        is_correct_prediction: true,
        correction_notes: notes || null,
      }),
    });

    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      openAuthModal("Session expired. Please sign in again.");
      return;
    }

    if (!res.ok) throw new Error("Failed to save correction.");
    currentRecord = await res.json();
    closeModal();
    updateMatchDrawer(currentRecord);
    renderResults(currentRecord);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function handleChatSubmit(e) {
  e.preventDefault();
  if (!currentUser) {
    openAuthModal("Please sign in to query live eBird & ornitho.ch sightings.");
    return;
  }

  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-chat-send");
  const feed = document.getElementById("chat-messages");
  const message = input.value.trim();
  if (!message) return;

  appendChatBubble("user", message);
  input.value = "";
  sendBtn.disabled = true;

  const latVal = document.getElementById("latitude")?.value;
  const lngVal = document.getElementById("longitude")?.value;

  const payload = {
    message,
    conversation_history: chatHistory,
    user_latitude: latVal ? parseFloat(latVal) : null,
    user_longitude: lngVal ? parseFloat(lngVal) : null,
    preferred_radius_km: 15,
  };

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });

    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      openAuthModal("Session expired. Please sign in again.");
      return;
    }

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Sightings query failed.");
    }

    const data = await res.json();
    chatHistory.push({ role: "user", content: message });
    chatHistory.push({ role: "assistant", content: data.reply });
    appendChatBubble("assistant", data.reply, data.sightings || []);
  } catch (err) {
    appendChatBubble("assistant", `Could not fetch sightings: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    if (feed) feed.scrollTop = feed.scrollHeight;
  }
}

function appendChatBubble(role, text, sightings = []) {
  const feed = document.getElementById("chat-messages");
  if (!feed) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;

  let html = `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>`;
  if (Array.isArray(sightings) && sightings.length > 0) {
    const rows = sightings.slice(0, 6).map((s) => {
      const name = s.common_name || s.species || "Unknown";
      const loc = s.location_name || s.location || "";
      const when = s.observation_date || s.date || "";
      const src = s.source || "";
      return `
        <div class="sighting-row">
          <div>
            <div class="sighting-species">${escapeHtml(name)}</div>
            <div class="sighting-meta">${escapeHtml([loc, when].filter(Boolean).join(" · "))}</div>
          </div>
          <span class="source-pill">${escapeHtml(src || "Sighting")}</span>
        </div>
      `;
    }).join("");
    html += `<div class="sightings-mini-list">${rows}</div>`;
  }

  bubble.innerHTML = html;
  feed.appendChild(bubble);
  feed.scrollTop = feed.scrollHeight;
}

function switchView(view) {
  const viewMap = {
    new: "capture-view",
    results: "results-view",
    sightings: "sightings-view",
    journal: "journal-view",
  };

  Object.entries(viewMap).forEach(([key, id]) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("active", key === view);
  });

  document.querySelectorAll(".bottom-nav-item").forEach((btn) => {
    const isActive = btn.dataset.view === view;
    btn.classList.toggle("active", isActive);
    if (isActive) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  });

  if (view === "journal") {
    loadJournal();
  }
}

async function loadJournal() {
  const listEl = document.getElementById("journal-list");
  if (!listEl) return;

  if (!currentUser) {
    listEl.innerHTML = `
      <div class="surface-card state-box">
        <div class="state-icon-circle">
          <span class="material-symbols-outlined">lock</span>
        </div>
        <p class="state-title">Private Life List</p>
        <p class="state-sub">Sign in to view your saved field observations and verified ground truth.</p>
        <button type="button" class="btn-primary-inline" onclick="openAuthModal()">Sign In</button>
      </div>
    `;
    return;
  }

  listEl.innerHTML = '<div class="surface-card state-box"><div class="spinner"></div></div>';

  try {
    const res = await fetch("/api/observations?limit=50", {
      headers: getAuthHeaders(),
    });

    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      loadJournal();
      return;
    }

    const records = await res.json();

    if (!records || records.length === 0) {
      listEl.innerHTML = `
        <div class="surface-card state-box">
          <div class="state-icon-circle">
            <span class="material-symbols-outlined">menu_book</span>
          </div>
          <p class="state-title">No Saved Observations Yet</p>
          <p class="state-sub">Captured observations will appear here once analyzed.</p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";
    records.forEach((r) => {
      const item = document.createElement("div");
      item.className = "journal-item";
      const topName = r.candidates && r.candidates.length > 0 ? r.candidates[0].common_name : "Unknown bird";
      const verified = r.user_correction
        ? `<span class="verified-badge"><span class="material-symbols-outlined icon-xs">verified</span> ${escapeHtml(r.user_correction.confirmed_species)}</span>`
        : '<span style="color: var(--on-surface-variant); font-size: 11px; font-weight: 600;">Unverified</span>';

      const loc = r.observation_context?.location_text || "Unknown location";
      const obsDate = r.observation_context?.observation_date || "";

      item.innerHTML = `
        <div style="min-width: 0;">
          <div style="font-weight: 700; font-size: 15px; color: var(--primary);">${escapeHtml(topName)}</div>
          <div style="font-size: 12px; color: var(--on-surface-variant); margin-top: 2px;">
            ${escapeHtml([loc, obsDate].filter(Boolean).join(" · "))}
          </div>
        </div>
        <div style="flex-shrink: 0;">${verified}</div>
      `;
      item.addEventListener("click", () => {
        currentRecord = r;
        updateMatchDrawer(r);
        renderResults(r);
        switchView("results");
      });
      listEl.appendChild(item);
    });
  } catch (err) {
    listEl.innerHTML = `<div class="surface-card state-box"><p class="state-sub">Error loading journal: ${escapeHtml(err.message)}</p></div>`;
  }
}
