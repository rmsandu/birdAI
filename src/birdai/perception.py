import uuid
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from birdai.audio_utils import inspect_audio_file
from birdai.classifier_client import (
    ClassifierServiceError,
    classify_image,
    normalize_classifier_result,
)
from birdai.config import CLASSIFIER_ENABLED
from birdai.context import resolve_observation_context
from birdai.ebird_client import EBirdClient, EBirdServiceError
from birdai.file_utils import DetectedFileType, detect_file_type
from birdai.gemini_client import analyze_file as analyze_file_with_gemini
from birdai.gemini_client import search_recent_web_evidence
from birdai.mock_analyzer import mock_analyze_file
from birdai.schemas import (
    AudioEvidence,
    BirdAIResult,
    CertaintyEstimate,
    ContextualEvidence,
    LocalClassifierResult,
    MerlinSuggestion,
    ObservationContext,
    ObservationRecord,
    SpeciesCandidate,
    VisualEvidence,
)


def _enrich_candidate_with_recent_observations(
    candidate: SpeciesCandidate,
    *,
    observation_context: ObservationContext,
    ebird_client: EBirdClient,
) -> tuple[SpeciesCandidate, list[str]]:
    warnings: list[str] = []

    if (
        observation_context.latitude is None
        or observation_context.longitude is None
    ):
        warnings.append(
            f"Skipping eBird enrichment for {candidate.common_name} because no "
            "coordinates were provided."
        )
        return candidate, warnings

    try:
        species_match = ebird_client.resolve_species_code(
            candidate.common_name,
            candidate.scientific_name,
        )

        if species_match is None:
            raise EBirdServiceError(
                f"Could not resolve eBird taxonomy for {candidate.common_name}."
            )

        species_code, common_name, scientific_name = species_match
        evidence = ebird_client.recent_observations_for_species(
            species_code,
            observation_context,
        )

        contextual = ContextualEvidence(
            source="ebird",
            recent_observation_count=evidence.recent_observation_count,
            lookback_days=evidence.lookback_days,
            summary=evidence.summary,
            species_code=species_code,
            last_observation_date=evidence.last_observation_date,
            regional_plausibility="high" if evidence.recent_observation_count > 0 else "unconfirmed",
            plausibility_reason=f"eBird reported {evidence.recent_observation_count} observations nearby.",
        )

        return candidate.model_copy(
            update={
                "common_name": common_name,
                "scientific_name": scientific_name or candidate.scientific_name,
                "evidence": evidence,
                "contextual_evidence": contextual,
            }
        ), warnings

    except EBirdServiceError as exc:
        warnings.append(
            f"eBird enrichment failed for {candidate.common_name}. "
            "Using a web-grounded fallback instead."
        )

        try:
            evidence = search_recent_web_evidence(
                common_name=candidate.common_name,
                scientific_name=candidate.scientific_name,
                observation_context=observation_context,
            )
            contextual = ContextualEvidence(
                source="google_search",
                summary=evidence.summary,
                regional_plausibility="unknown",
                plausibility_reason="Web search fallback used.",
            )
        except Exception as fallback_exc:  # pragma: no cover - safety net
            warnings.append(
                f"Fallback web search also failed for {candidate.common_name}: "
                f"{fallback_exc}"
            )
            evidence = candidate.evidence.model_copy(
                update={
                    "source": "none",
                    "summary": f"No recent-observation enrichment available. {exc}",
                }
            )
            contextual = None

        return candidate.model_copy(
            update={
                "evidence": evidence,
                "contextual_evidence": contextual,
            }
        ), warnings


def _add_local_classifier_signal(
    file_path: str,
    *,
    detected_file: DetectedFileType,
    classifier_client_fn=classify_image,
) -> tuple[LocalClassifierResult, list[str]]:
    warnings: list[str] = []

    if not CLASSIFIER_ENABLED or detected_file.modality != "image":
        return LocalClassifierResult(source="unavailable"), warnings

    try:
        payload = classifier_client_fn(file_path)
        return normalize_classifier_result(payload), warnings
    except ClassifierServiceError as exc:
        warnings.append(f"Local classifier unavailable: {exc}")
        return LocalClassifierResult(source="error", summary=str(exc)), warnings


