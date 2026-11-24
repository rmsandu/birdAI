import logging
import re
from typing import Optional

from google.genai import types

from birdai.config import GEMINI_API_KEY
from birdai.gemini_client import (
    extract_response_text,
    generate_content_with_fallback,
    get_client,
)
from birdai.schemas import ChatMessage, ChatResponse
from birdai.sightings_aggregator import (
    SOURCE_LABELS,
    SightingsAggregator,
    describe_unavailable_sources,
)

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are BirdAI Assistant, an expert naturalist and birdwatching guide.
You help birdwatchers discover recent bird sightings in Switzerland and worldwide using verified real-time data.

When the user asks about bird sightings, species in a region, or a specific bird:
1. Call the `search_bird_sightings` tool with the extracted location, distance radius (5, 15, or 25 km), and optional species name.
2. If the user didn't specify a radius, use 15 km (or the user's preferred radius).
3. If the user didn't specify a location, leave location empty to use their GPS coordinates.
4. When synthesizing your final response:
   - Provide a warm, knowledgeable naturalist summary.
   - Mention key details: species names (common and scientific), how many individuals, dates, distances, and locations.
   - Explicitly cite the source platform for each record (e.g. "[eBird]").
   - Give practical birdwatching advice on the habitat (e.g. reedbeds for bitterns, fast streams for dippers).
5. If the tool result lists `unavailable_sources`, the user is already shown a notice about it, so don't repeat it.
   Never imply that a species is absent from a source that could not be queried.
