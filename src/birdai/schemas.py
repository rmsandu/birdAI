from datetime import date, datetime, time, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ObservationContext(BaseModel):
    observation_date: date
    observation_time: time
    location_text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_source: str = "user_input"
    timezone_name: Optional[str] = None


class MerlinSuggestion(BaseModel):
    species_name: str
    scientific_name: Optional[str] = None
    notes: Optional[str] = None
    source: str = "merlin_user_input"
    is_verified_ground_truth: bool = False


class VisualEvidence(BaseModel):
    source: str = "vlm"
    model_name: str = "gemini-2.5-flash"
    raw_score: Optional[float] = None
    reason: str = ""
    visual_features: List[str] = Field(default_factory=list)


class AudioEvidence(BaseModel):
    source: str = "audio_model"
    model_name: str = "gemini-2.5-flash"
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    merlin_suggestion: Optional[MerlinSuggestion] = None
    raw_score: Optional[float] = None
    reason: str = ""


class ContextualEvidence(BaseModel):
    source: str = "ebird"
    recent_observation_count: int = 0
    lookback_days: int = 30
    summary: str = ""
    species_code: Optional[str] = None
    last_observation_date: Optional[str] = None
    regional_plausibility: str = "unknown"
    plausibility_reason: str = ""


class CertaintyEstimate(BaseModel):
    score: int = Field(ge=0, le=100, description="Raw model confidence heuristic (0-100)")
    is_calibrated: bool = Field(default=False, description="Whether this score is statistically calibrated")
    uncertainty_level: Literal["low", "medium", "high", "unknown"] = "medium"
    uncertainty_reasons: List[str] = Field(default_factory=list)
    score_meaning: str = Field(
        default="Heuristic model score; not an empirical probability. Uncalibrated."
    )


class ObservationEvidence(BaseModel):
    source: str = "none"
    recent_observation_count: int = 0
    lookback_days: int = 30
    summary: str = ""
    species_code: Optional[str] = None
    last_observation_date: Optional[str] = None


class SpeciesCandidate(BaseModel):
    common_name: str
    scientific_name: Optional[str] = None
    confidence_probability: int = Field(ge=0, le=100)
    reason: str = ""
    evidence: ObservationEvidence = Field(default_factory=ObservationEvidence)
    certainty: Optional[CertaintyEstimate] = None
    visual_evidence: Optional[VisualEvidence] = None
    audio_evidence: Optional[AudioEvidence] = None
    contextual_evidence: Optional[ContextualEvidence] = None

    def model_post_init(self, __context) -> None:
        if self.certainty is None:
            self.certainty = CertaintyEstimate(
                score=self.confidence_probability,
                is_calibrated=False,
                uncertainty_level="low" if self.confidence_probability >= 80 else ("medium" if self.confidence_probability >= 40 else "high"),
                uncertainty_reasons=[],
                score_meaning="Heuristic model score; uncalibrated.",
            )


class EcologicalPlausibility(BaseModel):
    location: str
    season: str
    plausibility: str = Field(description="low, medium, or high")
    reason: str


class LocalClassifierPrediction(BaseModel):
    species_name: str
    scientific_name: Optional[str] = None
    confidence_probability: int = Field(ge=0, le=100)


class LocalClassifierResult(BaseModel):
    source: str = "none"
    model_version: Optional[str] = None
    predictions: List[LocalClassifierPrediction] = Field(default_factory=list)
    summary: str = ""


class BirdAIResult(BaseModel):
    observation_context: ObservationContext
    likely_species: List[SpeciesCandidate]
    uncertainty: str
    uncertainty_reasons: List[str]
    ecological_plausibility: EcologicalPlausibility
    suggested_next_action: str
    modality: str
    warnings: List[str] = Field(default_factory=list)
    local_classifier: LocalClassifierResult = Field(default_factory=LocalClassifierResult)


class ObservationCorrection(BaseModel):
    confirmed_species: str
    scientific_name: Optional[str] = None
    is_correct_prediction: bool = True
    correction_notes: Optional[str] = None
    reviewer: str = "user"
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ObservationRecord(BaseModel):
    id: str
    created_at: datetime
    modality: Literal["image", "audio", "multimodal", "unknown"] = "image"
    image_path: Optional[str] = None
    audio_path: Optional[str] = None
    observation_context: ObservationContext
    merlin_suggestion: Optional[MerlinSuggestion] = None
    candidates: List[SpeciesCandidate] = Field(default_factory=list)
    overall_uncertainty: Literal["low", "medium", "high", "unknown"] = "medium"
    overall_uncertainty_reasons: List[str] = Field(default_factory=list)
    suggested_next_action: str = ""
    user_correction: Optional[ObservationCorrection] = None
    warnings: List[str] = Field(default_factory=list)
    local_classifier: LocalClassifierResult = Field(default_factory=LocalClassifierResult)


class SightingItem(BaseModel):
    species_common_name: str
    species_scientific_name: Optional[str] = None
    count: Optional[int] = 1
    observed_at: str
    location_name: str
    latitude: float
    longitude: float
    distance_km: float
    source: Literal["ebird", "ornitho.ch"]
    checklist_url: Optional[str] = None
    notable: bool = False


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    sightings: Optional[List[SightingItem]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    user_latitude: Optional[float] = None
    user_longitude: Optional[float] = None
    preferred_radius_km: Optional[int] = 15


class ChatResponse(BaseModel):
    reply: str
    sightings: List[SightingItem] = Field(default_factory=list)
    parsed_query: dict = Field(default_factory=dict)
    # "ai": Gemini understood the question; "rule_based": keyword-matching fallback
    mode: Literal["ai", "rule_based"] = "ai"
    # Source name -> why it couldn't be queried (results may be incomplete)
    unavailable_sources: Dict[str, str] = Field(default_factory=dict)


class SightingsResponse(BaseModel):
    sightings: List[SightingItem] = Field(default_factory=list)
    unavailable_sources: Dict[str, str] = Field(default_factory=dict)