def analyze_observation(
    file_path: str,
    observation_context: ObservationContext,
    *,
    use_mock: bool = False,
    http_client: httpx.Client | None = None,
    ebird_client: EBirdClient | None = None,
    classifier_client_fn=classify_image,
) -> BirdAIResult:
    detected_file = detect_file_type(file_path)

    if detected_file.modality == "unknown":
        raise ValueError(
            "Unsupported or unrecognized file content. Please upload a valid "
            "image, audio, or video recording."
        )

    resolved_context, context_warnings = resolve_observation_context(
        observation_context,
        file_path=file_path,
        detected_file=detected_file,
        http_client=http_client,
    )

    if use_mock:
        result = mock_analyze_file(
            file_path=file_path,
            modality=detected_file.modality,
            observation_context=resolved_context,
        )
    else:
        result = analyze_file_with_gemini(
            file_path=file_path,
            detected_file=detected_file,
            observation_context=resolved_context,
        )

    all_warnings = [*result.warnings, *context_warnings]

    client = ebird_client or EBirdClient(http_client=http_client)
    enriched_candidates = []

    for candidate in result.likely_species:
        enriched_candidate, candidate_warnings = _enrich_candidate_with_recent_observations(
            candidate,
            observation_context=resolved_context,
            ebird_client=client,
        )

        # Attach modality-specific evidence
        if detected_file.modality == "image":
            visual_ev = VisualEvidence(
                source="vlm",
                model_name="gemini-2.5-flash",
                raw_score=float(candidate.confidence_probability),
                reason=candidate.reason,
            )
            enriched_candidate = enriched_candidate.model_copy(update={"visual_evidence": visual_ev})
        elif detected_file.modality == "audio":
            audio_info = inspect_audio_file(file_path)
            audio_ev = AudioEvidence(
                source="audio_model",
                model_name="gemini-2.5-flash",
                duration_seconds=audio_info.get("duration_seconds"),
                sample_rate=audio_info.get("sample_rate"),
                channels=audio_info.get("channels"),
                raw_score=float(candidate.confidence_probability),
                reason=candidate.reason,
            )
            enriched_candidate = enriched_candidate.model_copy(update={"audio_evidence": audio_ev})
        elif detected_file.modality == "video":
            visual_ev = VisualEvidence(
                source="vlm_video",
                model_name="gemini-2.5-flash",
                raw_score=float(candidate.confidence_probability),
                reason=candidate.reason,
            )
            audio_ev = AudioEvidence(
                source="video_audio",
                model_name="gemini-2.5-flash",
                raw_score=float(candidate.confidence_probability),
                reason="Evaluated jointly from video clip visual frames and soundtrack.",
            )
            enriched_candidate = enriched_candidate.model_copy(
                update={"visual_evidence": visual_ev, "audio_evidence": audio_ev}
            )

        enriched_candidates.append(enriched_candidate)
        all_warnings.extend(candidate_warnings)

    local_classifier, classifier_warnings = _add_local_classifier_signal(
        file_path,
        detected_file=detected_file,
        classifier_client_fn=classifier_client_fn,
    )
    all_warnings.extend(classifier_warnings)

    return result.model_copy(
        update={
            "observation_context": resolved_context,
            "likely_species": enriched_candidates,
            "warnings": all_warnings,
            "local_classifier": local_classifier,
        }
    )


