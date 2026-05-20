from datetime import datetime

import httpx

from birdai import context as context_module


def test_default_observation_context_uses_local_system_time(monkeypatch):
    fake_now = datetime.fromisoformat("2026-05-19T14:05:06+02:00")
    monkeypatch.setattr(context_module, "get_local_now", lambda: fake_now)
    monkeypatch.setattr(
        context_module,
        "geocode_location",
        lambda location_text, http_client=None: (47.3769, 8.5417),
    )

    context = context_module.get_default_observation_context()

    assert context.observation_date.isoformat() == "2026-05-19"
    assert context.observation_time.isoformat() == "14:05:06"
    assert context.latitude == 47.3769
    assert context.longitude == 8.5417
    assert context.location_source == "geocoded_location"


def test_resolve_observation_context_warns_when_coordinates_missing():
    observation_context = context_module.build_observation_context(
        observation_date="2026-05-19",
        observation_time="14:05:06",
        location_text="Zurich, Switzerland",
        latitude=None,
        longitude=None,
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[{"lat": "47.3769", "lon": "8.5417"}],
        )
    )
    client = httpx.Client(transport=transport)

    resolved_context, warnings = context_module.resolve_observation_context(
        observation_context,
        http_client=client,
    )

    assert resolved_context.latitude == 47.3769
    assert resolved_context.longitude == 8.5417
    assert resolved_context.location_source == "geocoded_location"
    assert warnings == []


def test_resolve_observation_context_prefers_photo_exif(monkeypatch):
    observation_context = context_module.build_observation_context(
        observation_date="2026-05-19",
        observation_time="14:05:06",
        location_text="Zurich, Switzerland",
        latitude=47.3,
        longitude=8.5,
    )
    monkeypatch.setattr(
        context_module,
        "extract_photo_coordinates",
        lambda file_path: (47.4001, 8.6002),
    )
    monkeypatch.setattr(
        context_module,
        "reverse_geocode_coordinates",
        lambda latitude, longitude, http_client=None: "Recovered Photo Location",
    )

    resolved_context, warnings = context_module.resolve_observation_context(
        observation_context,
        file_path="sample.jpg",
        detected_file=context_module.DetectedFileType(
            modality="image",
            mime_type="image/jpeg",
        ),
    )

    assert resolved_context.latitude == 47.4001
    assert resolved_context.longitude == 8.6002
    assert resolved_context.location_text == "Recovered Photo Location"
    assert resolved_context.location_source == "photo_exif"
    assert warnings == []


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


def test_resolve_observation_context_replaces_placeholder_zero_coordinates():
    observation_context = context_module.build_observation_context(
        observation_date="2026-05-19",
        observation_time="14:05:06",
        location_text="Zurich, Switzerland",
        latitude=0.0,
        longitude=0.0,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[{"lat": "47.3769", "lon": "8.5417"}],
        )
    )
    client = httpx.Client(transport=transport)

    resolved_context, warnings = context_module.resolve_observation_context(
        observation_context,
        http_client=client,
    )

    assert resolved_context.latitude == 47.3769
    assert resolved_context.longitude == 8.5417
    assert resolved_context.location_source == "geocoded_location"
    assert warnings == [
        "Coordinates 0.0, 0.0 look like a placeholder. Geocoding the location text instead."
    ]
