from datetime import datetime

from birdai import context as context_module


def test_default_observation_context_uses_local_system_time(monkeypatch):
    fake_now = datetime.fromisoformat("2026-05-19T14:05:06+02:00")
    monkeypatch.setattr(context_module, "get_local_now", lambda: fake_now)

    context = context_module.get_default_observation_context()

    assert context.observation_date.isoformat() == "2026-05-19"
    assert context.observation_time.isoformat() == "14:05:06"


def test_resolve_observation_context_warns_when_coordinates_missing():
    observation_context = context_module.build_observation_context(
        observation_date="2026-05-19",
        observation_time="14:05:06",
        location_text="Zurich, Switzerland",
        latitude=None,
        longitude=None,
    )

    resolved_context, warnings = context_module.resolve_observation_context(
        observation_context
    )

    assert resolved_context.latitude is None
    assert resolved_context.longitude is None
    assert warnings == ["No coordinates were provided. Skipping eBird enrichment."]


def test_resolve_observation_context_keeps_manual_coordinates():
    observation_context = context_module.build_observation_context(
        observation_date="2026-05-19",
        observation_time="14:05:06",
        location_text="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
    )

    resolved_context, warnings = context_module.resolve_observation_context(
        observation_context
    )

    assert not warnings
    assert resolved_context.location_source == "manual_coordinates"
