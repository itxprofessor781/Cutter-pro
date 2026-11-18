
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_upload_requires_video_file():
    response = client.post("/api/upload")

    assert response.status_code == 422
