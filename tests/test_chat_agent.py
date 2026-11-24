from unittest.mock import MagicMock

import pytest
from google.genai import types

import birdai.chat_agent as chat_agent_module
from birdai.chat_agent import (
    MAX_TOOL_ROUNDS,
    BirdChatAgent,
    _extract_heuristics_from_prompt,
    _history_to_contents,
)
from birdai.schemas import ChatMessage, SightingItem


def _sighting(**overrides):
    data = dict(
        species_common_name="Common Kingfisher",
        species_code="comkin1",
        species_scientific_name="Alcedo atthis",
        count=1,
        observed_at="2026-11-21 09:15",
        location_name="Neeracherried ZH",
        latitude=47.5098,
        longitude=8.4988,
        distance_km=14.2,
        source="ebird",
    )
    data.update(overrides)
    return SightingItem(**data)


def _mock_aggregator(sightings=(), sources=("ebird",), **metadata):
    agg = MagicMock()
    agg.sources = list(sources)
    agg.search_sightings.return_value = (
        list(sightings),
        {"location_name": "Zurich", "radius_km": 15, "sources_queried": list(sources), **metadata},
    )
    return agg


def _function_call_response(**args):
    fn_call = types.FunctionCall(name="search_bird_sightings", args=args)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=fn_call)]))]
    )


def _text_response(text):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))]
    )


