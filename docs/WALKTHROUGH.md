# Walkthrough: BirdAI Phase 1 — Database & Multi-User Security

We have completed the implementation of **Phase 1** for BirdAI: transitioning from plain JSON files to a structured **SQLite database** using **SQLAlchemy 2.0**, paired with **JWT authentication**, **bcrypt password hashing**, and **strict observation privacy** per user.

---

## What Changed

### 1. Database & ORM Layer ([src/birdai/db/](file:///Users/raluca/develop/birdAI/src/birdai/db/))
- **`session.py`**:
  - Configures SQLAlchemy engine with SQLite foreign key enforcement (`PRAGMA foreign_keys=ON;`).
  - Implements `get_db()` dependency for FastAPI.
  - Implements `init_db()` for automatic schema generation.
- **`models.py`**:
  - **`UserModel`**: UUID primary key, unique email, bcrypt hashed password, full name, active status, creation timestamp, and cascade relationship to observations.
  - **`ObservationModel`**: Observation ID primary key, `user_id` foreign key (indexed), creation timestamp, modality, media paths, structured JSON payloads (`context_json`, `merlin_suggestion_json`, `candidates_json`, `uncertainty_reasons_json`, `user_correction_json`).
- **`sql_store.py`**:
  - `SQLObservationStore`: Implements full observation lifecycle (`save`, `get`, `update_correction`, `list`, `get_media_path`) with mandatory `user_id` scoping.

### 2. Authentication & Security Layer ([src/birdai/auth/](file:///Users/raluca/develop/birdAI/src/birdai/auth/))
- **`security.py`**:
  - `hash_password` & `verify_password`: Uses modern `bcrypt` directly (bypassing legacy passlib compatibility issues in Python 3.14).
  - `create_access_token` & `decode_access_token`: Generates and verifies signed JSON Web Tokens (`HS256`, 7-day default expiration).
- **`dependencies.py`**:
  - `get_current_user`: Validates Bearer token from the `Authorization` header, retrieves user from database, and enforces authentication.
  - `get_current_active_user`: Verifies `is_active` status.
- **`routes.py`**:
  - `POST /api/auth/register`: Validates email and creates new user accounts.
  - `POST /api/auth/token`: OAuth2 standard login endpoint returning signed JWT.
  - `GET /api/auth/me`: Retrieves current authenticated user profile.

### 3. API Routes Update ([src/birdai/api/routes.py](file:///Users/raluca/develop/birdAI/src/birdai/api/routes.py))
- Injected `current_user: UserModel = Depends(get_current_active_user)` and `obs_store = Depends(get_store)` into all observation endpoints.
- Enforced strict tenant privacy:
  - Users can **only** save, fetch, update, and list their own observations (`WHERE user_id = current_user.id`).
  - Media streaming `GET /api/media/{id}/{file}` verifies that the requesting user owns the observation before serving bytes.

### 4. Legacy Data Migration ([scripts/migrate_json_to_db.py](file:///Users/raluca/develop/birdAI/scripts/migrate_json_to_db.py))
- Reads existing JSON records from `data/observations/*.json`.
- Automatically seeds a default admin user (`admin@birdai.local`) if no user exists.
- Ingests all historical observations into `data/birdai.db` without data loss.

### 5. Frontend Multi-User UI ([src/birdai/frontend/](file:///Users/raluca/develop/birdAI/src/birdai/frontend/))
- **Navigation Bar**: Added user status section (Sign In button when logged out; user email badge + Sign Out button when logged in).
- **Auth Modal**: Tabbed Sign In / Create Account modal styled with BirdAI palette (`#123F2A`, `#547239`, `#9F2245`).
- **Token Management**: `app.js` manages JWT in `localStorage`, attaches `Authorization: Bearer <token>` to all protected calls, and displays sign-in prompts when unauthorized.

---

## Validation & Test Results

Executed the full test suite covering Unit, Auth, Storage, Migration, and Route isolation:

```bash
PYTHONPATH=src ./.venv/bin/pytest tests/ -v
```

