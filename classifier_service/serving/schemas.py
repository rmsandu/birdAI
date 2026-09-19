from typing import Optional

from pydantic import BaseModel


class SpeciesPrediction(BaseModel):
    species_name: str
    scientific_name: Optional[str] = None
    confidence: float


class PredictResponse(BaseModel):
    predictions: list[SpeciesPrediction]
    model_version: str
    backbone: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
