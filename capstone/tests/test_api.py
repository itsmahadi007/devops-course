from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ask_echoes_question():
    r = client.get("/ask", params={"q": "what is devops?"})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "what is devops?"
    assert "placeholder" in body["answer"]


def test_visits_degrades_without_redis():
    r = client.get("/visits")
    assert r.status_code == 200
    assert r.json()["visits"] is None