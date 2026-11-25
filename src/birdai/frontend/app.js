// BirdAI Stitch UI Controller (All 4 Tabs: Live Field ID, Species Confidence, Sightings & Radar, Life List)
let currentRecord = null;
let currentImageFile = null;
let currentImageUrl = null;
let currentAudioFile = null;
let currentUser = null;
let currentMode = "hybrid";
let preferredRadiusKm = 15;
let chatHistory = [];
let cachedJournalRecords = [];
let currentJournalFilter = "all";

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
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
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
  if (token) localStorage.setItem("birdai_token", token);
  else localStorage.removeItem("birdai_token");
}

function getAuthHeaders(extraHeaders = {}) {
  const token = getAuthToken();
  return token ? { ...extraHeaders, Authorization: `Bearer ${token}` } : extraHeaders;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function readErrorDetail(res, fallback) {
  try {
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await res.json();
      return data.detail || fallback;
    }
    const text = (await res.text()).trim();
    return text ? `${fallback} (${res.status}: ${text.slice(0, 120)})` : `${fallback} (HTTP ${res.status})`;
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}

async function checkAuthStatus() {
  const token = getAuthToken();
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const userBadge = document.getElementById("user-profile-badge");
  const emailDisplay = document.getElementById("user-email-display");
  const initialsEl = document.getElementById("user-avatar-initials");
  const lifelistSub = document.getElementById("lifelist-user-sub");

  if (!token) {
    currentUser = null;
    if (btnOpenAuth) btnOpenAuth.style.display = "inline-flex";
    if (userBadge) userBadge.style.display = "none";
    if (lifelistSub) lifelistSub.textContent = "Sign in to sync your personal field log";
    return;
  }

  try {
    const res = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      currentUser = await res.json();
      if (btnOpenAuth) btnOpenAuth.style.display = "none";
      if (userBadge) userBadge.style.display = "flex";
      if (emailDisplay) emailDisplay.textContent = currentUser.email;
      if (initialsEl) {
        const label = currentUser.full_name || currentUser.email || "U";
        initialsEl.textContent = label.trim().charAt(0).toUpperCase();
      }
      if (lifelistSub) {
        lifelistSub.textContent = currentUser.full_name
          ? `${currentUser.full_name} • ${currentUser.email}`
          : currentUser.email;
      }
    } else {
      setAuthToken(null);
      currentUser = null;
      if (btnOpenAuth) btnOpenAuth.style.display = "inline-flex";
      if (userBadge) userBadge.style.display = "none";
    }
  } catch {
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

  // Bottom Navigation & Cross-Tab Shortcuts
  document.querySelectorAll(".bottom-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  document.getElementById("btn-quick-search")?.addEventListener("click", () => switchView("sightings"));
  document.getElementById("btn-open-results")?.addEventListener("click", () => switchView("results"));
  document.getElementById("btn-go-identify")?.addEventListener("click", () => switchView("new"));
  document.getElementById("btn-new-sighting")?.addEventListener("click", () => switchView("new"));
  document.getElementById("btn-radar-to-acoustic")?.addEventListener("click", () => {
    switchCaptureMode("acoustic");
    switchView("new");
  });

  // Capture Mode Switcher
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchCaptureMode(btn.dataset.mode));
  });

  // Viewfinder Zoom
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
    if (shouldOpen) drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  document.getElementById("btn-toggle-context")?.addEventListener("click", () => toggleContext());
  document.getElementById("header-location-btn")?.addEventListener("click", () => {
    switchView("new");
    toggleContext(true);
  });

  ["chip-gps", "chip-time", "chip-context"].forEach((id) => {
    document.getElementById(id)?.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleContext(true);
    });
  });

  ["location-text", "latitude", "longitude", "observation-date", "observation-time"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", syncContextChips);
  });

  // File Inputs & Dropzone
  const dropzone = document.getElementById("dropzone");
  const imageInput = document.getElementById("image-file-input");
  const audioInput = document.getElementById("audio-file-input");

  document.getElementById("btn-import-photo")?.addEventListener("click", () => imageInput?.click());
  document.getElementById("btn-import-audio")?.addEventListener("click", () => audioInput?.click());

  if (dropzone) {
    dropzone.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      if (currentMode === "acoustic") audioInput?.click();
      else imageInput?.click();
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

  imageInput?.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFileSelection(e.target.files[0]);
  });
  audioInput?.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFileSelection(e.target.files[0]);
  });

  // Mini-HUD Audio Play
  const btnAudioPlay = document.getElementById("btn-audio-play");
  const audioEl = document.getElementById("audio-preview");
  if (btnAudioPlay && audioEl) {
    btnAudioPlay.addEventListener("click", (e) => {
      e.stopPropagation();
      if (audioEl.paused) audioEl.play();
      else audioEl.pause();
    });
    audioEl.addEventListener("play", () => {
      document.getElementById("spectrogram-bars")?.classList.add("active");
      btnAudioPlay.innerHTML = '<span class="material-symbols-outlined icon-xs">pause</span><span>Pause</span>';
    });
    audioEl.addEventListener("pause", () => {
      document.getElementById("spectrogram-bars")?.classList.remove("active");
      btnAudioPlay.innerHTML = '<span class="material-symbols-outlined icon-xs">play_arrow</span><span>Play</span>';
    });
  }

  document.getElementById("btn-clear-audio")?.addEventListener("click", () => {
    currentAudioFile = null;
    const container = document.getElementById("audio-preview-container");
    if (audioEl) {
      audioEl.pause();
      audioEl.removeAttribute("src");
    }
    if (container) container.style.display = "none";
    const status = document.getElementById("audio-hud-status");
    const playBtn = document.getElementById("btn-audio-play");
    const score = document.getElementById("audio-hud-score");
    if (status) status.textContent = "No audio clip attached";
    if (playBtn) playBtn.style.display = "none";
    if (score) score.textContent = "Ready";
    document.getElementById("btn-import-audio")?.classList.remove("has-file");
    updateShutterState();
  });

  document.getElementById("btn-geolocation")?.addEventListener("click", requestBrowserLocation);

  // Main Shutter / Analyze
  document.getElementById("btn-analyze")?.addEventListener("click", () => {
    if (!currentImageFile && !currentAudioFile) {
      if (currentMode === "acoustic") audioInput?.click();
      else imageInput?.click();
      return;
    }
    submitObservation();
  });

  // Correction Modal
  document.getElementById("modal-close")?.addEventListener("click", closeModal);
  document.getElementById("btn-save-correction")?.addEventListener("click", submitCorrection);

  // Sightings Radar Controls
  const chatForm = document.getElementById("chat-form");
  chatForm?.addEventListener("submit", handleChatSubmit);

  document.querySelectorAll(".radius-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".radius-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      preferredRadiusKm = parseInt(pill.dataset.radius || "15", 10);
      const badge = document.getElementById("radar-radius-badge");
      if (badge) badge.textContent = `${preferredRadiusKm} km radius`;
    });
  });

  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const input = document.getElementById("chat-input");
      if (input && chatForm) {
        input.value = chip.dataset.query || chip.textContent;
        chatForm.requestSubmit();
      }
    });
  });

  document.getElementById("btn-load-nearby")?.addEventListener("click", loadNearbySightings);

  // Life List Search, Filters & CSV Export
  document.getElementById("journal-search-input")?.addEventListener("input", renderJournalEntries);
  document.querySelectorAll(".journal-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".journal-filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentJournalFilter = btn.dataset.filter || "all";
      renderJournalEntries();
    });
  });
  document.getElementById("btn-export-csv")?.addEventListener("click", exportJournalCsv);
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
    if (meterLabel) meterLabel.textContent = "Photo • EXIF";
    if (modeBadge) modeBadge.textContent = "Photo Only";
  } else {
    if (reticle) reticle.style.opacity = "0.25";
    if (acousticHud) acousticHud.style.display = "block";
    if (meterLabel) meterLabel.textContent = "Sound • 48kHz";
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

  if (headerLoc) headerLoc.textContent = loc || (lat && lng ? `${lat}, ${lng}` : "Set field location or GPS");
  if (chipGps) chipGps.textContent = lat && lng ? `${Number(lat).toFixed(4)}°, ${Number(lng).toFixed(4)}°` : "GPS Auto";
  if (chipTime) chipTime.textContent = dateVal || timeVal ? [dateVal, timeVal].filter(Boolean).join(" • ") : "EXIF Time";
  if (chipContext) chipContext.textContent = loc ? loc.split(",")[0] : "Field Context";
}

