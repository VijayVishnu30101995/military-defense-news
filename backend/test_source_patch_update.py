from fastapi.testclient import TestClient

from app.core.jwt import create_access_token
from app.database import SessionLocal
from app.main import app
from app.schemas.source import SourceCreate
from app.services.source import SourceService


def test_patch_partial_update_success() -> None:
    client = TestClient(app)
    token = create_access_token("1")

    db = SessionLocal()
    try:
        service = SourceService(db)
        source = service.create(
            SourceCreate(
                name="__TEST_PATCH__",
                website_url="https://example.com",
                source_type="rss",
            )
        )
        source_id = source.id
    finally:
        db.close()

    try:
        response = client.patch(
            f"/api/v1/sources/{source_id}",
            json={
                "reliability_score": 90,
            },
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "__TEST_PATCH__"
        assert data["reliability_score"] == 90
        assert data["website_url"] == "https://example.com/"
    finally:
        db = SessionLocal()
        try:
            service = SourceService(db)
            service.delete(source_id)
        finally:
            db.close()
