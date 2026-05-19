import datetime
import json
import mimetypes
from pathlib import Path
from google import genai

from birdai.config import GEMINI_API_KEY, BIRDAI_LOCATION


client = genai.Client(api_key=GEMINI_API_KEY)


def _build_media_content(modality: str, uploaded_file, path: Path) -> dict:
    mime_type = uploaded_file.mime_type or mimetypes.guess_type(path)[0]

    if modality == "image":
        return {
            "type": "image",
            "uri": uploaded_file.uri,
            "mime_type": mime_type or "image/jpeg",
        }
    if modality == "audio":
        return {
            "type": "audio",
            "uri": uploaded_file.uri,
            "mime_type": mime_type or "audio/mpeg",
        }
    if modality == "video":
        return {
            "type": "video",
            "uri": uploaded_file.uri,
            "mime_type": mime_type or "video/mp4",
        }

    raise ValueError(f"Unsupported modality: {modality}")


SYSTEM_PROMPT = """
You are BirdAI, a cautious bird perception assistant for an embodied wildlife-observation agent.

Your task:
- analyze the uploaded image or audio recording
- identify likely bird species
- explain uncertainty
- check ecological plausibility for the location and season
- suggest the next perception action an embodied observer should take

Important:
- Do not overclaim certainty.
- If image or audio quality is poor, say so.
- Return valid JSON only.
- Use this JSON structure:

{
  "likely_species": [
    {
      "common_name": "...",
      "scientific_name": "...",
      "likelihood": "low|medium|high",
      "reason": "..."
    }
  ],
  "uncertainty": "low|medium|high",
  "uncertainty_reasons": ["..."],
  "ecological_plausibility": {
    "location": "...",
    "season": "...",
    "plausibility": "low|medium|high",
    "reason": "..."
  },
  "suggested_next_action": "...",
  "modality": "image|audio|video"
}
"""


def analyze_file(file_path: str, modality: str) -> dict:
    path = Path(file_path)

    uploaded_file = client.files.upload(file=path)

    current_month = datetime.datetime.now().strftime("%B")

    prompt = f"""
    Analyze this {modality} for bird species identification.

    Location: {BIRDAI_LOCATION}
    Current season/month: {current_month}

    Focus on uncertainty, plausible alternatives, and next observation action.
    """

    media_content = _build_media_content(modality, uploaded_file, path)

    response = client.interactions.create(
        model="gemini-2.5-flash",
        input=[{"type": "text", "text": prompt}, media_content],
        system_instruction=SYSTEM_PROMPT,
        response_format={"type": "text", "mime_type": "application/json"},
        response_modalities=["text"],
    )

    text = response.text().strip()
    return json.loads(text)