def analyze_multimodal_observation(
    *,
    image_path: Optional[str] = None,
    audio_path: Optional[str] = None,
    video_path: Optional[str] = None,
    observation_context: ObservationContext,
    merlin_suggestion: Optional[MerlinSuggestion] = None,
    use_mock: bool = False,
    http_client: httpx.Client | None = None,
    ebird_client: EBirdClient | None = None,
    classifier_client_fn=classify_image,
) -> ObservationRecord:
    if not image_path and not audio_path and not video_path:
        raise ValueError("At least one image, audio, or video file must be provided.")

    record_id = f"obs-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc)
    warnings: List[str] = []

    candidates_by_name: dict[str, SpeciesCandidate] = {}
    local_classifier = LocalClassifierResult()
    overall_uncertainty = "medium"
    uncertainty_reasons: List[str] = []
    suggested_next_action = ""

    resolved_context = observation_context

    # 1. Analyze Image if present
    if image_path:
        img_result = analyze_observation(
            image_path,
            resolved_context,
            use_mock=use_mock,
            http_client=http_client,
            ebird_client=ebird_client,
            classifier_client_fn=classifier_client_fn,
        )
        resolved_context = img_result.observation_context
        warnings.extend(img_result.warnings)
        local_classifier = img_result.local_classifier
        overall_uncertainty = img_result.uncertainty
        uncertainty_reasons.extend(img_result.uncertainty_reasons)
        suggested_next_action = img_result.suggested_next_action

        for cand in img_result.likely_species:
            candidates_by_name[cand.common_name.lower()] = cand

    # 2. Analyze Audio if present
    if audio_path:
        audio_info = inspect_audio_file(audio_path)
        audio_result = analyze_observation(
            audio_path,
            resolved_context,
            use_mock=use_mock,
            http_client=http_client,
            ebird_client=ebird_client,
            classifier_client_fn=classifier_client_fn,
        )
        if not image_path:
            resolved_context = audio_result.observation_context
            overall_uncertainty = audio_result.uncertainty
            uncertainty_reasons = audio_result.uncertainty_reasons
            suggested_next_action = audio_result.suggested_next_action
        warnings.extend(audio_result.warnings)

        for cand in audio_result.likely_species:
            name_key = cand.common_name.lower()
            audio_ev = AudioEvidence(
                source="audio_model",
                model_name="gemini-2.5-flash",
                duration_seconds=audio_info.get("duration_seconds"),
                sample_rate=audio_info.get("sample_rate"),
                channels=audio_info.get("channels"),
                merlin_suggestion=merlin_suggestion,
                raw_score=float(cand.confidence_probability),
                reason=cand.reason,
            )

            if name_key in candidates_by_name:
                # Merge into existing candidate from visual inspection
                existing = candidates_by_name[name_key]
                merged = existing.model_copy(
                    update={
                        "audio_evidence": audio_ev,
                        "confidence_probability": max(
                            existing.confidence_probability,
                            cand.confidence_probability,
                        ),
                        "certainty": CertaintyEstimate(
                            score=max(existing.confidence_probability, cand.confidence_probability),
                            is_calibrated=False,
                            uncertainty_level="low" if (existing.confidence_probability >= 70 and cand.confidence_probability >= 70) else "medium",
                            uncertainty_reasons=uncertainty_reasons,
                            score_meaning="Multimodal heuristic score; uncalibrated.",
                        ),
                    }
                )
                candidates_by_name[name_key] = merged
            else:
                cand = cand.model_copy(update={"audio_evidence": audio_ev})
                candidates_by_name[name_key] = cand

    # 2b. Analyze Video if present
    if video_path:
        vid_result = analyze_observation(
            video_path,
            resolved_context,
            use_mock=use_mock,
            http_client=http_client,
            ebird_client=ebird_client,
            classifier_client_fn=classifier_client_fn,
        )
        if not image_path and not audio_path:
            resolved_context = vid_result.observation_context
            overall_uncertainty = vid_result.uncertainty
            uncertainty_reasons = vid_result.uncertainty_reasons
            suggested_next_action = vid_result.suggested_next_action
        else:
            uncertainty_reasons.extend(vid_result.uncertainty_reasons)
        warnings.extend(vid_result.warnings)

        for cand in vid_result.likely_species:
            name_key = cand.common_name.lower()
            if name_key in candidates_by_name:
                existing = candidates_by_name[name_key]
                merged_score = max(existing.confidence_probability, cand.confidence_probability)
                candidates_by_name[name_key] = existing.model_copy(
                    update={
                        "visual_evidence": existing.visual_evidence or cand.visual_evidence,
                        "audio_evidence": existing.audio_evidence or cand.audio_evidence,
                        "confidence_probability": merged_score,
                    }
                )
            else:
                candidates_by_name[name_key] = cand

    # 3. Add Merlin suggestion as an explicitly unverified candidate if not present
    if merlin_suggestion and merlin_suggestion.species_name:
        merlin_key = merlin_suggestion.species_name.strip().lower()
        if merlin_key in candidates_by_name:
            cand = candidates_by_name[merlin_key]
            if cand.audio_evidence:
                cand.audio_evidence.merlin_suggestion = merlin_suggestion
        else:
            # Add as additional candidate explicitly flagged as unverified external input
            merlin_cand = SpeciesCandidate(
                common_name=merlin_suggestion.species_name,
                scientific_name=merlin_suggestion.scientific_name,
                confidence_probability=50,
                reason=f"Suggested by Merlin Bird ID (unverified external candidate): {merlin_suggestion.notes or 'No audio notes provided.'}",
                certainty=CertaintyEstimate(
                    score=50,
                    is_calibrated=False,
                    uncertainty_level="medium",
                    uncertainty_reasons=["External uncalibrated user input from Merlin Bird ID"],
                    score_meaning="Candidate imported from Merlin; uncalibrated external suggestion.",
                ),
                audio_evidence=AudioEvidence(
                    source="merlin_import",
                    model_name="merlin",
                    merlin_suggestion=merlin_suggestion,
                    raw_score=50.0,
                    reason=merlin_suggestion.notes or "Imported from Merlin Bird ID.",
                ),
            )
            candidates_by_name[merlin_key] = merlin_cand

    # Sort final candidates by confidence descending
    final_candidates = sorted(
        candidates_by_name.values(),
        key=lambda c: c.confidence_probability,
        reverse=True,
    )

    active_modalities = [m for m, p in (("image", image_path), ("audio", audio_path), ("video", video_path)) if p]
    if len(active_modalities) > 1:
        modality = "multimodal"
    elif active_modalities:
        modality = active_modalities[0]
    else:
        modality = "unknown"

    return ObservationRecord(
        id=record_id,
        created_at=created_at,
        modality=modality,
        image_path=image_path,
        audio_path=audio_path,
        video_path=video_path,
        observation_context=resolved_context,
        merlin_suggestion=merlin_suggestion,
        candidates=final_candidates,
        overall_uncertainty=overall_uncertainty if overall_uncertainty in ["low", "medium", "high", "unknown"] else "medium",
        overall_uncertainty_reasons=list(dict.fromkeys(uncertainty_reasons)),
        suggested_next_action=suggested_next_action or "Capture additional media to verify.",
        warnings=list(dict.fromkeys(warnings)),
        local_classifier=local_classifier,
    )
