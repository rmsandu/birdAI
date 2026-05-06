from pydantic import BaseModel, Field
from typing import List, Optional


class SpeciesCandidate(BaseModel):
    common_name: str
    scientific_name: Optional[str] = None
    likelihood: str = Field(description="low, medium, or high")
    reason: str


class EcologicalPlausibility(BaseModel):
    location: str
    season: str
    plausibility: str = Field(description="low, medium, or high")
    reason: str


class BirdAIResult(BaseModel):
    likely_species: List[SpeciesCandidate]
    uncertainty: str
    uncertainty_reasons: List[str]
    ecological_plausibility: EcologicalPlausibility
    suggested_next_action: str
    modality: str