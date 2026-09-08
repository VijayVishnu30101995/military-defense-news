from fastapi.testclient import TestClient

from app.core.jwt import create_access_token
from app.database import SessionLocal
from app.main import app
from app.schemas.source import SourceCreate
from app.services.source import SourceService


client = TestClient(app)
token = create_access_token("1")

db = SessionLocal()

try:
    service = SourceService(db)

    source_a = service.create(
        SourceCreate(
            name="__TEST_PATCH_A__",
            website_url="https://example.com",
            source_type="rss",
        )
    )

    source_b = service.create(
        SourceCreate(
            name="__TEST_PATCH_B__",
            website_url="https://example.org",
            source_type="rss",
        )
    )

    source_a_id = source_a.id
    source_b_id = source_b.id

finally:
    db.close()


response = client.patch(
    f"/api/v1/sources/{source_a_id}",
    json={
        "name": "__TEST_PATCH_B__",
    },
    headers={
        "Authorization": f"Bearer {token}",
    },
)

print("Status:", response.status_code)
print("Response:", response.json())

assert response.status_code == 409
assert response.json()["detail"] == "A source with this name already exists"

print("PATCH duplicate-name protection: PASS")


# Cleanup
db = SessionLocal()

try:
    service = SourceService(db)
    service.delete(source_a_id)
    service.delete(source_b_id)
finally:
    db.close()

print("Cleanup: PASS")
