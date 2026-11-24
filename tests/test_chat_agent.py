from unittest.mock import MagicMock

from birdai.chat_agent import BirdChatAgent, _extract_heuristics_from_prompt
from birdai.schemas import SightingItem


def test_extract_heuristics_from_prompt():
    loc, rad, sp = _extract_heuristics_from_prompt(
        "Have any Kingfishers been seen within 5 km of Zurich?", default_radius=15
    )
    assert loc == "Zurich"
    assert rad == 5
    assert sp == "Kingfisher"

    loc, rad, sp = _extract_heuristics_from_prompt(
        "What birds are spotted in Bern within 25 km?", default_radius=15
    )
    assert loc == "Bern"
    assert rad == 25
    assert sp is None


def test_chat_agent_fallback_process():
    mock_agg = MagicMock()
    mock_agg.sources = ["ebird", "ornitho.ch"]
    mock_agg.search_sightings.return_value = (
        [
            SightingItem(
                species_common_name="Common Kingfisher",
                species_scientific_name="Alcedo atthis",
                count=1,
                observed_at="2026-11-21 09:15",
                location_name="Neeracherried ZH",
                latitude=47.5098,
                longitude=8.4988,
                distance_km=14.2,
                source="ornitho.ch",
            )
        ],
        {"location_name": "Zurich", "radius_km": 15, "total_count": 1, "sources": ["ornitho.ch"]},
    )

    agent = BirdChatAgent(aggregator=mock_agg)
    res = agent._fallback_process("Kingfisher within 15 km of Zurich")

    assert len(res.sightings) == 1
    assert "Common Kingfisher" in res.reply
    assert "14.2 km" in res.reply
    assert "[ornitho.ch]" in res.reply
    assert res.parsed_query["location_name"] == "Zurich"
    assert res.mode == "rule_based"
    assert res.reply.startswith("**Basic search mode:**")
    assert res.unavailable_sources == {}


def _sighting(**overrides):
    data = dict(
        species_common_name="Common Kingfisher",
        species_scientific_name="Alcedo atthis",
        count=1,
        observed_at="2026-11-21 09:15",
        location_name="Neeracherried ZH",
        latitude=47.5098,
        longitude=8.4988,
        distance_km=14.2,
        source="ornitho.ch",
    )
    data.update(overrides)
    return SightingItem(**data)


