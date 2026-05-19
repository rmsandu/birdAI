from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, Field


class ObservationContext(BaseModel):
    observation_date: date
    observation_time: time
    location_text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_source: str = "user_input"
    timezone_name: Optional[str] = None


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
    reason: str
    evidence: ObservationEvidence = Field(default_factory=ObservationEvidence)


class EcologicalPlausibility(BaseModel):
    location: str
    season: str
    plausibility: str = Field(description="low, medium, or high")
    reason: str


class BirdAIResult(BaseModel):
    observation_context: ObservationContext
    likely_species: List[SpeciesCandidate]
    uncertainty: str
    uncertainty_reasons: List[str]
    ecological_plausibility: EcologicalPlausibility
    suggested_next_action: str
    modality: str
    warnings: List[str] = Field(default_factory=list)
