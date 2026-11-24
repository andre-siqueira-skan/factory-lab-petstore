import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


def test_create_and_get(client):
    created = client.post("/pets", json={"name": "Rex", "species": "dog"}).json()
    assert created["status"] == "available"
    assert client.get(f"/pets/{created['id']}").json() == created


def test_filter_by_status(client):
    client.post("/pets", json={"name": "Tom", "species": "cat", "status": "sold"})
    client.post("/pets", json={"name": "Bo", "species": "dog"})
    assert [p["name"] for p in client.get("/pets", params={"status": "sold"}).json()] == ["Tom"]


def test_missing_pet_is_404(client):
    assert client.get("/pets/999").status_code == 404
    assert client.delete("/pets/999").status_code == 404


@pytest.mark.stack
@pytest.mark.skipif(not os.environ.get("STACK_URL"), reason="STACK_URL not set")
def test_stack_round_trip():
    base = os.environ["STACK_URL"]
    created = httpx.post(f"{base}/pets", json={"name": "Nemo", "species": "fish"}).json()
    assert httpx.get(f"{base}/pets/{created['id']}").status_code == 200
    assert httpx.delete(f"{base}/pets/{created['id']}").status_code == 204
