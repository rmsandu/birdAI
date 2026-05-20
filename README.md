# BirdAI

BirdAI is a context-aware bird identification app for reviewing wildlife observations from photos and audio recordings.

It addresses a common gap in bird ID tools: a media file on its own is often not enough. Real observations depend on where and when they were captured, whether GPS metadata is available, and whether a suggested species is plausible for that place and season. BirdAI brings those pieces together so the result is more useful than a plain label.

## What it solves

Bird watchers, wildlife camera users, and field observers often need more than a top prediction. They need help answering questions like:

- What species is most likely in this photo or recording?
- How certain is that result?
- Does the candidate make sense for this location and season?
- What should I capture next to reduce uncertainty?

BirdAI is built to support that workflow by combining media analysis with observation context and recent-species evidence.

## What the app currently does

- Uploads bird images and audio recordings through a Gradio interface.
- Supports image files such as JPEG, PNG, WebP, and HEIC.
- Supports audio files such as WAV, MP3, FLAC, and OGG.
- Lets the user review or edit observation date, time, location text, latitude, and longitude before analysis.
- Extracts GPS coordinates from photo metadata when available.
- Geocodes location text and reverse-geocodes extracted coordinates.
- Sends the observation to Gemini and returns structured JSON output.
- Returns likely species candidates, uncertainty, ecological plausibility, and a suggested next observation action.
- Adds recent-species evidence using eBird when coordinates are available.
- Falls back to grounded web evidence when eBird enrichment is unavailable.
- Logs analyses to `data/observations.csv`.

## Output

The app returns structured JSON with:

- `likely_species`: ranked bird candidates.
- `uncertainty` and `uncertainty_reasons`: how confident the result is and what limits it.
- `ecological_plausibility`: whether the candidate fits the observation context.
- `suggested_next_action`: the most useful follow-up observation.
- `observation_context`, `modality`, and `warnings`: resolved context and runtime notes.

Example output:

```json
{
  "likely_species": [
    {
      "common_name": "European Robin",
      "scientific_name": "Erithacus rubecula",
      "confidence_probability": 78,
      "reason": "Small passerine with orange-red breast and robin-like proportions."
    }
  ],
  "uncertainty": "medium",
  "uncertainty_reasons": [
    "partial occlusion",
    "low resolution",
    "single frame only"
  ],
  "ecological_plausibility": {
    "location": "Zurich, Switzerland",
    "season": "Spring",
    "plausibility": "high",
    "reason": "This species is commonly observed in the area during this season."
  },
  "suggested_next_action": "Capture another frame from the side or confirm with audio."
}
```

## Current scope

- Image and audio analysis are supported in the current app.
- Results are context-aware and designed to support observation review, not just species ranking.
- Each run can be stored locally for later review and comparison.

## Running the app

```bash
python app.py
```