@pytest.fixture
def fake_gemini(monkeypatch):
    """Replace Gemini with a scripted sequence of responses; records every call."""
    calls = []
    script = []

    def fake_generate(client, *, contents, config):
        calls.append({"contents": list(contents), "config": config})
        return script.pop(0)

    monkeypatch.setattr(chat_agent_module, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(chat_agent_module, "get_client", lambda: object())
    monkeypatch.setattr(chat_agent_module, "generate_content_with_fallback", fake_generate)
    return script, calls


def _mode(call):
    return call["config"].tool_config.function_calling_config.mode


# --- heuristics / helpers -------------------------------------------------------


def test_extract_heuristics_from_prompt():
    assert _extract_heuristics_from_prompt("Kingfishers within 5 km of Zurich?") == ("Zurich", 5)
    assert _extract_heuristics_from_prompt("Birds in Bern within 25 km?") == ("Bern", 25)
    assert _extract_heuristics_from_prompt("Any owls?", default_radius=15) == (None, 15)


def test_history_to_contents_maps_roles_and_skips_system():
    contents = _history_to_contents(
        [
            ChatMessage(role="system", content="ignored"),
            ChatMessage(role="user", content="Birds near Bern?"),
            ChatMessage(role="assistant", content="Here are some..."),
        ]
    )
    assert [c.role for c in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "Birds near Bern?"


def test_sort_sightings_closest_then_most_recent():
    from birdai.ebird_client import sort_sightings

    older = _sighting(observed_at="2026-11-18 08:00", distance_km=2.0)
    newer = _sighting(observed_at="2026-11-21 08:00", distance_km=2.0)
    far = _sighting(observed_at="2026-11-22 08:00", distance_km=9.0)

    assert sort_sightings([far, older, newer]) == [newer, older, far]


# --- Gemini agent loop -----------------------------------------------------------


def test_agent_sends_history_and_function_response(fake_gemini):
    script, calls = fake_gemini
    script += [
        _function_call_response(location="Zurich", radius_km=5, species_name="Kingfisher"),
        _text_response("Two kingfishers were seen [eBird]."),
    ]
    agg = _mock_aggregator([_sighting()])

    res = BirdChatAgent(aggregator=agg).process_query(
        message="And kingfishers within 5 km?",
        conversation_history=[
            ChatMessage(role="user", content="What's around Zurich?"),
            ChatMessage(role="assistant", content="Lots of ducks."),
        ],
    )

    assert res.reply == "Two kingfishers were seen [eBird]."
    assert res.mode == "ai"
    assert len(res.sightings) == 1
    assert agg.search_sightings.call_args.kwargs["radius_km"] == 5
    assert agg.search_sightings.call_args.kwargs["species_name"] == "Kingfisher"

    # First call: prior turns, then the new message
    assert [c.role for c in calls[0]["contents"]] == ["user", "model", "user"]
    # Second call: + the model's function call and our function response
    fn_response = calls[1]["contents"][-1].parts[0].function_response
    assert fn_response.name == "search_bird_sightings"
    assert fn_response.response["total_sightings"] == 1


def test_agent_allows_follow_up_searches(fake_gemini):
    """Regression: a second tool call used to make the chat fall back to basic mode."""
    script, calls = fake_gemini
    script += [
        _function_call_response(location="Zurich", radius_km=5, species_name="owl"),
        _function_call_response(location="Zurich", radius_km=25, species_name="owl"),
        _text_response("Nothing within 5 km, but a Barn Owl 12 km away [eBird]."),
    ]
    agg = _mock_aggregator([_sighting(species_common_name="Western Barn Owl", species_code="barowl2")])

    res = BirdChatAgent(aggregator=agg).process_query("Any owls near Zurich?")

    assert res.mode == "ai"
    assert res.reply.startswith("Nothing within 5 km")
    assert agg.search_sightings.call_count == 2
    assert [c.kwargs["radius_km"] for c in agg.search_sightings.call_args_list] == [5, 25]
    assert len(res.sightings) == 1  # identical sighting from both searches is de-duplicated


def test_agent_forces_an_answer_after_max_tool_rounds(fake_gemini):
    script, calls = fake_gemini
    script += [_function_call_response(location="Zurich")] * MAX_TOOL_ROUNDS
    script += [_text_response("Here is what I found.")]
    agg = _mock_aggregator([_sighting()])

    res = BirdChatAgent(aggregator=agg).process_query("Birds near Zurich?")

    assert res.reply == "Here is what I found."
    assert agg.search_sightings.call_count == MAX_TOOL_ROUNDS
    assert [_mode(c) for c in calls] == ["AUTO"] * MAX_TOOL_ROUNDS + ["NONE"]


def test_agent_with_all_sources_down_answers_without_gemini_synthesis(fake_gemini):
    script, calls = fake_gemini
    script += [_function_call_response(location="Zurich")]
    agg = _mock_aggregator(unavailable_sources={"ebird": "could not be reached"})

    res = BirdChatAgent(aggregator=agg).process_query("Birds near Zurich?")

    assert len(calls) == 1  # no second Gemini call
    assert res.mode == "ai"
    assert "couldn't check for sightings" in res.reply


def test_agent_failure_falls_back_to_rule_based(fake_gemini):
    script, _ = fake_gemini  # empty script -> IndexError inside the loop
    agg = _mock_aggregator([_sighting()])

    res = BirdChatAgent(aggregator=agg).process_query("Kingfisher near Zurich")

    assert res.mode == "rule_based"
    assert "could not be reached" in res.reply


# --- rule-based fallback ---------------------------------------------------------


def test_fallback_passes_whole_message_for_species_detection():
    agg = _mock_aggregator(
        [_sighting()],
        matched_species=[{"species_code": "comkin1", "common_names": {"en": "Common Kingfisher"}}],
    )
    res = BirdChatAgent(aggregator=agg)._fallback_process("Gibt es Eisvögel bei Zürich?")

    kwargs = agg.search_sightings.call_args.kwargs
    assert kwargs["species_name"] == "Gibt es Eisvögel bei Zürich?"
    assert kwargs["species_in_free_text"] is True
    assert res.mode == "rule_based"
    assert res.reply.startswith("**Basic search mode:**")
    assert "for **Common Kingfisher**" in res.reply
    assert "14.2 km" in res.reply and "[ebird]" in res.reply


def test_fallback_no_results_does_not_suggest_25_km_when_already_25():
    agg = _mock_aggregator([], radius_km=25)
    res = BirdChatAgent(aggregator=agg)._fallback_process("Hoopoes within 25 km of Zurich")
    assert "found no matching records" in res.reply
    assert "up to 25 km" not in res.reply

    agg = _mock_aggregator([], radius_km=5)
    res = BirdChatAgent(aggregator=agg)._fallback_process("Hoopoes within 5 km of Zurich")
    assert "up to 25 km" in res.reply


def test_fallback_when_all_sources_fail_does_not_claim_no_birds():
    agg = _mock_aggregator(unavailable_sources={"ebird": "could not be reached"})
    res = BirdChatAgent(aggregator=agg)._fallback_process(
        "Birds near Zurich?", ai_unavailable_reason="could not be reached"
    )

    assert "Basic search mode" in res.reply
    assert "couldn't check for sightings" in res.reply
    assert "found no matching records" not in res.reply


def test_fallback_with_one_source_down_names_the_working_source():
    agg = _mock_aggregator(
        [_sighting(source="ornitho.ch")],
        sources=("ebird", "ornitho.ch"),
        unavailable_sources={"ebird": "not configured"},
    )
    res = BirdChatAgent(aggregator=agg)._fallback_process("Kingfisher near Zurich")

    assert "results are incomplete" in res.reply
    assert "eBird not configured" in res.reply
    assert "from ornitho.ch:" in res.reply
