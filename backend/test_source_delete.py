from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.database import SessionLocal


client = TestClient(app)


def login() -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200, response.text

    return response.json()["access_token"]


token = login()

headers = {
    "Authorization": f"Bearer {token}",
}


# ---------------------------------------------------------
# 1. DELETE missing source
# ---------------------------------------------------------

response = client.delete(
    "/api/v1/sources/999999999",
    headers=headers,
)

assert response.status_code == 404
assert response.json()["detail"] == "Source not found"

print("DELETE missing source: PASS")


# ---------------------------------------------------------
# 2. Create temporary source
# ---------------------------------------------------------

source_payload = {
    "name": "__TEST_DELETE_SOURCE__",
    "website_url": "https://example.com",
    "feed_url": "https://example.com/feed.xml",
    "source_type": "rss",
    "language": "en",
    "reliability_score": 100,
    "is_active": True,
    "collection_frequency": 360,
}

response = client.post(
    "/api/v1/sources",
    json=source_payload,
    headers=headers,
)

assert response.status_code == 201, response.text

source = response.json()
source_id = source["id"]

print(f"Created temporary source: {source_id}")


# ---------------------------------------------------------
# 3. Create collection job for the source
# ---------------------------------------------------------

db = SessionLocal()

try:
    db.execute(
        text(
            """
            INSERT INTO source_collection_jobs (
                source_id,
                is_enabled,
                interval_minutes,
                next_run_at,
                created_at,
                updated_at
            )
            VALUES (
                :source_id,
                true,
                360,
                :next_run_at,
                now(),
                now()
            )
            """
        ),
        {
            "source_id": source_id,
            "next_run_at": datetime.now(timezone.utc),
        },
    )

    db.commit()

    print("Temporary collection job created: PASS")

finally:
    db.close()


# ---------------------------------------------------------
# 4. Confirm collection job exists
# ---------------------------------------------------------

db = SessionLocal()

try:
    job_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM source_collection_jobs
            WHERE source_id = :source_id
            """
        ),
        {"source_id": source_id},
    ).scalar_one()

    assert job_count == 1

    print("Collection job exists before DELETE: PASS")

finally:
    db.close()


# ---------------------------------------------------------
# 5. DELETE source
# ---------------------------------------------------------

response = client.delete(
    f"/api/v1/sources/{source_id}",
    headers=headers,
)

assert response.status_code == 204
assert response.content == b""

print("DELETE source: PASS")


# ---------------------------------------------------------
# 6. GET deleted source
# ---------------------------------------------------------

response = client.get(
    f"/api/v1/sources/{source_id}",
    headers=headers,
)

assert response.status_code == 404
assert response.json()["detail"] == "Source not found"

print("GET deleted source: PASS")


# ---------------------------------------------------------
# 7. Verify collection job was cascaded
# ---------------------------------------------------------

db = SessionLocal()

try:
    source_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM sources
            WHERE id = :source_id
            """
        ),
        {"source_id": source_id},
    ).scalar_one()

    job_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM source_collection_jobs
            WHERE source_id = :source_id
            """
        ),
        {"source_id": source_id},
    ).scalar_one()

    assert source_count == 0
    assert job_count == 0

    print("Source DB deletion: PASS")
    print("Collection job CASCADE deletion: PASS")

finally:
    db.close()


print()
print("SOURCE DELETE TEST: ALL PASS")
