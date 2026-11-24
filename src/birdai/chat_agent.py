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
from birdai.schemas import ChatMessage, ChatResponse, SightingItem
from birdai.sightings_aggregator import (
    SOURCE_LABELS,
    SightingsAggregator,
    describe_unavailable_sources,
)

logger = logging.getLogger(__name__)

# How many times Gemini may call the search tool for one user message before it must
# answer with what it has (e.g. search a species, then retry with a wider radius).
MAX_TOOL_ROUNDS = 3
# Sightings sent back to Gemini per search (all are still returned to the client)
MAX_SIGHTINGS_TO_MODEL = 25

CHAT_SYSTEM_PROMPT = """You are BirdAI Assistant, an expert naturalist and birdwatching guide.
You help birdwatchers discover recent bird sightings using verified real-time data.
Reply in the language the user writes in (English, German, French or Italian).

Searching:
1. Call `search_bird_sightings` with the location, radius (5, 15 or 25 km) and optional species.
   - If no radius is given, use the user's preferred radius. If no location is given, leave it
     empty to use their GPS position.
   - `species_name` accepts a species or a bird group in English, German, French, Italian or
     Latin, exactly as the user wrote it: "Eisvogel", "red kite", "owl", "Eulen", "chouette".
2. You may search again if it clearly helps, e.g. nothing found within 5 km -> try 25 km once,
   or the user asked about two different birds. Don't repeat an identical search.

Answering:
- Base every statement on the tool results. Never invent sightings, counts or places.
- Group sightings by species. Give common and scientific names, counts, dates, distances and
  places, and cite the source of each record (e.g. "[eBird]").
- For a group search (`species_match_type` = "group"):
  - Up to about 6 species: summarise each one.
  - More than that: briefly summarise the nearest/most notable few, list the rest by name,
    and ask whether the user wants to focus on one of them.
  - If `species_not_fetched` > 0, say that only the nearest species were looked up in detail.
- If nothing matched, say that this bird wasn't reported in the area and period, and suggest
  a wider radius or a typical habitat nearby. Don't claim the bird is absent.
- If the request is genuinely ambiguous (no idea which place, or a name that could mean very
  different birds), ask one short clarifying question instead of guessing.
- Add brief, practical habitat advice (reedbeds for bitterns, fast streams for dippers).
- If `unavailable_sources` is non-empty, the user already sees a notice about it, so don't
  repeat it. Never imply a bird is absent from a source that could not be queried.
"""


