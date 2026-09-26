from fastapi.testclient import TestClient

from app.core.jwt import create_access_token
from app.main import app


def test_patch_missing_source_returns_404() -> None:
    client = TestClient(app)
    token = create_access_token("1")

    response = client.patch(
        "/api/v1/sources/999999",
        json={
            "reliability_score": 90,
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found"
