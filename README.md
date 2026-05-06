# BirdAI

## Overview

This project explores **active perception for wildlife monitoring**: how an embodied visual agent can combine visual, audio, temporal, and ecological context to make more reliable predictions and decisions under uncertainty.

## BirdAI MVP v0.1

**Goal:** Input upload bird image/audio/video → get likely species, uncertainty, ecological plausibility, and next observation action.

### Features

- **Gradio app** with drag-and-drop upload interface
- **Multi-modal support:**
  - Image upload (Sony/phone/Birdfy screenshots)
  - Audio upload (Merlin recordings)
  - Video upload (Birdfy videos, coming soon)
- **Gemini-based inference** returning structured JSON
- **Local observations.csv** log for tracking observations

example output JSON:

{
"likely_species": [
{
"common_name": "European Robin",
"scientific_name": "Erithacus rubecula",
"likelihood": "medium",
"reason": "Small passerine with orange-red breast visible..."
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
"season": "May",
"plausibility": "high",
"reason": "Common resident species in Switzerland"
},
"suggested_next_action": "Capture another frame from the side or confirm with audio."
}

TO BE DONE: Active Bird Observer The system decides: Is there a bird in the frame? Which crop/region should the agent focus on? Is the classification uncertain? Should it request another frame, another angle, or audio confirmation? Is this species plausible in Zurich/Switzerland in this season?