def _build_sightings_tool() -> types.Tool:
    fn = types.FunctionDeclaration(
        name="search_bird_sightings",
        description=(
            "Search recent bird sightings (live eBird data) within 5, 15 or 25 km of a "
            "location, optionally for one species or a bird group."
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
                    "description": (
                        "Optional species or bird group, in English, German, French, Italian "
                        "or Latin, as the user wrote it (e.g. 'Kingfisher', 'Eisvogel', "
                        "'Milvus milvus', 'owl', 'Eulen', 'pics'). Groups return all "
                        "matching species seen in the area."
                    ),
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
) -> tuple[Optional[str], int]:
    """Location and radius for rule-based mode (species are matched by the aggregator)."""
    lowered = prompt.lower()

    radius = default_radius
    if re.search(r"\b5\s*km\b", lowered):
        radius = 5
    elif re.search(r"\b25\s*km\b", lowered):
        radius = 25
    elif re.search(r"\b15\s*km\b", lowered):
        radius = 15

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

    return location, radius


_GEMINI_ROLES = {"user": "user", "assistant": "model"}

RULE_BASED_NOTICE = (
    "**Basic search mode:** the AI assistant {reason}, so I matched keywords in your "
    "message instead. I recognise bird names in English, German, French and Italian, "
    "but only some Swiss place names and radii of 5, 15 or 25 km, and I don't remember "
    "earlier messages."
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


def _sighting_key(s: SightingItem) -> tuple:
    return (s.source, s.species_code or s.species_common_name, s.location_name, s.observed_at)


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
        """Answer a message with Gemini, letting it search sightings up to MAX_TOOL_ROUNDS times."""
        if not GEMINI_API_KEY:
            return self._fallback_process(
                message=message,
                user_lat=user_lat,
                user_lng=user_lng,
                preferred_radius_km=preferred_radius_km,
                ai_unavailable_reason="is not configured",
            )

        try:
            return self._agent_loop(
                message, conversation_history, user_lat, user_lng, preferred_radius_km
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

    def _agent_loop(
        self,
        message: str,
        conversation_history: Optional[list[ChatMessage]],
        user_lat: Optional[float],
        user_lng: Optional[float],
        preferred_radius_km: int,
    ) -> ChatResponse:
        client = get_client()
        tool = _build_sightings_tool()
        sources = self.aggregator.sources

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

        sightings: dict[tuple, SightingItem] = {}
        last_metadata: dict = {"location_name": "unknown", "radius_km": preferred_radius_km}
        unavailable: dict[str, str] = {}

        for round_no in range(MAX_TOOL_ROUNDS + 1):
            # On the last round tools stay declared (the history contains tool calls) but
            # Gemini must answer in text with what it has.
            final_round = round_no == MAX_TOOL_ROUNDS
            config = types.GenerateContentConfig(
                system_instruction=CHAT_SYSTEM_PROMPT,
                tools=[tool],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="NONE" if final_round else "AUTO"
                    )
                ),
            )
            response = generate_content_with_fallback(client, contents=contents, config=config)

            function_calls = response.function_calls or []
            if not function_calls:
                return ChatResponse(
                    reply=_with_notices(
                        extract_response_text(response),
                        describe_unavailable_sources(unavailable, sources),
                    ),
                    sightings=sorted(sightings.values(), key=lambda s: s.distance_km),
                    parsed_query=last_metadata,
                    mode="ai",
                    unavailable_sources=unavailable,
                )

            contents.append(response.candidates[0].content)
            response_parts = []
            for fn_call in function_calls:
                args = dict(fn_call.args or {})
                found, metadata = self.aggregator.search_sightings(
                    location_name=args.get("location") or None,
                    radius_km=int(args.get("radius_km") or preferred_radius_km),
                    species_name=args.get("species_name") or None,
                    back_days=int(args.get("back_days") or 7),
                    user_lat=user_lat,
                    user_lng=user_lng,
                )
                last_metadata = metadata
                unavailable.update(metadata.get("unavailable_sources", {}))
                for s in found:
                    sightings.setdefault(_sighting_key(s), s)

                # Every source failed: nothing for Gemini to work with, so say so directly
                if set(unavailable) >= set(sources):
                    return ChatResponse(
                        reply=describe_unavailable_sources(unavailable, sources),
                        sightings=[],
                        parsed_query=metadata,
                        mode="ai",
                        unavailable_sources=unavailable,
                    )

                response_parts.append(
                    types.Part.from_function_response(
                        name=fn_call.name,
                        response={
                            "query": metadata,
                            "total_sightings": len(found),
                            "sightings": [
                                s.model_dump(mode="json") for s in found[:MAX_SIGHTINGS_TO_MODEL]
                            ],
                        },
                    )
                )
            contents.append(types.Content(role="user", parts=response_parts))

        raise RuntimeError("Gemini kept calling tools after tool calling was disabled.")

    def _fallback_process(
        self,
        message: str,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
        preferred_radius_km: int = 15,
        ai_unavailable_reason: str = "is unavailable",
    ) -> ChatResponse:
        """Rule-based response: keyword location/radius, species detected in the message."""
        loc, radius = _extract_heuristics_from_prompt(message, default_radius=preferred_radius_km)
        sightings, metadata = self.aggregator.search_sightings(
            location_name=loc,
            radius_km=radius,
            species_name=message,
            species_in_free_text=True,
            user_lat=user_lat,
            user_lng=user_lng,
        )

        loc_label = metadata["location_name"]
        rad_label = metadata["radius_km"]
        unavailable = metadata.get("unavailable_sources", {})
        queried = metadata.get("sources_queried", self.aggregator.sources)
        source_notice = describe_unavailable_sources(unavailable, queried)
        checked = " and ".join(SOURCE_LABELS[src] for src in queried if src not in unavailable)
        matched = metadata.get("matched_species", [])
        species_label = ", ".join(m["common_names"].get("en", m["species_code"]) for m in matched)
        about = f" for **{species_label}**" if species_label else ""

        if not sightings and not checked:
            body = ""  # the source notice already explains that nothing could be checked
        elif not sightings:
            wider = (
                " Try a wider radius (up to 25 km) or a nearby wetland or forest hotspot."
                if rad_label < 25
                else " Try a nearby wetland or forest hotspot, or a longer time period."
            )
            body = (
                f"I searched recent sightings{about} within **{rad_label} km** of **{loc_label}** "
                f"on {checked}, but found no matching records in the last "
                f"{metadata.get('back_days', 7)} days.{wider}"
            )
        else:
            lines = [
                f"Here are the recent sightings{about} within **{rad_label} km** of "
                f"**{loc_label}** from {checked}:"
            ]
            if metadata.get("species_note"):
                lines.insert(0, f"*{metadata['species_note']}*")
            for s in sightings[:6]:
                cnt = f"{s.count}x " if s.count and s.count > 1 else ""
                lines.append(
                    f"- **{cnt}{s.species_common_name}** (*{s.species_scientific_name or 'sp.'}*): "
                    f"Spotted at {s.location_name} ({s.distance_km:.1f} km away) on {s.observed_at}. [{s.source}]"
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
