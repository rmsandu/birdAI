import inspect
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from birdai.auth.dependencies import get_current_active_user, get_current_user
from birdai.context import build_observation_context, reverse_geocode_coordinates
from birdai.db.models import UserModel
from birdai.db.session import get_db
from birdai.db.sql_store import SQLObservationStore
from birdai.perception import analyze_multimodal_observation
from birdai.photo_metadata import extract_photo_coordinates
from birdai.schemas import (
    ChatRequest,
    ChatResponse,
    MerlinSuggestion,
    ObservationCorrection,
    ObservationRecord,
    SightingsResponse,
)
from birdai.chat_agent import BirdChatAgent

router = APIRouter(tags=["observations"])

# Data directory can be configured via environment variable
DATA_DIR = os.getenv("BIRDAI_DATA_DIR", "data")

# Global store fallback (allows monkeypatching in unit tests)
store = None


def get_store(db: Session = Depends(get_db)):
    if store is not None:
        return store
    return SQLObservationStore(db=db, base_dir=DATA_DIR)


@router.post("/extract-metadata")
async def extract_metadata(file: UploadFile):
    """Extract photo coordinates and reverse geocode location from uploaded image metadata."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    file_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as temp_f:
        temp_f.write(file_bytes)
        temp_path = temp_f.name

    try:
        # --- EXIF datetime ---
        observation_date: Optional[str] = None
        observation_time: Optional[str] = None
        try:
            from PIL import Image as PILImage
            img = PILImage.open(temp_path)
            exif_raw = img._getexif() if hasattr(img, "_getexif") else None
            if exif_raw:
                # Tag 36867 = DateTimeOriginal, format "YYYY:MM:DD HH:MM:SS"
                dt_str = exif_raw.get(36867) or exif_raw.get(306)  # 306 = DateTime
                if dt_str and ":" in dt_str:
                    parts = dt_str.strip().split(" ")
                    if len(parts) == 2:
                        date_part = parts[0].replace(":", "-")  # YYYY-MM-DD
                        time_part = parts[1]  # HH:MM:SS
                        observation_date = date_part
                        observation_time = time_part
        except Exception:
            pass

        # --- GPS coords ---
        coords = extract_photo_coordinates(temp_path)
        if coords is None:
            return {
                "has_gps": False,
                "latitude": None,
                "longitude": None,
                "location_text": None,
                "observation_date": observation_date,
                "observation_time": observation_time,
                "status": "No GPS metadata found in photo." + (
                    " Date/time extracted from EXIF." if observation_date else ""
                ),
            }

        latitude, longitude = coords
        location_name = None
        try:
            location_name = reverse_geocode_coordinates(latitude, longitude)
        except Exception:
            location_name = f"GPS: {latitude:.4f}, {longitude:.4f}"

        return {
            "has_gps": True,
            "latitude": round(latitude, 5),
            "longitude": round(longitude, 5),
            "location_text": location_name or f"GPS: {latitude:.4f}, {longitude:.4f}",
            "observation_date": observation_date,
            "observation_time": observation_time,
            "status": "✓ GPS coordinates extracted from photo metadata.",
        }
    finally:
        if Path(temp_path).exists():
            try:
                Path(temp_path).unlink()
            except Exception:
                pass


@router.post("/observations", response_model=ObservationRecord)
async def create_observation(
    image: Optional[UploadFile] = None,
    audio: Optional[UploadFile] = None,
    location_text: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    observation_date: Optional[str] = Form(None),
    observation_time: Optional[str] = Form(None),
    merlin_species: Optional[str] = Form(None),
    merlin_notes: Optional[str] = Form(None),
    use_mock: bool = Form(False),
    current_user: UserModel = Depends(get_current_active_user),
    obs_store=Depends(get_store),
) -> ObservationRecord:
    """Submit a bird observation with image, audio, or both."""
    if not image and not audio:
        raise HTTPException(
            status_code=400,
            detail="At least one image or audio file must be uploaded.",
        )

    saved_files: dict[str, bytes] = {}
    temp_image_path: Optional[str] = None
    temp_audio_path: Optional[str] = None

    try:
        if image and image.filename:
            image_bytes = await image.read()
            saved_files[image.filename] = image_bytes
            with tempfile.NamedTemporaryFile(
                suffix=Path(image.filename).suffix,
                delete=False,
            ) as temp_img:
                temp_img.write(image_bytes)
                temp_image_path = temp_img.name

        if audio and audio.filename:
            audio_bytes = await audio.read()
            saved_files[audio.filename] = audio_bytes
            with tempfile.NamedTemporaryFile(
                suffix=Path(audio.filename).suffix,
                delete=False,
            ) as temp_aud:
                temp_aud.write(audio_bytes)
                temp_audio_path = temp_aud.name

        context = build_observation_context(
            observation_date=observation_date,
            observation_time=observation_time,
            location_text=location_text,
            latitude=latitude,
            longitude=longitude,
        )

        merlin = None
        if merlin_species and merlin_species.strip():
            merlin = MerlinSuggestion(
                species_name=merlin_species.strip(),
                notes=merlin_notes.strip() if merlin_notes else None,
            )

        record = analyze_multimodal_observation(
            image_path=temp_image_path,
            audio_path=temp_audio_path,
            observation_context=context,
            merlin_suggestion=merlin,
            use_mock=use_mock,
        )

        # Update media paths in record to point to permanent stored paths
        rel_img = f"/api/media/{record.id}/{image.filename}" if (image and image.filename) else None
        rel_aud = f"/api/media/{record.id}/{audio.filename}" if (audio and audio.filename) else None
        record = record.model_copy(update={"image_path": rel_img, "audio_path": rel_aud})

        # Save to store with user_id scoping
        sig = inspect.signature(obs_store.save)
        if "user_id" in sig.parameters:
            obs_store.save(record, user_id=current_user.id, files=saved_files)
        else:
            obs_store.save(record, files=saved_files)
        return record

    finally:
        if temp_image_path and Path(temp_image_path).exists():
            try:
                Path(temp_image_path).unlink()
            except Exception:
                pass
        if temp_audio_path and Path(temp_audio_path).exists():
            try:
                Path(temp_audio_path).unlink()
            except Exception:
                pass


@router.get("/observations/{observation_id}", response_model=ObservationRecord)
def get_observation(
    observation_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    obs_store=Depends(get_store),
) -> ObservationRecord:
    """Retrieve an observation by ID with its evidence breakdown and status."""
    sig = inspect.signature(obs_store.get)
    if "user_id" in sig.parameters:
        record = obs_store.get(observation_id, user_id=current_user.id)
    else:
        record = obs_store.get(observation_id)

    if not record:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return record


@router.post("/observations/{observation_id}/correct", response_model=ObservationRecord)
def correct_observation(
    observation_id: str,
    correction: ObservationCorrection,
    current_user: UserModel = Depends(get_current_active_user),
    obs_store=Depends(get_store),
) -> ObservationRecord:
    """Submit a human verification or species correction for an observation."""
    sig = inspect.signature(obs_store.update_correction)
    if "user_id" in sig.parameters:
        updated = obs_store.update_correction(
            observation_id, correction, user_id=current_user.id
        )
    else:
        updated = obs_store.update_correction(observation_id, correction)

    if not updated:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return updated


@router.get("/observations", response_model=List[ObservationRecord])
def list_observations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    reviewed_only: Optional[bool] = Query(None),
    current_user: UserModel = Depends(get_current_active_user),
    obs_store=Depends(get_store),
) -> List[ObservationRecord]:
    """List saved observations with pagination and optional review status filtering."""
    sig = inspect.signature(obs_store.list)
    if "user_id" in sig.parameters:
        return obs_store.list(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            reviewed_only=reviewed_only,
        )
    return obs_store.list(limit=limit, offset=offset, reviewed_only=reviewed_only)


@router.get("/media/{observation_id}/{filename}")
def get_observation_media(
    observation_id: str,
    filename: str,
    current_user: Optional[UserModel] = Depends(get_current_user),
    obs_store=Depends(get_store),
):
    """Serve uploaded observation media file (requires observation ownership)."""
    user_id = current_user.id if current_user else None
    sig = inspect.signature(obs_store.get_media_path)
    if "user_id" in sig.parameters:
        path = obs_store.get_media_path(
            observation_id, filename, user_id=user_id
        )
    else:
        path = obs_store.get_media_path(observation_id, filename)

    if not path:
        raise HTTPException(status_code=404, detail="Media file not found.")
    return FileResponse(path)


# Shared chat agent (and its sightings aggregator) reused across requests
chat_agent = BirdChatAgent()


@router.post("/chat", response_model=ChatResponse)
def chat_sightings(
    request: ChatRequest,
    current_user: UserModel = Depends(get_current_active_user),
) -> ChatResponse:
    """Natural language bird sightings assistant powered by eBird and ornitho.ch."""
    return chat_agent.process_query(
        message=request.message,
        conversation_history=request.conversation_history,
        user_lat=request.user_latitude,
        user_lng=request.user_longitude,
        preferred_radius_km=request.preferred_radius_km or 15,
    )


@router.get("/sightings", response_model=SightingsResponse)
def get_recent_sightings(
    location: Optional[str] = Query(None, description="City or landmark name"),
    radius_km: int = Query(15, ge=1, le=50, description="Radius in km (5, 15, 25)"),
    species: Optional[str] = Query(None, description="Species common or scientific name"),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    current_user: UserModel = Depends(get_current_active_user),
) -> SightingsResponse:
    """Direct REST query for recent sightings from eBird and ornitho.ch.

    ``unavailable_sources`` lists any source that failed, so an empty list of sightings
    can be told apart from "couldn't check".
    """
    sightings, metadata = chat_agent.aggregator.search_sightings(
        location_name=location,
        radius_km=radius_km,
        species_name=species,
        user_lat=lat,
        user_lng=lng,
    )
    return SightingsResponse(
        sightings=sightings,
        unavailable_sources=metadata.get("unavailable_sources", {}),
    )
