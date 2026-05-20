import httpx

from birdai.context import resolve_observation_context
from birdai.ebird_client import EBirdClient, EBirdServiceError
from birdai.file_utils import detect_file_type
from birdai.gemini_client import analyze_file as analyze_file_with_gemini
from birdai.gemini_client import search_recent_web_evidence
from birdai.mock_analyzer import mock_analyze_file
from birdai.schemas import BirdAIResult, ObservationContext, SpeciesCandidate


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

        return candidate.model_copy(
            update={
                "common_name": common_name,
                "scientific_name": scientific_name or candidate.scientific_name,
                "evidence": evidence,
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

        return candidate.model_copy(update={"evidence": evidence}), warnings


def analyze_observation(
    file_path: str,
    observation_context: ObservationContext,
    *,
    use_mock: bool = False,
    http_client: httpx.Client | None = None,
    ebird_client: EBirdClient | None = None,
) -> BirdAIResult:
    detected_file = detect_file_type(file_path)

    if detected_file.modality == "unknown":
        raise ValueError(
            "Unsupported or unrecognized file content. Please upload a valid "
            "image or audio recording."
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
        enriched_candidates.append(enriched_candidate)
        all_warnings.extend(candidate_warnings)

    return result.model_copy(
        update={
            "observation_context": resolved_context,
            "likely_species": enriched_candidates,
            "warnings": all_warnings,
        }
    )