function updateShutterState() {
  const caption = document.getElementById("shutter-caption");
  const icon = document.getElementById("shutter-icon");
  const ready = Boolean(currentImageFile || currentAudioFile);
  if (caption) caption.textContent = ready ? "Identify Now" : "Capture / Pick";
  if (icon) icon.textContent = ready ? "auto_awesome" : "lens";
}

/* ==================== Auth Handlers ==================== */
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
    const res = await fetch("/api/auth/token", { method: "POST", body: formData });
    if (!res.ok) throw new Error(await readErrorDetail(res, "Invalid email or password."));
    const data = await res.json();
    setAuthToken(data.access_token);
    await checkAuthStatus();
    closeAuthModal();
    if (document.getElementById("journal-view")?.classList.contains("active")) loadJournal();
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
      body: JSON.stringify({ email, password, full_name: fullName || null }),
    });
    if (!res.ok) throw new Error(await readErrorDetail(res, "Registration failed."));

    const loginData = new FormData();
    loginData.append("username", email);
    loginData.append("password", password);
    const loginRes = await fetch("/api/auth/token", { method: "POST", body: loginData });
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
  if (document.getElementById("journal-view")?.classList.contains("active")) loadJournal();
}

/* ==================== Media & Metadata ==================== */
function handleFileSelection(file) {
  if (file.type.startsWith("image/") || /\.(jpe?g|png|heic|webp)$/i.test(file.name)) {
    currentImageFile = file;
    currentImageUrl = URL.createObjectURL(file);
    const imgPreview = document.getElementById("image-preview");
    const container = document.getElementById("image-preview-container");
    const emptyEl = document.getElementById("viewfinder-empty");
    const matchThumb = document.getElementById("match-thumb");
    const lockText = document.getElementById("reticle-lock-text");

    if (imgPreview && container) {
      imgPreview.src = currentImageUrl;
      container.style.display = "block";
    }
    if (emptyEl) emptyEl.style.display = "none";
    if (matchThumb) matchThumb.src = currentImageUrl;
    if (lockText) lockText.textContent = `Lock: ${file.name}`;
    document.getElementById("btn-import-photo")?.classList.add("has-file");

    extractPhotoMetadata(file);
    updateShutterState();
  } else if (file.type.startsWith("audio/") || /\.(wav|mp3|flac|ogg|m4a)$/i.test(file.name)) {
    currentAudioFile = file;
    const objectUrl = URL.createObjectURL(file);
    const audPreview = document.getElementById("audio-preview");
    const container = document.getElementById("audio-preview-container");

    if (audPreview && container) {
      audPreview.src = objectUrl;
      container.style.display = "flex";
    }
    const filenameLabel = document.getElementById("audio-filename-label");
    const hudStatus = document.getElementById("audio-hud-status");
    const playBtn = document.getElementById("btn-audio-play");
    const hudScore = document.getElementById("audio-hud-score");
    if (filenameLabel) filenameLabel.textContent = file.name;
    if (hudStatus) hudStatus.textContent = file.name;
    if (playBtn) playBtn.style.display = "inline-flex";
    if (hudScore) hudScore.textContent = "Loaded";
    document.getElementById("btn-import-audio")?.classList.add("has-file");
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
    const res = await fetch("/api/extract-metadata", { method: "POST", body: formData });
    if (res.ok) {
      const data = await res.json();
      if (data.observation_date) document.getElementById("observation-date").value = data.observation_date;
      if (data.observation_time) document.getElementById("observation-time").value = data.observation_time;
      if (data.has_gps) {
        if (data.location_text) document.getElementById("location-text").value = data.location_text;
        if (data.latitude != null) document.getElementById("latitude").value = data.latitude;
        if (data.longitude != null) document.getElementById("longitude").value = data.longitude;
      }
      const msg = data.status || (data.has_gps ? "✓ GPS extracted from EXIF." : "No GPS metadata found in photo.");
      if (statusEl) statusEl.textContent = msg;
      if (bannerEl) bannerEl.textContent = msg;
      syncContextChips();
    }
  } catch {
    if (statusEl) statusEl.textContent = "Photo metadata scan skipped.";
  }
}

