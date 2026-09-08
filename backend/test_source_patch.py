from fastapi.testclient import TestClient

from app.core.jwt import create_access_token
from app.main import app


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

print("Status:", response.status_code)
print("Response:", response.json())

assert response.status_code == 404

print("PATCH endpoint: PASS")
