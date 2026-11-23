from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from birdai.api import routes as routes_module
from birdai.api.app import app
from birdai.db.models import UserModel
from birdai.schemas import SightingItem

SIGHTING = SightingItem(
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
METADATA = {"location_name": "Zurich", "radius_km": 15, "total_count": 1, "sources": ["ornitho.ch"]}


@pytest.fixture
def mock_aggregator(monkeypatch):
    aggregator = MagicMock()
    aggregator.search_sightings.return_value = ([SIGHTING], METADATA)
    monkeypatch.setattr(routes_module.chat_agent, "aggregator", aggregator)
    # Force the offline rule-based path so tests never call Gemini
    monkeypatch.setattr("birdai.chat_agent.GEMINI_API_KEY", "")
    return aggregator


@pytest.fixture
def authed_client(mock_aggregator):
    mock_user = UserModel(
        id="test-user-123",
        email="test@example.com",
        hashed_password="hash",
        full_name="Test User",
        is_active=True,
    )
    app.dependency_overrides[routes_module.get_current_active_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_chat_requires_authentication(mock_aggregator):
    response = TestClient(app).post("/api/chat", json={"message": "Kingfishers near Zurich?"})
    assert response.status_code == 401


def test_sightings_requires_authentication(mock_aggregator):
    response = TestClient(app).get("/api/sightings?location=Zurich")
    assert response.status_code == 401


def test_api_chat_endpoint(authed_client):
    response = authed_client.post(
        "/api/chat",
        json={
            "message": "Have any Kingfishers been seen within 15 km of Zurich?",
            "preferred_radius_km": 15,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "Common Kingfisher" in data["reply"]
    assert data["sightings"][0]["source"] == "ornitho.ch"
    assert data["parsed_query"]["location_name"] == "Zurich"
    assert data["mode"] == "rule_based"
    assert "Basic search mode" in data["reply"]


def test_api_sightings_endpoint(authed_client, mock_aggregator):
    response = authed_client.get("/api/sightings?location=Zurich&radius_km=15&species=kingfisher")

    assert response.status_code == 200
    data = response.json()
    assert data["sightings"][0]["species_common_name"] == "Common Kingfisher"
    assert data["unavailable_sources"] == {}
    mock_aggregator.search_sightings.assert_called_once_with(
        location_name="Zurich",
        radius_km=15,
        species_name="kingfisher",
        user_lat=None,
        user_lng=None,
    )


def test_api_sightings_reports_unavailable_sources(authed_client, mock_aggregator):
    mock_aggregator.search_sightings.return_value = (
        [],
        {**METADATA, "unavailable_sources": {"ebird": "could not be reached"}},
    )
    response = authed_client.get("/api/sightings?location=Zurich")

    assert response.status_code == 200
    assert response.json()["unavailable_sources"] == {"ebird": "could not be reached"}