"""


def _build_sightings_tool() -> types.Tool:
    fn = types.FunctionDeclaration(
        name="search_bird_sightings",
        description=(
            "Search recent bird sightings within 5 km, 15 km, or 25 km of a location "
            "using live eBird data."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "location": {
                    "type": "STRING",
                    "description": "City, town, lake, or landmark name (e.g. 'Zurich', 'Bern', 'Neeracherried'). Leave empty if using current GPS.",
                },
                "radius_km": {
                    "type": "INTEGER",
                    "description": "Search radius in kilometers: 5, 15, or 25. Default is 15.",
                },
                "species_name": {
                    "type": "STRING",
                    "description": "Optional common or scientific name of a specific bird to search for (e.g. 'Kingfisher', 'Red Kite').",
                },
                "back_days": {
                    "type": "INTEGER",
                    "description": "Number of lookback days (1 to 30, default 7).",
                },
            },
        },
    )
    return types.Tool(function_declarations=[fn])


def _extract_heuristics_from_prompt(
    prompt: str,
    default_radius: int = 15,
) -> tuple[Optional[str], int, Optional[str]]:
    """Heuristic parameter extractor for offline or fallback operation."""
    lowered = prompt.lower()

    # Radius extraction (5, 15, 25 km)
    radius = default_radius
    if re.search(r"\b5\s*km\b", lowered):
        radius = 5
    elif re.search(r"\b25\s*km\b", lowered):
        radius = 25
    elif re.search(r"\b15\s*km\b", lowered):
        radius = 15

    # Location extraction
    location: Optional[str] = None
    swiss_places = [
        "neeracherried", "klingnau", "klingnauer stausee", "greifensee", "zürichsee",
        "zurich", "zürich", "bern", "geneva", "genève", "genf", "basel", "lucerne",
        "luzern", "lausanne", "st. gallen", "fanel", "flachsee", "lugano",
    ]
    for place in swiss_places:
        if place in lowered:
            location = place.title()
            break

    # Species extraction
    known_birds = [
        "kingfisher", "eisvogel", "red kite", "rotmilan", "great bittern", "rohrdommel",
        "dipper", "wasseramsel", "smew", "zwergsäger", "wallcreeper", "mauerläufer",
        "robin", "rotkehlchen", "blue tit", "blaumeise", "great tit", "kohlmeise",
        "chaffinch", "buchfink", "red-crested pochard", "kolbenente",
    ]
    species: Optional[str] = None
    for bird in known_birds:
        if bird in lowered:
            species = bird.title()
            break

    return location, radius, species


_GEMINI_ROLES = {"user": "user", "assistant": "model"}

RULE_BASED_NOTICE = (
    "**Basic search mode:** the AI assistant {reason}, so I matched keywords in your "
    "message instead. I only recognise some Swiss place names and common bird names, "
    "radii of 5, 15 or 25 km, and I don't remember earlier messages."
)


def _with_notices(body: str, *notices: Optional[str]) -> str:
    return "\n\n".join(part for part in [*notices, body] if part)


def _history_to_contents(history: Optional[list[ChatMessage]]) -> list[types.Content]:
    """Convert prior chat turns into Gemini contents (system messages are skipped)."""
    contents: list[types.Content] = []
    for msg in history or []:
        role = _GEMINI_ROLES.get(msg.role)
        if role is None or not msg.content.strip():
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))
    return contents


class BirdChatAgent:
    def __init__(
        self,
        aggregator: Optional[SightingsAggregator] = None,
    ):
        self.aggregator = aggregator or SightingsAggregator()

    def process_query(
        self,
        message: str,
        conversation_history: Optional[list[ChatMessage]] = None,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
        preferred_radius_km: int = 15,
    ) -> ChatResponse:
        """Process a natural language query with Gemini function calling and sightings aggregation."""
        # Check if Gemini API is configured
        if not GEMINI_API_KEY:
            return self._fallback_process(
                message=message,
                user_lat=user_lat,
                user_lng=user_lng,
                preferred_radius_km=preferred_radius_km,
                ai_unavailable_reason="is not configured",
            )

        try:
            client = get_client()
            tool = _build_sightings_tool()

            contents = _history_to_contents(conversation_history)
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                f"User GPS coordinates available: lat={user_lat}, lng={user_lng}\n"
                                f"Preferred default radius: {preferred_radius_km} km\n\n"
                                f"User request: {message}"
                            )
                        )
                    ],
                )
            )

            # 1. First turn: let Gemini decide whether to call the search tool
            response = generate_content_with_fallback(
                client,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=CHAT_SYSTEM_PROMPT,
                    tools=[tool],
                ),
            )

            function_calls = response.function_calls or []
            if not function_calls:
                return ChatResponse(
                    reply=extract_response_text(response),
                    sightings=[],
                    parsed_query={"location_name": "unknown", "radius_km": preferred_radius_km},
                )

            fn_call = function_calls[0]
            args = dict(fn_call.args or {})
            species = args.get("species_name") or None
            sightings, metadata = self.aggregator.search_sightings(
                location_name=args.get("location") or None,
                radius_km=int(args.get("radius_km") or preferred_radius_km),
                species_name=species,
                back_days=int(args.get("back_days") or 7),
                user_lat=user_lat,
                user_lng=user_lng,
            )

            unavailable = metadata.get("unavailable_sources", {})
            sources = self.aggregator.sources
            source_notice = describe_unavailable_sources(unavailable, sources)

            # Every source failed: there is nothing for Gemini to summarise
            if set(unavailable) >= set(sources):
                return ChatResponse(
                    reply=source_notice,
                    sightings=[],
                    parsed_query=metadata,
                    mode="ai",
                    unavailable_sources=unavailable,
                )

            # 2. Second turn: return the tool result to Gemini for a natural-language answer
            contents.append(response.candidates[0].content)
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=fn_call.name,
                            response={
                                "query": metadata,
                                "total_sightings": len(sightings),
                                "unavailable_sources": unavailable,
                                "sightings": [s.model_dump(mode="json") for s in sightings[:20]],
                            },
                        )
                    ],
                )
            )
            synthesis_response = generate_content_with_fallback(
                client,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=CHAT_SYSTEM_PROMPT,
                    tools=[tool],
                ),
            )

            return ChatResponse(
                reply=_with_notices(extract_response_text(synthesis_response), source_notice),
                sightings=sightings,
                parsed_query=metadata,
                mode="ai",
                unavailable_sources=unavailable,
            )

        except Exception as exc:
            logger.warning("Gemini chat processing encountered error (%s); using fallback.", exc)
            return self._fallback_process(
                message=message,
                user_lat=user_lat,
                user_lng=user_lng,
                preferred_radius_km=preferred_radius_km,
                ai_unavailable_reason="could not be reached",
            )

    def _fallback_process(
        self,
        message: str,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
        preferred_radius_km: int = 15,
        ai_unavailable_reason: str = "is unavailable",
    ) -> ChatResponse:
        """Rule-based natural language response generator."""
        loc, radius, species = _extract_heuristics_from_prompt(
            message, default_radius=preferred_radius_km
        )
        sightings, metadata = self.aggregator.search_sightings(
            location_name=loc,
            radius_km=radius,
            species_name=species,
            user_lat=user_lat,
            user_lng=user_lng,
        )

        loc_label = metadata["location_name"]
        rad_label = metadata["radius_km"]
        unavailable = metadata.get("unavailable_sources", {})
        queried = metadata.get("sources_queried", self.aggregator.sources)
        source_notice = describe_unavailable_sources(unavailable, queried)
        checked = " and ".join(SOURCE_LABELS[src] for src in queried if src not in unavailable)

        if not sightings and not checked:
            body = ""  # the source notice already explains that nothing could be checked
        elif not sightings:
            body = (
                f"I searched recent sightings within **{rad_label} km** of **{loc_label}** on {checked}, "
                f"but found no matching records in the last 7 days. "
                f"Try expanding your radius to 25 km or searching for a nearby wetland or forest hotspot."
            )
        else:
            lines = [
                f"Here are the recent bird sightings found within **{rad_label} km** of **{loc_label}** "
                f"from {checked}:"
            ]
            for s in sightings[:6]:
                src_badge = f"[{s.source}]"
                cnt = f"{s.count}x " if s.count and s.count > 1 else ""
                lines.append(
                    f"- **{cnt}{s.species_common_name}** (*{s.species_scientific_name or 'sp.'}*): "
                    f"Spotted at {s.location_name} ({s.distance_km:.1f} km away) on {s.observed_at}. {src_badge}"
                )
            if len(sightings) > 6:
                lines.append(f"\n*(And {len(sightings) - 6} additional records displayed in the cards below)*")
            lines.append("\nTip: Click any checklist link below to inspect exact observer notes and coordinates.")
            body = "\n".join(lines)

        return ChatResponse(
            reply=_with_notices(
                body,
                RULE_BASED_NOTICE.format(reason=ai_unavailable_reason),
                source_notice,
            ),
            sightings=sightings,
            parsed_query=metadata,
            mode="rule_based",
            unavailable_sources=unavailable,
        )
