import json
from pathlib import Path

from google import genai

from birdai.config import EBIRD_LOOKBACK_DAYS, GEMINI_API_KEY, GEMINI_MODEL
from birdai.context import describe_season
from birdai.file_utils import DetectedFileType
from birdai.schemas import BirdAIResult, ObservationContext, ObservationEvidence


SYSTEM_PROMPT = """
You are BirdAI, a cautious bird perception assistant for wildlife observation.

Your task:
- analyze the uploaded image or audio recording
- suggest the most likely bird species using the observation context
- return up to three likely species sorted by confidence descending
- if you are highly confident, you may return only one species
- use integer confidence_probability values from 0 to 100
- explain uncertainty, ecological plausibility, and the next best observation action

Important:
- Do not overclaim certainty.
- If quality is poor, say so in uncertainty_reasons.
- Return valid JSON only.
- Do not include markdown or prose outside the JSON object.
"""


def extract_response_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_attr = getattr(response, "text", None)
    if callable(text_attr):
        text_value = text_attr()
        if isinstance(text_value, str) and text_value.strip():
            return text_value.strip()
    elif isinstance(text_attr, str) and text_attr.strip():
        return text_attr.strip()

    raise ValueError("Gemini response did not contain any text output.")


def get_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=GEMINI_API_KEY)


def _build_media_content(
    detected_file: DetectedFileType,
    uploaded_file,
) -> dict:
    if detected_file.modality == "image":
        return {
            "type": "image",
            "uri": uploaded_file.uri,
            "mime_type": detected_file.mime_type,
        }

    if detected_file.modality == "audio":
        return {
            "type": "audio",
            "uri": uploaded_file.uri,
            "mime_type": detected_file.mime_type,
        }

    raise ValueError(f"Unsupported modality: {detected_file.modality}")


def _build_analysis_prompt(
    modality: str,
    observation_context: ObservationContext,
) -> str:
    coordinates = "unknown"
    if (
        observation_context.latitude is not None
        and observation_context.longitude is not None
    ):
        coordinates = (
            f"{observation_context.latitude:.5f}, "
            f"{observation_context.longitude:.5f}"
        )

    return f"""
Analyze this {modality} for bird species identification.

Observation context:
- date: {observation_context.observation_date.isoformat()}
- time: {observation_context.observation_time.isoformat()}
- timezone: {observation_context.timezone_name or "unknown"}
- location: {observation_context.location_text}
- coordinates: {coordinates}
- season: {describe_season(observation_context)}

Return JSON with this exact structure:
{{
  "likely_species": [
    {{
      "common_name": "...",
      "scientific_name": "...",
      "confidence_probability": 0,
      "reason": "..."
    }}
  ],
  "uncertainty": "low|medium|high",
  "uncertainty_reasons": ["..."],
  "ecological_plausibility": {{
    "location": "...",
    "season": "...",
    "plausibility": "low|medium|high",
    "reason": "..."
  }},
  "suggested_next_action": "..."
}}
"""


def parse_gemini_json(response_text: str) -> dict:
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini returned malformed JSON.") from exc


def normalize_birdai_result(
    payload: dict,
    *,
    observation_context: ObservationContext,
    modality: str,
) -> BirdAIResult:
    result = BirdAIResult.model_validate(
        {
            **payload,
            "observation_context": observation_context.model_dump(mode="json"),
            "modality": modality,
            "warnings": payload.get("warnings", []),
        }
    )

    if not result.likely_species:
        raise ValueError("Gemini returned no species candidates.")

    sorted_candidates = sorted(
        result.likely_species,
        key=lambda candidate: candidate.confidence_probability,
        reverse=True,
    )

    sorted_candidates = sorted_candidates[:3]

    return result.model_copy(update={"likely_species": sorted_candidates})


def analyze_file(
    file_path: str,
    *,
    detected_file: DetectedFileType,
    observation_context: ObservationContext,
) -> BirdAIResult:
    client = get_client()
    path = Path(file_path)
    uploaded_file = client.files.upload(file=path)
    media_content = _build_media_content(detected_file, uploaded_file)
    prompt = _build_analysis_prompt(detected_file.modality, observation_context)

    response = client.interactions.create(
        model=GEMINI_MODEL,
        input=[{"type": "text", "text": prompt}, media_content],
        system_instruction=SYSTEM_PROMPT,
        response_format={"type": "text", "mime_type": "application/json"},
        response_modalities=["text"],
    )

    payload = parse_gemini_json(extract_response_text(response))
    return normalize_birdai_result(
        payload,
        observation_context=observation_context,
        modality=detected_file.modality,
    )


def search_recent_web_evidence(
    *,
    common_name: str,
    scientific_name: str | None,
    observation_context: ObservationContext,
) -> ObservationEvidence:
    client = get_client()
    species_label = scientific_name or common_name

    prompt = f"""
Use Google Search grounding to summarize recent public-web evidence for {species_label}
near {observation_context.location_text}. Focus on the last {EBIRD_LOOKBACK_DAYS} days.

Return a short plain-text summary with no markdown.
"""

    response = client.interactions.create(
        model=GEMINI_MODEL,
        input=[{"type": "text", "text": prompt}],
        tools=[{"google_search": {}}],
        response_modalities=["text"],
    )

    return ObservationEvidence(
        source="google_search",
        recent_observation_count=0,
        lookback_days=EBIRD_LOOKBACK_DAYS,
        summary=extract_response_text(response),
    )