**Result: 57 passed in 3.31s (100% pass rate)**:
- `tests/test_auth.py`: 4 passed (Bcrypt hashing, JWT encoding/decoding, registration & login flow, 401 on unauthenticated)
- `tests/test_sql_store.py`: 1 passed (Strict privacy isolation: User B cannot get, list, correct, or view media for User A's observations)
- `tests/test_migration.py`: 1 passed (Migration script imports JSON files and assigns them to seed user)
- `tests/test_api_routes.py`: 4 passed (Health, Authenticated create/get/correct, Media requirement, 401 rejection on unauthenticated)
- All 47 existing tests across perception, audio, metadata, Gemini fallback, evaluation, and classifier: all passed.

---

## How to Test

1. Start the server:
   ```bash
   PYTHONPATH=src ./.venv/bin/uvicorn birdai.api.app:app --host 0.0.0.0 --port 8080 --reload
   ```
2. Open [http://localhost:8080](http://localhost:8080):
   - Click **Sign In** in the top right to log in as `admin@birdai.local` (password: `birdai12345`) or create a new account.
   - Switch to the **Journal** tab: verify you see observations owned by your account.
   - Log out, create a second account (`user2@example.com`), and verify the journal is empty (strict isolation).
   - Upload an observation as `user2`, verify it appears only under `user2`'s journal.

---

# Walkthrough: Phase 2 — Natural-Language Sightings Chatbot

BirdAI can now answer questions such as *"Have any kingfishers been seen within 5 km of Neeracherried?"*, *"Gibt es Eulen bei Zürich?"* or *"Avez-vous vu des pics près de Genève?"* using live **eBird** data. ornitho.ch support exists but is **parked** (see section 6).

## What Changed

### 1. Endpoints ([src/birdai/api/routes.py](../src/birdai/api/routes.py))
Both endpoints require a signed-in user (`Authorization: Bearer <token>`), like the observation routes. This protects the Gemini quota and the eBird API key from anonymous use.
- `POST /api/chat`: takes `message`, optional `conversation_history`, GPS coordinates and a preferred radius. Returns `reply`, `sightings`, `parsed_query`, `mode` (`"ai"` or `"rule_based"`) and `unavailable_sources`.
- `GET /api/sightings`: direct query by `location` or `lat`/`lng`, `radius_km` (1–50) and `species` (any language, or a group like `owl`). Returns `{sightings, unavailable_sources}`.

### 2. Chat agent ([src/birdai/chat_agent.py](../src/birdai/chat_agent.py))
- **Agent loop:** Gemini may call `search_bird_sightings` up to `MAX_TOOL_ROUNDS` (3) times per message, e.g. to retry a species with a wider radius or to look up two birds. Each result goes back as a function response. After the last round, tool calling is switched off (`mode="NONE"`) so Gemini must answer with what it has.
- Replies in the user's language. For group searches it summarises up to ~6 species; with more, it summarises the nearest few and asks whether to focus on one.
- Earlier turns in `conversation_history` are sent to Gemini (`assistant` → `model`, `system` messages skipped), so follow-ups like *"and within 5 km?"* work.
- **Rule-based fallback** (no Gemini key, or Gemini fails): detects bird names anywhere in the message in all four languages (see section 4), plus some Swiss places and 5/15/25 km. It says so in the reply (*Basic search mode*) and doesn't use conversation history.

### 3. Sightings aggregator ([src/birdai/sightings_aggregator.py](../src/birdai/sightings_aggregator.py))
- Search centre: GPS → known Swiss hotspots → geocoding → configured default location.
- **Species search:** fetches everything seen in the area (uncapped), matches the query against those species' names, then fetches full sightings for each match (nearest `MAX_SPECIES_PER_SEARCH` = 10 species). `parsed_query` includes `matched_species` (names in all four languages), `species_match_type` (`species` / `group` / `none`) and `species_not_fetched`.
- Failed sources are reported in `unavailable_sources` and in the reply, so "couldn't check" is never shown as "no birds".
- Enforces the radius and sorts **closest first, most recent first** among equal distances.

### 4. Multilingual species matching ([src/birdai/species_search.py](../src/birdai/species_search.py))
Uses eBird's own localized names (taxonomy API, `en`/`de`/`fr`/`it`, cached per species):
- Exact names in any language or Latin: *Eisvogel*, *Martin pescatore*, *Alcedo atthis*.
- Partial names and plurals: *kingfishers*, *red kite*, *hiboux*; German compound heads: *Meise* → Kohlmeise, Blaumeise.
- Groups: eBird family names are English-only, so a small alias table maps group words in all four languages (*Eulen*, *chouette*, *gufo* → Owls; also woodpeckers, tits, ducks/waterfowl, gulls, herons, birds of prey, finches, grebes).
- Known limitation: *ducks* uses the eBird family "Ducks, Geese, and Waterfowl", so geese and swans are included.

### 5. eBird client ([src/birdai/ebird_client.py](../src/birdai/ebird_client.py))
- All recent, single-species and notable radius searches share one helper; each result has a species code, distance and checklist link. `max_results=None` fetches everything for the area.
- `species_names()` returns localized names for a set of species codes.

### 6. ornitho.ch client — parked ([src/birdai/ornitho_client.py](../src/birdai/ornitho_client.py))
- The RSS URL it used returns ornitho.ch's **login page**; there is no public feed. It's off by default (`ORNITHO_ENABLED=false`) and is not queried or mentioned in replies.
- Re-enable it once there's API access (Swiss Ornithological Institute / Biolovision). The client already skips records with unknown locations, never returns placeholder data, and raises `OrnithoServiceError` when unreachable.

## Tests
- `tests/test_species_search.py`: names in all four languages, groups, plurals, compounds, free-text detection, false positives (*tit* ≠ *Tree Pipit*, *Reiher* ≠ *Reiherente*).
- `tests/test_chat_agent.py`: agent loop (history, follow-up searches, forced answer after 3 rounds, all sources down, Gemini failure), rule-based fallback.
- `tests/test_sightings_aggregator.py`: centre resolution, merging, radius enforcement, uncapped multilingual species search, owl group, lookup cap, ornitho parked, failed-source reporting.
- `tests/test_ornitho_client.py`: RSS parsing, radius filtering, skipping unknown locations, unreachable feed.
- `tests/test_api_chat.py`: 401 without login, chat and sightings responses (aggregator mocked, no network).
