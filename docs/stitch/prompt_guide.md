# Google Stitch UI Design Guide: BirdAI

This guide provides the design system specifications and ready-to-use prompt pack for creating and iterating on BirdAI screens on **Google Stitch** ([stitch.google.com](https://stitch.google.com/)).

---

## 1. Color Palette Tokens

The design uses a natural history field-guide palette:

| Color | Hex | Semantic Role |
| :--- | :--- | :--- |
| **Deep Evergreen** | `#123F2A` | App header, primary text, dark surfaces, sidebar |
| **Olive Leaf** | `#547239` | High-confidence badges, confirmed checkmarks, nature accents |
| **Crimson Berry** | `#9F2245` | Primary action CTAs, uncertainty flags, warning alerts |
| **Coral Pink** | `#FF868A` | Tab underlines, audio waveforms, interactive chips |
| **Warm Sand Tan** | `#C19168` | Card borders, metadata tags (date, time, GPS), neutral dividers |
| **Warm Canvas** | `#F9F8F6` | App background |
| **Pure White** | `#FFFFFF` | Card surfaces |

---

## 2. Stitch Screen Prompt Pack

Paste these prompts into [stitch.google.com](https://stitch.google.com/) to generate or refine BirdAI screens:

### Screen 1: Field Capture & Upload (Mobile-First)
```
Design a mobile-first wildlife bird observation capture screen for a field observer.
Theme: Clean naturalist field guide aesthetic with deep evergreen (#123F2A), olive green (#547239), and warm sand (#C19168) accents.
Layout:
- Top bar with app title 'BirdAI' and a modern camera/journal toggle.
- Dual-media dropzone supporting camera photo snapshot and audio voice/Merlin recording upload.
- Location card displaying auto-detected GPS coordinates with a subtle openstreetmap pin icon and editable city name.
- Date and time selectors formatted cleanly.
- An expandable 'Merlin Bird ID Suggestion' accordion with an 'Unverified Prior' badge and input fields for Merlin species name and notes.
- A prominent 'Analyze Observation' button styled in crimson berry (#9F2245).
- Ensure 48px touch targets and safe area insets for mobile screens.
```

### Screen 2: Candidate Rankings & Evidence Inspector (Desktop & Mobile)
```
Design a bird perception results screen comparing uncertain species candidates.
Layout:
- Ranked candidate cards sorted by probability (e.g., European Robin, Common Buzzard).
- Confidence chips displaying probability with an explicit 'Uncalibrated Heuristic' warning subtitle.
- Interactive tabbed evidence breakdown inside each candidate card:
  - 'Visual Evidence' tab showing key field marks observed, plumage notes, and model name.
  - 'Audio Evidence' tab displaying audio duration, sample rate, call pattern notes, and Merlin suggestion comparison.
  - 'Context' tab displaying eBird recent sightings count within 25km and seasonal plausibility.
- An alert banner explaining that model scores are uncalibrated and allowing 'Unknown / Insufficient Evidence' fallback.
- A 'Confirm or Correct Label' button opening a verification drawer.
```

### Screen 3: Human Verification Modal (Bottom Sheet)
```
Design a modern bottom-sheet modal for confirming or correcting a bird species identification.
Layout:
- Header: 'Verify or Correct Species' with a close icon.
- Form field for 'Confirmed Common Name' with autocomplete styling.
- Optional 'Scientific Name' field.
- 'Field Notes' textarea for capturing environmental context, lighting, or song playback.
- Green checkmark confirmation button: 'Save Verified Ground Truth'.
- Clean rounded corners (20px top radius), backdrop blur.
```

### Screen 4: Observation Journal (Evaluation History)
```
Design a chronological observation history screen for reviewed bird sightings.
Layout:
- List of past observations with thumbnail previews (photo or audio wave icon).
- Top predicted species vs. human verified species badge.
- Filter chips: 'All', 'Verified', 'Unverified', 'Photo', 'Audio'.
- Summary stats bar at the top showing Top-1 accuracy and total observations logged.
```

---

## 3. Importing Stitch Exports into BirdAI

1. Open your project on [stitch.google.com](https://stitch.google.com/).
2. Export the generated code (HTML/Tailwind CSS or React).
3. Place exported styles and layouts into `src/birdai/frontend/`:
   - `styles.css`: Paste or merge updated design tokens and utility classes.
   - `index.html`: Update screen DOM structures, preserving the element IDs used by `app.js`.
   - `app.js`: Interacts with the backend endpoints:
     - `POST /api/observations`
     - `GET /api/observations/{id}`
     - `POST /api/observations/{id}/correct`
     - `GET /api/observations`
