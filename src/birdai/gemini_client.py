import json
from pathlib import Path
from google import genai
from google.genai import types

from birdai.config import GEMINI_API_KEY, BIRDAI_LOCATION


client = genai.Client(api_key=GEMINI_API_KEY)


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

    prompt = f"""
    Analyze this {modality} for bird species identification.

    Location: {BIRDAI_LOCATION}
    Current season/month: May

    Be cautious. Merlin/BirdNET and visual classifiers can make mistakes.
    Focus on uncertainty, plausible alternatives, and next observation action.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            SYSTEM_PROMPT,
            prompt,
            uploaded_file,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    text = response.text.strip()
    return json.loads(text)