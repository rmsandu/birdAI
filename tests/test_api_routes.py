import io
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from birdai.api.app import app
from birdai.api import routes as routes_module
from birdai.db.models import UserModel
from birdai.storage import LocalObservationStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_client(tmp_path, monkeypatch):
    test_store = LocalObservationStore(base_dir=str(tmp_path))
    monkeypatch.setattr(routes_module, "store", test_store)
    mock_user = UserModel(
        id="test-user-123",
        email="test@example.com",
        hashed_password="hash",
        full_name="Test User",
        is_active=True,
    )
    app.dependency_overrides[routes_module.get_current_active_user] = lambda: mock_user
    app.dependency_overrides[routes_module.get_current_user] = lambda: mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_health_endpoint(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "birdai"}


def test_create_and_get_observation(test_client):
    sample_img = FIXTURES / "sample.jpg"
    assert sample_img.exists()

    with sample_img.open("rb") as f:
        file_bytes = f.read()

    response = test_client.post(
        "/api/observations",
        data={
            "location_text": "Zurich, Switzerland",
            "observation_date": "2026-05-20",
            "observation_time": "12:00:00",
            "merlin_species": "Eurasian Blue Tit",
            "merlin_notes": "Heard song",
            "use_mock": "true",
        },
        files={"image": ("sample.jpg", file_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    obs_id = data["id"]
    assert data["modality"] == "image"
    assert data["merlin_suggestion"]["species_name"] == "Eurasian Blue Tit"
    assert len(data["candidates"]) >= 1

    # Check retrieve endpoint
    get_res = test_client.get(f"/api/observations/{obs_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == obs_id

    # Check correct observation endpoint
    corr_res = test_client.post(
        f"/api/observations/{obs_id}/correct",
        json={
            "confirmed_species": "European Robin",
            "scientific_name": "Erithacus rubecula",
            "is_correct_prediction": True,
            "correction_notes": "Verified by observer in field",
        },
    )
    assert corr_res.status_code == 200
    corr_data = corr_res.json()
    assert corr_data["user_correction"]["confirmed_species"] == "European Robin"

    # Check list endpoint
    list_res = test_client.get("/api/observations?reviewed_only=true")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


def test_create_observation_requires_media(test_client):
    response = test_client.post(
        "/api/observations",
        data={"location_text": "Zurich, Switzerland"},
    )
    assert response.status_code == 400
    assert "At least one image or audio file" in response.json()["detail"]


def test_observation_endpoints_require_authentication():
    # Fresh client with no auth overrides
    app.dependency_overrides.clear()
    unauth_client = TestClient(app)

    res = unauth_client.get("/api/observations")
    assert res.status_code == 401

    post_res = unauth_client.post("/api/observations")
    assert post_res.status_code == 401