function requestBrowserLocation() {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }
  const statusEl = document.getElementById("location-status");
  if (statusEl) statusEl.textContent = "Requesting GPS coordinates…";

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      document.getElementById("latitude").value = pos.coords.latitude.toFixed(5);
      document.getElementById("longitude").value = pos.coords.longitude.toFixed(5);
      if (statusEl) statusEl.textContent = `GPS locked: ${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
      syncContextChips();
    },
    (err) => {
      if (statusEl) statusEl.textContent = `GPS error: ${err.message}`;
    }
  );
}

/* ==================== Observation Submission & Stitch Results View ==================== */
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
    if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to analyze observation."));

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
  if (audioScore) audioScore.textContent = `${top.confidence_probability}% Match`;
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
  const list = document.getElementById("candidates-list");
  if (!container || !list) return;

  if (placeholder) placeholder.style.display = "none";
  list.innerHTML = "";

  if (!record.candidates || record.candidates.length === 0) {
    list.innerHTML = `
      <div class="surface-card state-box">
        <p class="state-title">No species candidates resolved</p>
        <p class="state-sub">${escapeHtml(record.suggested_next_action || "Try another photo or clearer audio.")}</p>
      </div>
    `;
    container.style.display = "flex";
    return;
  }

  const top = record.candidates[0];
  const alternates = record.candidates.slice(1);
  const conf = Number(top.confidence_probability || 0);
  const circumference = 2 * Math.PI * 36;
  const dashOffset = circumference * (1 - Math.min(100, Math.max(0, conf)) / 100);
  const shortId = String(record.id || "").slice(0, 6).toUpperCase() || "OBS";
  const heroPhoto = currentImageUrl || (record.image_path ? record.image_path : null);
  const obsLoc = record.observation_context?.location_text || "Field Location";
  const obsDate = record.observation_context?.observation_date || "Today";
  const modalityLabel = (record.modality || "multimodal").toUpperCase();
  const isVerified = Boolean(record.user_correction);

  const visualText = top.visual_evidence
    ? `${top.visual_evidence.reason || "Features evaluated from image."} (${top.visual_evidence.model_name || "Vision Model"})`
    : "No visual image uploaded for this observation.";
  const visualScore = top.visual_evidence ? Math.min(99, Math.max(conf, 45)) : 0;

  const audioText = top.audio_evidence
    ? `${top.audio_evidence.reason || "Acoustic call analyzed."}${
        top.audio_evidence.duration_seconds ? ` · ${top.audio_evidence.duration_seconds}s` : ""
      }${
        top.audio_evidence.merlin_suggestion ? ` · Merlin prior: ${top.audio_evidence.merlin_suggestion.species_name}` : ""
      }`
    : "No audio clip uploaded for this observation.";
  const audioScore = top.audio_evidence ? Math.min(99, Math.max(conf - 2, 40)) : 0;

  const contextText = top.contextual_evidence
    ? `${top.contextual_evidence.summary || top.contextual_evidence.plausibility_reason || "Regional checklist checked."} (${top.contextual_evidence.source || "Checklist"})`
    : top.evidence?.summary || "Regional checklist context not verified.";
  const contextScore = top.contextual_evidence ? Math.min(99, Math.max(conf, 60)) : 50;

  const confBadgeLabel = conf >= 80 ? "High Consensus" : conf >= 50 ? "Moderate Match" : "Low Confidence";

  let html = `
    <!-- Specimen Hero Card -->
    <article class="specimen-hero-card">
      <div class="specimen-hero-media">
        ${heroPhoto ? `<img src="${escapeHtml(heroPhoto)}" alt="${escapeHtml(top.common_name)}">` : ""}
        <div class="specimen-hero-overlay">
          <div class="specimen-hero-badges">
            <span class="hero-badge-light">
              <span class="status-dot" style="background: var(--secondary);"></span>
              ${isVerified ? "Human Verified" : "Heuristic • Uncalibrated"}
            </span>
            <span class="hero-badge-dark">Field Specimen #${escapeHtml(shortId)}</span>
          </div>
          <div class="specimen-hero-title-block">
            <div class="consensus-eyebrow">
              <span class="material-symbols-outlined icon-xs">verified</span>
              <span>${escapeHtml(modalityLabel)} MATCH</span>
            </div>
            <h1 class="specimen-hero-name">${escapeHtml(top.common_name)}</h1>
            <div class="specimen-hero-subrow">
              <span class="specimen-hero-sci">${escapeHtml(top.scientific_name || "Species candidate")}</span>
              <span class="specimen-status-pill">${isVerified ? `Verified: ${escapeHtml(record.user_correction.confirmed_species)}` : `${conf}% Heuristic`}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="specimen-traits-strip">
        <div class="trait-cell">
          <span class="trait-label">Modality</span>
          <span class="trait-value">${escapeHtml(modalityLabel)}</span>
        </div>
        <div class="trait-cell">
          <span class="trait-label">Location</span>
          <span class="trait-value">${escapeHtml(obsLoc.split(",")[0])}</span>
        </div>
        <div class="trait-cell">
          <span class="trait-label">Date</span>
          <span class="trait-value">${escapeHtml(obsDate)}</span>
        </div>
      </div>
    </article>

    <!-- Algorithmic Assessment Card -->
    <article class="assessment-card">
      <div class="assessment-header">
        <span class="eyebrow-dot">ALGORITHMIC ASSESSMENT</span>
        <span class="source-pill">${escapeHtml(confBadgeLabel)}</span>
      </div>
      <div class="assessment-body">
        <div class="trust-ring-wrap" aria-label="${conf}% heuristic confidence">
          <svg class="trust-ring-svg" viewBox="0 0 86 86">
            <circle class="trust-ring-track" cx="43" cy="43" r="36"></circle>
            <circle class="trust-ring-fill" cx="43" cy="43" r="36"
              stroke-dasharray="${circumference.toFixed(1)}"
              stroke-dashoffset="${dashOffset.toFixed(1)}"></circle>
          </svg>
          <div class="trust-ring-center">
            <span class="trust-pct">${conf}%</span>
            <span class="trust-sub">Heuristic</span>
          </div>
        </div>
        <div class="assessment-copy">
          <h2 class="assessment-heading">${isVerified ? "Verified Field Observation" : "Multimodal Sensor Assessment"}</h2>
          <p class="assessment-desc">${escapeHtml(top.reason || "Diagnostic plumage, acoustic, and regional checklist signals evaluated.")}</p>
          <div class="assessment-meta-chips">
            <span class="meta-chip-soft">Model: ${escapeHtml(top.visual_evidence?.model_name || "Gemini + BirdAI")}</span>
            <span class="meta-chip-soft">Uncalibrated Score</span>
          </div>
        </div>
      </div>
    </article>

    <!-- Multimodal Breakdown -->
    <div class="breakdown-section-header">
      <h2 class="breakdown-title">
        <span class="material-symbols-outlined icon-sm text-secondary">hub</span>
        <span>Multimodal Breakdown</span>
      </h2>
      <span class="breakdown-count">3 Evidence Vectors</span>
    </div>

    <div class="vector-card">
      <div class="vector-header">
        <span class="vector-name"><span class="material-symbols-outlined icon-sm text-secondary">photo_camera</span>Visual Morphology</span>
        <span class="vector-score">${visualScore ? `${visualScore}% Match` : "Not Provided"}</span>
      </div>
      <div class="vector-bar-track"><div class="vector-bar-fill" style="width: ${visualScore}%;"></div></div>
      <p class="vector-text">${escapeHtml(visualText)}</p>
    </div>

    <div class="vector-card">
      <div class="vector-header">
        <span class="vector-name"><span class="material-symbols-outlined icon-sm text-secondary">graphic_eq</span>Bioacoustic Syllables</span>
        <span class="vector-score">${audioScore ? `${audioScore}% Match` : "Not Provided"}</span>
      </div>
      <div class="vector-bar-track"><div class="vector-bar-fill" style="width: ${audioScore}%;"></div></div>
      <p class="vector-text">${escapeHtml(audioText)}</p>
    </div>

    <div class="vector-card">
      <div class="vector-header">
        <span class="vector-name"><span class="material-symbols-outlined icon-sm text-secondary">map</span>Location &amp; Phenology</span>
        <span class="vector-score">${contextScore}% Context</span>
      </div>
      <div class="vector-bar-track"><div class="vector-bar-fill" style="width: ${contextScore}%;"></div></div>
      <p class="vector-text">${escapeHtml(contextText)}</p>
    </div>
  `;

  if (alternates.length > 0) {
    html += `
      <div class="breakdown-section-header">
        <h2 class="breakdown-title">
          <span class="material-symbols-outlined icon-sm text-secondary">compare_arrows</span>
          <span>Candidate Differentiation</span>
        </h2>
        <span class="breakdown-count">Top Alternate Hits</span>
      </div>
    `;
    alternates.forEach((alt) => {
      html += `
        <div class="alt-candidate-card">
          <div style="min-width: 0;">
            <div class="alt-cand-name">${escapeHtml(alt.common_name)}</div>
            <div class="alt-cand-sci">${escapeHtml(alt.scientific_name || "")}</div>
            <div class="alt-cand-diff">${escapeHtml(alt.reason || "Alternate visual/contextual match.")}</div>
          </div>
          <div class="alt-cand-actions">
            <span class="source-pill">${alt.confidence_probability}% Match</span>
            <button type="button" class="btn-secondary alt-select-btn" data-common="${escapeHtml(alt.common_name)}" data-sci="${escapeHtml(alt.scientific_name || "")}">
              Select
            </button>
          </div>
        </div>
      `;
    });
  }

  html += `
    <div class="results-action-bar">
      <button type="button" id="btn-confirm-top" class="btn-primary-full">
        <span class="material-symbols-outlined icon-sm">bookmark_added</span>
        <span>${isVerified ? "Update Verified Species" : "Confirm & Add to Life List"}</span>
      </button>
      <div class="results-secondary-row">
        <button type="button" id="btn-export-record" class="btn-surface-action">
          <span class="material-symbols-outlined icon-sm">download</span>
          <span>Export JSON</span>
        </button>
        <button type="button" id="btn-results-new" class="btn-surface-action">
          <span class="material-symbols-outlined icon-sm">photo_camera</span>
          <span>New Capture</span>
        </button>
      </div>
    </div>
  `;

  list.innerHTML = html;

  document.getElementById("btn-confirm-top")?.addEventListener("click", () => {
    openCorrectionModal(top.common_name, top.scientific_name || "");
  });
  document.querySelectorAll(".alt-select-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      openCorrectionModal(btn.dataset.common || "", btn.dataset.sci || "");
    });
  });
  document.getElementById("btn-export-record")?.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `birdai-${shortId.toLowerCase()}.json`;
    a.click();
  });
  document.getElementById("btn-results-new")?.addEventListener("click", () => switchView("new"));

  container.style.display = "flex";
}

/* ==================== Verification Modal ==================== */
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
    if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to save correction."));
    currentRecord = await res.json();
    closeModal();
    updateMatchDrawer(currentRecord);
    renderResults(currentRecord);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

/* ==================== Sightings & Radar Tab ==================== */
async function handleChatSubmit(e) {
  e.preventDefault();
  if (!currentUser) {
    openAuthModal("Please sign in to query live eBird & ornitho.ch sightings.");
    return;
  }

  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-chat-send");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  sendBtn.disabled = true;

  const latVal = document.getElementById("latitude")?.value;
  const lngVal = document.getElementById("longitude")?.value;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        message,
        conversation_history: chatHistory,
        user_latitude: latVal ? parseFloat(latVal) : null,
        user_longitude: lngVal ? parseFloat(lngVal) : null,
        preferred_radius_km: preferredRadiusKm,
      }),
    });

    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      openAuthModal("Session expired. Please sign in again.");
      return;
    }
    if (!res.ok) throw new Error(await readErrorDetail(res, "Sightings query failed."));

    const data = await res.json();
    chatHistory.push({ role: "user", content: message });
    chatHistory.push({ role: "assistant", content: data.reply });
    renderSightingsActivity(data.reply, data.sightings || []);
  } catch (err) {
    renderSightingsActivity(`Could not fetch sightings: ${err.message}`, []);
  } finally {
    sendBtn.disabled = false;
  }
}

async function loadNearbySightings() {
  if (!currentUser) {
    openAuthModal("Please sign in to scan nearby eBird & ornitho.ch sightings.");
    return;
  }
  const loc = document.getElementById("location-text")?.value.trim() || "";
  const lat = document.getElementById("latitude")?.value || "";
  const lng = document.getElementById("longitude")?.value || "";

  const params = new URLSearchParams({ radius_km: String(preferredRadiusKm) });
  if (loc) params.set("location", loc);
  if (lat) params.set("lat", lat);
  if (lng) params.set("lng", lng);

  try {
    const res = await fetch(`/api/sightings?${params.toString()}`, { headers: getAuthHeaders() });
    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      openAuthModal("Session expired. Please sign in again.");
      return;
    }
    if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to scan nearby sightings."));
    const data = await res.json();
    const list = data.sightings || [];
    const summary = list.length
      ? `Found ${list.length} recent sighting(s) within ${preferredRadiusKm} km.`
      : `No recent sightings returned within ${preferredRadiusKm} km. Try specifying a city or species in the search bar.`;
    renderSightingsActivity(summary, list);
  } catch (err) {
    renderSightingsActivity(`Scan error: ${err.message}`, []);
  }
}

function renderSightingsActivity(summaryText, sightings) {
  const banner = document.getElementById("radar-assistant-banner");
  const summaryEl = document.getElementById("radar-summary-text");
  const countEl = document.getElementById("sightings-count-label");
  const feed = document.getElementById("chat-messages");

  if (banner && summaryEl) {
    summaryEl.innerHTML = escapeHtml(summaryText).replace(/\n/g, "<br>");
    banner.style.display = "flex";
  }
  if (countEl) countEl.textContent = `${sightings.length} Sighted`;
  if (!feed) return;

  if (!sightings || sightings.length === 0) {
    feed.innerHTML = `
      <div class="surface-card state-box compact-state">
        <p class="state-title">No Matching Sightings</p>
        <p class="state-sub">Try widening the radius or searching a nearby city or species name.</p>
      </div>
    `;
    return;
  }

  feed.innerHTML = sightings.slice(0, 15).map((s) => {
    const name = s.common_name || s.species || "Unknown Species";
    const sci = s.scientific_name || "";
    const loc = s.location_name || s.location || "Nearby hotspot";
    const when = s.observation_date || s.date || "Recent";
    const src = s.source || "eBird";
    const count = s.count != null ? `Count: ${s.count}` : "Verified record";
    return `
      <article class="sighting-card">
        <div class="sighting-card-top">
          <div style="min-width: 0;">
            <div class="sighting-time-loc">${escapeHtml(when)}</div>
            <div class="sighting-common">${escapeHtml(name)}</div>
            ${sci ? `<div class="sighting-sci">${escapeHtml(sci)}</div>` : ""}
            <div class="sighting-observer">${escapeHtml(loc)}</div>
          </div>
          <span class="source-pill">${escapeHtml(src)}</span>
        </div>
        <div class="sighting-card-footer">
          <span>${escapeHtml(count)}</span>
          <span>Live Feed</span>
        </div>
      </article>
    `;
  }).join("");
}

/* ==================== Navigation & Life List Journal ==================== */
function switchView(view) {
  const viewMap = {
    new: "capture-view",
    results: "results-view",
    sightings: "sightings-view",
    journal: "journal-view",
  };

  Object.entries(viewMap).forEach(([key, id]) => {
    document.getElementById(id)?.classList.toggle("active", key === view);
  });

  document.querySelectorAll(".bottom-nav-item").forEach((btn) => {
    const isActive = btn.dataset.view === view;
    btn.classList.toggle("active", isActive);
    if (isActive) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });

  if (view === "journal") loadJournal();
}

async function loadJournal() {
  const listEl = document.getElementById("journal-list");
  if (!listEl) return;

  if (!currentUser) {
    cachedJournalRecords = [];
    updateLifeListStats([]);
    listEl.innerHTML = `
      <div class="surface-card state-box">
        <div class="state-icon-circle"><span class="material-symbols-outlined">lock</span></div>
        <p class="state-title">Private Life List</p>
        <p class="state-sub">Sign in to view your saved field observations and verified ground truth.</p>
        <button type="button" class="btn-primary-inline" onclick="openAuthModal()">Sign In</button>
      </div>
    `;
    return;
  }

  listEl.innerHTML = '<div class="surface-card state-box"><div class="spinner"></div></div>';

  try {
    const res = await fetch("/api/observations?limit=100", { headers: getAuthHeaders() });
    if (res.status === 401) {
      setAuthToken(null);
      checkAuthStatus();
      loadJournal();
      return;
    }
    const records = await res.json();
    cachedJournalRecords = Array.isArray(records) ? records : [];
    updateLifeListStats(cachedJournalRecords);
    renderJournalEntries();
  } catch (err) {
    listEl.innerHTML = `<div class="surface-card state-box"><p class="state-sub">Error loading journal: ${escapeHtml(err.message)}</p></div>`;
  }
}

function updateLifeListStats(records) {
  const uniqueSpecies = new Set();
  let verifiedCount = 0;

  records.forEach((r) => {
    const species =
      r.user_correction?.confirmed_species ||
      (r.candidates && r.candidates.length > 0 ? r.candidates[0].common_name : null);
    if (species) uniqueSpecies.add(species.toLowerCase());
    if (r.user_correction) verifiedCount += 1;
  });

  const spEl = document.getElementById("stat-species-count");
  const logsEl = document.getElementById("stat-logs-count");
  const verEl = document.getElementById("stat-verified-sub");
  if (spEl) spEl.textContent = String(uniqueSpecies.size);
  if (logsEl) logsEl.textContent = String(records.length);
  if (verEl) verEl.textContent = `${verifiedCount} Verified`;
}

function renderJournalEntries() {
  const listEl = document.getElementById("journal-list");
  const countLabel = document.getElementById("journal-count-label");
  if (!listEl) return;

  const query = (document.getElementById("journal-search-input")?.value || "").trim().toLowerCase();
  const filtered = cachedJournalRecords.filter((r) => {
    if (currentJournalFilter === "verified" && !r.user_correction) return false;
    if (currentJournalFilter === "audio" && !r.audio_path) return false;
    if (currentJournalFilter === "photo" && !r.image_path) return false;
    if (query) {
      const hay = [
        r.user_correction?.confirmed_species,
        r.candidates?.[0]?.common_name,
        r.candidates?.[0]?.scientific_name,
        r.observation_context?.location_text,
        r.user_correction?.correction_notes,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  if (countLabel) countLabel.textContent = `${filtered.length} logged entries`;

  if (filtered.length === 0) {
    listEl.innerHTML = `
      <div class="surface-card state-box compact-state">
        <p class="state-title">No Matching Field Entries</p>
        <p class="state-sub">Capture an observation on the Identify tab or clear your active filter.</p>
      </div>
    `;
    return;
  }

  listEl.innerHTML = "";
  filtered.forEach((r) => {
    const top = r.candidates && r.candidates.length > 0 ? r.candidates[0] : null;
    const displayName = r.user_correction?.confirmed_species || top?.common_name || "Unknown bird";
    const sciName = r.user_correction?.scientific_name || top?.scientific_name || "";
    const conf = top ? `${top.confidence_probability}%` : "--";
    const loc = r.observation_context?.location_text || "Unknown location";
    const obsDate = r.observation_context?.observation_date || "";
    const coords =
      r.observation_context?.latitude != null && r.observation_context?.longitude != null
        ? `${Number(r.observation_context.latitude).toFixed(4)}°, ${Number(r.observation_context.longitude).toFixed(4)}°`
        : loc;
    const note = r.user_correction?.correction_notes || top?.reason || "";

    const card = document.createElement("article");
    card.className = "journal-log-card";
    card.innerHTML = `
      <div class="journal-log-top">
        <img class="journal-thumb" src="${escapeHtml(r.image_path || "/static/icon.png")}" alt="${escapeHtml(displayName)}" onerror="this.src='/static/icon.png'">
        <div class="journal-log-meta">
          <div class="journal-log-name">${escapeHtml(displayName)}</div>
          ${sciName ? `<div class="journal-log-sci">${escapeHtml(sciName)}</div>` : ""}
          <div class="journal-log-when">${escapeHtml([obsDate, loc].filter(Boolean).join(" • "))}</div>
        </div>
        <div class="journal-log-badge-col">
          <span class="source-pill">• ${escapeHtml(conf)}</span>
          <span class="journal-status-tag">${r.user_correction ? "VERIFIED" : "LOGGED"}</span>
        </div>
      </div>
      ${
        r.audio_path
          ? `<div class="journal-audio-banner"><span>Bioacoustic recording attached</span><span class="material-symbols-outlined icon-sm text-mint">graphic_eq</span></div>`
          : note
          ? `<div class="journal-note-box">${escapeHtml(note)}</div>`
          : ""
      }
      <div class="journal-log-footer">
        <span>${escapeHtml(coords)}</span>
        <div class="modality-chips">
          ${r.audio_path ? '<span class="modality-chip">Audio</span>' : ""}
          ${r.image_path ? '<span class="modality-chip">Photo</span>' : ""}
        </div>
      </div>
    `;
    card.addEventListener("click", () => {
      currentRecord = r;
      currentImageUrl = r.image_path || null;
      updateMatchDrawer(r);
      renderResults(r);
      switchView("results");
    });
    listEl.appendChild(card);
  });
}

function exportJournalCsv() {
  if (!cachedJournalRecords.length) {
    alert("No observations loaded to export yet.");
    return;
  }
  const headers = ["id", "date", "location", "species", "scientific_name", "confidence", "verified", "notes"];
  const rows = cachedJournalRecords.map((r) => {
    const top = r.candidates?.[0];
    const cols = [
      r.id || "",
      r.observation_context?.observation_date || "",
      r.observation_context?.location_text || "",
      r.user_correction?.confirmed_species || top?.common_name || "",
      r.user_correction?.scientific_name || top?.scientific_name || "",
      top?.confidence_probability ?? "",
      r.user_correction ? "yes" : "no",
      r.user_correction?.correction_notes || "",
    ];
    return cols.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",");
  });
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "birdai-life-list.csv";
  a.click();
}
