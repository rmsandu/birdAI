// BirdAI Responsive Frontend Controller with Multi-User Auth
let currentRecord = null;
let currentImageFile = null;
let currentAudioFile = null;
let currentUser = null;

document.addEventListener("DOMContentLoaded", () => {
  initDateDefaults();
  setupEventListeners();
  checkAuthStatus();
});

function initDateDefaults() {
  // Leave date/time empty by default.
  // They are auto-filled from EXIF when an image is uploaded.
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
    return { ...extraHeaders, "Authorization": `Bearer ${token}` };
  }
  return extraHeaders;
}

async function checkAuthStatus() {
  const token = getAuthToken();
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const userBadge = document.getElementById("user-profile-badge");
  const emailDisplay = document.getElementById("user-email-display");

  if (!token) {
    currentUser = null;
    if (btnOpenAuth) btnOpenAuth.style.display = "block";
    if (userBadge) userBadge.style.display = "none";
    return;
  }

  try {
    const res = await fetch("/api/auth/me", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (res.ok) {
      currentUser = await res.json();
      if (btnOpenAuth) btnOpenAuth.style.display = "none";
      if (userBadge) userBadge.style.display = "flex";
      if (emailDisplay) emailDisplay.textContent = currentUser.email;
    } else {
      setAuthToken(null);
      currentUser = null;
      if (btnOpenAuth) btnOpenAuth.style.display = "block";
      if (userBadge) userBadge.style.display = "none";
    }
  } catch (err) {
    currentUser = null;
    if (btnOpenAuth) btnOpenAuth.style.display = "block";
    if (userBadge) userBadge.style.display = "none";
  }
}

function setupEventListeners() {
  // Auth Controls
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const authModalClose = document.getElementById("auth-modal-close");
  const btnLogout = document.getElementById("btn-logout");
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  const formLogin = document.getElementById("form-login");
  const formRegister = document.getElementById("form-register");

  if (btnOpenAuth) btnOpenAuth.addEventListener("click", () => openAuthModal());
  if (authModalClose) authModalClose.addEventListener("click", () => closeAuthModal());
  if (btnLogout) btnLogout.addEventListener("click", handleLogout);

  if (tabLogin) {
    tabLogin.addEventListener("click", () => {
      tabLogin.classList.add("active");
      tabRegister.classList.remove("active");
      formLogin.style.display = "block";
      formRegister.style.display = "none";
      hideAuthErrors();
    });
  }

  if (tabRegister) {
    tabRegister.addEventListener("click", () => {
      tabRegister.classList.add("active");
      tabLogin.classList.remove("active");
      formRegister.style.display = "block";
      formLogin.style.display = "none";
      hideAuthErrors();
    });
  }

  if (formLogin) formLogin.addEventListener("submit", handleLoginSubmit);
  if (formRegister) formRegister.addEventListener("submit", handleRegisterSubmit);

  // Navigation
  const navNew = document.getElementById("nav-new");
  const navJournal = document.getElementById("nav-journal");
  if (navNew) navNew.addEventListener("click", () => switchView("new"));
  if (navJournal) navJournal.addEventListener("click", () => switchView("journal"));

  // File Inputs
  const dropzone = document.getElementById("dropzone");
  const imageInput = document.getElementById("image-file-input");
  const audioInput = document.getElementById("audio-file-input");

  if (dropzone) {
    dropzone.addEventListener("click", () => imageInput.click());
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) {
        handleFileSelection(e.dataTransfer.files[0]);
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

  // Geolocation trigger
  const geoBtn = document.getElementById("btn-geolocation");
  if (geoBtn) geoBtn.addEventListener("click", requestBrowserLocation);

  // Analyze Button
  const analyzeBtn = document.getElementById("btn-analyze");
  if (analyzeBtn) analyzeBtn.addEventListener("click", submitObservation);

  // Correction Modal
  const modalClose = document.getElementById("modal-close");
  const btnSaveCorrection = document.getElementById("btn-save-correction");
  if (modalClose) modalClose.addEventListener("click", closeModal);
  if (btnSaveCorrection) btnSaveCorrection.addEventListener("click", submitCorrection);
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
  if (modal) modal.classList.add("active");
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.classList.remove("active");
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

    // If viewing journal, refresh journal
    const journalView = document.getElementById("journal-view");
    if (journalView && journalView.style.display !== "none") {
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

    // Auto-login after registration
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
  if (journalView && journalView.style.display !== "none") {
    loadJournal();
  }
}

function handleFileSelection(file) {
  if (file.type.startsWith("image/") || /\.(jpe?g|png|heic|webp)$/i.test(file.name)) {
    currentImageFile = file;
    const imgPreview = document.getElementById("image-preview");
    const container = document.getElementById("image-preview-container");
    if (imgPreview && container) {
      imgPreview.src = URL.createObjectURL(file);
      container.style.display = "block";
    }
    extractPhotoMetadata(file);
  } else if (file.type.startsWith("audio/") || /\.(wav|mp3|flac|ogg)$/i.test(file.name)) {
    currentAudioFile = file;
    const audPreview = document.getElementById("audio-preview");
    const container = document.getElementById("audio-preview-container");
    if (audPreview && container) {
      audPreview.src = URL.createObjectURL(file);
      container.style.display = "block";
    }
  }
}

async function extractPhotoMetadata(file) {
  const statusEl = document.getElementById("location-status");
  if (statusEl) statusEl.textContent = "Scanning photo for GPS metadata...";

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
        if (statusEl) statusEl.textContent = data.status || "✓ GPS coordinates extracted from photo metadata.";
      } else {
        if (statusEl) statusEl.textContent = data.status || "No GPS metadata found in photo. Location empty by default.";
      }
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "Photo metadata scan skipped.";
  }
}

function requestBrowserLocation() {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }
  const statusEl = document.getElementById("location-status");
  if (statusEl) statusEl.textContent = "Requesting GPS coordinates...";

  navigator.geolocation.getCurrentPosition(
    (position) => {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      document.getElementById("latitude").value = lat.toFixed(5);
      document.getElementById("longitude").value = lng.toFixed(5);
      if (statusEl) statusEl.textContent = `Coordinates detected: ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
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

  if (analyzeBtn) analyzeBtn.disabled = true;
  if (resultsContainer) resultsContainer.style.display = "none";
  if (loadingContainer) loadingContainer.style.display = "block";

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
    renderResults(currentRecord);
  } catch (err) {
    alert(`Analysis error: ${err.message}`);
  } finally {
    if (analyzeBtn) analyzeBtn.disabled = false;
    if (loadingContainer) loadingContainer.style.display = "none";
  }
}

function renderResults(record) {
  const container = document.getElementById("results-container");
  if (!container) return;

  const candidatesList = document.getElementById("candidates-list");
  candidatesList.innerHTML = "";

  if (!record.candidates || record.candidates.length === 0) {
    candidatesList.innerHTML = `
      <div class="state-box">
        <p>No species candidates could be confidently resolved.</p>
        <p style="font-size: 0.85rem; margin-top: 6px;">${record.suggested_next_action || 'Try another photo or clearer audio.'}</p>
      </div>
    `;
    container.style.display = "block";
    return;
  }

  record.candidates.forEach((cand, idx) => {
    const isTop = idx === 0;
    const card = document.createElement("div");
    card.className = `candidate-card ${isTop ? 'top-rank' : ''}`;

    const conf = cand.confidence_probability;
    const confClass = conf >= 75 ? 'high' : (conf >= 40 ? 'medium' : 'low');

    card.innerHTML = `
      <div class="candidate-header">
        <div>
          <div class="species-name">${cand.common_name}</div>
          <div class="species-scientific">${cand.scientific_name || ''}</div>
        </div>
        <div class="confidence-chip ${confClass}">
          <span>${conf}%</span>
          <span class="uncalibrated-note">Uncalibrated</span>
        </div>
      </div>
      <div class="candidate-reason">${cand.reason || 'Diagnostic features match observation.'}</div>

      <div class="evidence-section">
        <div class="evidence-tabs">
          <button class="tab-btn active" onclick="switchEvidenceTab(this, 'visual-${idx}')">Visual</button>
          <button class="tab-btn" onclick="switchEvidenceTab(this, 'audio-${idx}')">Audio</button>
          <button class="tab-btn" onclick="switchEvidenceTab(this, 'context-${idx}')">Context</button>
        </div>
        <div id="visual-${idx}" class="evidence-body">
          ${cand.visual_evidence ? `${cand.visual_evidence.reason || 'Features evaluated from image.'} (Model: ${cand.visual_evidence.model_name})` : 'No visual evidence uploaded for this modality.'}
        </div>
        <div id="audio-${idx}" class="evidence-body" style="display: none;">
          ${cand.audio_evidence ? `${cand.audio_evidence.reason || 'Call analyzed.'} ${cand.audio_evidence.duration_seconds ? `· ${cand.audio_evidence.duration_seconds}s` : ''} ${cand.audio_evidence.merlin_suggestion ? `· Merlin: ${cand.audio_evidence.merlin_suggestion.species_name}` : ''}` : 'No audio recording uploaded for this modality.'}
        </div>
        <div id="context-${idx}" class="evidence-body" style="display: none;">
          ${cand.contextual_evidence ? `${cand.contextual_evidence.summary || cand.contextual_evidence.plausibility_reason} (Source: ${cand.contextual_evidence.source})` : (cand.evidence ? cand.evidence.summary : 'Contextual evidence unverified.')}
        </div>
      </div>

      <div class="verify-footer">
        <div id="verify-status-${idx}">
          ${record.user_correction ? `<span class="verified-badge">✓ Verified: ${record.user_correction.confirmed_species}</span>` : '<span style="font-size: 0.8rem; color: var(--color-text-muted);">Unverified</span>'}
        </div>
        <button class="btn-secondary" onclick="openCorrectionModal('${cand.common_name}', '${cand.scientific_name || ''}')">
          Confirm / Correct
        </button>
      </div>
    `;
    candidatesList.appendChild(card);
  });

  container.style.display = "block";
}

window.switchEvidenceTab = function(btn, targetId) {
  const parent = btn.closest(".evidence-section");
  parent.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  parent.querySelectorAll(".evidence-body").forEach(el => el.style.display = "none");
  btn.classList.add("active");
  const target = document.getElementById(targetId);
  if (target) target.style.display = "block";
};

window.openCorrectionModal = function(defaultSpecies, defaultSci) {
  const modal = document.getElementById("correction-modal");
  const input = document.getElementById("correct-species-input");
  const sciInput = document.getElementById("correct-sci-input");
  if (input) input.value = defaultSpecies;
  if (sciInput) sciInput.value = defaultSci;
  if (modal) modal.classList.add("active");
};

function closeModal() {
  const modal = document.getElementById("correction-modal");
  if (modal) modal.classList.remove("active");
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
    renderResults(currentRecord);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function switchView(view) {
  const captureView = document.getElementById("capture-view");
  const journalView = document.getElementById("journal-view");
  const navNew = document.getElementById("nav-new");
  const navJournal = document.getElementById("nav-journal");

  if (view === "new") {
    captureView.style.display = "grid";
    journalView.style.display = "none";
    navNew.classList.add("active");
    navJournal.classList.remove("active");
  } else {
    captureView.style.display = "none";
    journalView.style.display = "block";
    navNew.classList.remove("active");
    navJournal.classList.add("active");
    loadJournal();
  }
}

async function loadJournal() {
  const listEl = document.getElementById("journal-list");
  if (!currentUser) {
    listEl.innerHTML = `
      <div class="state-box">
        <div style="font-size: 2rem; margin-bottom: 8px;">🔒</div>
        <p style="font-weight: 700; color: var(--color-pine);">Private Observation Journal</p>
        <p style="font-size: 0.85rem; color: var(--color-text-muted); margin-top: 4px; margin-bottom: 12px;">
          Please sign in to view your private field observations.
        </p>
        <button class="btn-primary" style="max-width: 160px; margin: 0 auto;" onclick="openAuthModal()">Sign In</button>
      </div>
    `;
    return;
  }

  listEl.innerHTML = '<div class="spinner"></div>';

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

    if (records.length === 0) {
      listEl.innerHTML = '<div class="state-box"><p>No saved observations yet.</p></div>';
      return;
    }

    listEl.innerHTML = "";
    records.forEach(r => {
      const item = document.createElement("div");
      item.className = "card";
      item.style.marginBottom = "14px";
      const topName = r.candidates && r.candidates.length > 0 ? r.candidates[0].common_name : "Unknown bird";
      const verified = r.user_correction ? `<span class="verified-badge">✓ Verified: ${r.user_correction.confirmed_species}</span>` : '<span style="color: var(--color-text-muted); font-size: 0.8rem;">Unverified</span>';

      item.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div>
            <div style="font-weight: 700; font-size: 1.1rem; color: var(--color-pine);">${topName}</div>
            <div style="font-size: 0.8rem; color: var(--color-text-muted); margin-top: 2px;">
              ${r.observation_context.location_text} · ${r.observation_context.observation_date}
            </div>
          </div>
          <div>${verified}</div>
        </div>
      `;
      listEl.appendChild(item);
    });
  } catch (err) {
    listEl.innerHTML = `<div class="state-box"><p>Error loading journal: ${err.message}</p></div>`;
  }
}