def test_history_to_contents_maps_roles_and_skips_system():
    from birdai.chat_agent import _history_to_contents
    from birdai.schemas import ChatMessage

    contents = _history_to_contents(
        [
            ChatMessage(role="system", content="ignored"),
            ChatMessage(role="user", content="Birds near Bern?"),
            ChatMessage(role="assistant", content="Here are some..."),
        ]
    )
    assert [c.role for c in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "Birds near Bern?"


def test_gemini_path_sends_history_and_function_response(monkeypatch):
    from google.genai import types

    import birdai.chat_agent as chat_agent_module
    from birdai.schemas import ChatMessage

    fn_call = types.FunctionCall(
        name="search_bird_sightings",
        args={"location": "Zurich", "radius_km": 5, "species_name": "Kingfisher"},
    )
    first = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(function_call=fn_call)])
            )
        ]
    )
    second = MagicMock(text="Two kingfishers were seen [ornitho.ch].", output_text=None)

    calls = []

    def fake_generate(client, *, contents, config):
        calls.append(list(contents))
        return first if len(calls) == 1 else second

    monkeypatch.setattr(chat_agent_module, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(chat_agent_module, "get_client", lambda: object())
    monkeypatch.setattr(chat_agent_module, "generate_content_with_fallback", fake_generate)

    mock_agg = MagicMock()
    mock_agg.sources = ["ebird", "ornitho.ch"]
    mock_agg.search_sightings.return_value = ([_sighting()], {"location_name": "Zurich", "radius_km": 5})

    res = BirdChatAgent(aggregator=mock_agg).process_query(
        message="And kingfishers within 5 km?",
        conversation_history=[
            ChatMessage(role="user", content="What's around Zurich?"),
            ChatMessage(role="assistant", content="Lots of ducks."),
        ],
    )

    assert res.reply == "Two kingfishers were seen [ornitho.ch]."
    assert res.mode == "ai"
    assert len(res.sightings) == 1
    mock_agg.search_sightings.assert_called_once()
    assert mock_agg.search_sightings.call_args.kwargs["radius_km"] == 5

    # First call includes prior turns before the new message
    assert [c.role for c in calls[0]] == ["user", "model", "user"]
    # Second call appends the model's function call and the function response
    fn_response = calls[1][-1].parts[0].function_response
    assert fn_response.name == "search_bird_sightings"
    assert fn_response.response["total_sightings"] == 1


def test_sort_sightings_closest_then_most_recent():
    from birdai.ebird_client import sort_sightings

    older = _sighting(observed_at="2026-11-18 08:00", distance_km=2.0)
    newer = _sighting(observed_at="2026-11-21 08:00", distance_km=2.0)
    far = _sighting(observed_at="2026-11-22 08:00", distance_km=9.0)

    assert sort_sightings([far, older, newer]) == [newer, older, far]


def test_fallback_when_all_sources_fail_does_not_claim_no_birds():
    mock_agg = MagicMock()
    mock_agg.sources = ["ebird", "ornitho.ch"]
    mock_agg.search_sightings.return_value = (
        [],
        {
            "location_name": "Zurich",
            "radius_km": 15,
            "unavailable_sources": {
                "ebird": "could not be reached",
                "ornitho.ch": "could not be reached",
            },
        },
    )
    res = BirdChatAgent(aggregator=mock_agg)._fallback_process(
        "Birds near Zurich?", ai_unavailable_reason="could not be reached"
    )

    assert "Basic search mode" in res.reply
    assert "couldn't check for sightings" in res.reply
    assert "found no matching records" not in res.reply
    assert set(res.unavailable_sources) == {"ebird", "ornitho.ch"}


def test_fallback_with_one_source_down_names_the_working_source():
    mock_agg = MagicMock()
    mock_agg.sources = ["ebird", "ornitho.ch"]
    mock_agg.search_sightings.return_value = (
        [_sighting()],
        {"location_name": "Zurich", "radius_km": 15, "unavailable_sources": {"ebird": "not configured"}},
    )
    res = BirdChatAgent(aggregator=mock_agg)._fallback_process("Kingfisher near Zurich")

    assert "results are incomplete" in res.reply
    assert "eBird not configured" in res.reply
    assert "from ornitho.ch:" in res.reply


def test_ai_path_with_all_sources_down_skips_synthesis(monkeypatch):
    from google.genai import types

    import birdai.chat_agent as chat_agent_module

    fn_call = types.FunctionCall(name="search_bird_sightings", args={"location": "Zurich"})
    first = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fn_call)]))]
    )
    calls = []

    def fake_generate(client, *, contents, config):
        calls.append(contents)
        return first

    monkeypatch.setattr(chat_agent_module, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(chat_agent_module, "get_client", lambda: object())
    monkeypatch.setattr(chat_agent_module, "generate_content_with_fallback", fake_generate)

    mock_agg = MagicMock()
    mock_agg.sources = ["ebird", "ornitho.ch"]
    mock_agg.search_sightings.return_value = (
        [],
        {
            "location_name": "Zurich",
            "radius_km": 15,
            "unavailable_sources": {"ebird": "could not be reached", "ornitho.ch": "could not be reached"},
        },
    )
    res = BirdChatAgent(aggregator=mock_agg).process_query("Birds near Zurich?")

    assert len(calls) == 1  # no second Gemini call
    assert res.mode == "ai"
    assert "couldn't check for sightings" in res.reply
