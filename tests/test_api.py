from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health", headers={"User-Agent": "pytest-suite"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_blocks_missing_user_agent():
    resp = client.get("/health", headers={"User-Agent": ""})
    assert resp.status_code == 403


def test_blocks_known_scraper_user_agents():
    for ua in ("python-requests/2.31", "Scrapy/2.11", "curl/8.4.0"):
        resp = client.get("/health", headers={"User-Agent": ua})
        assert resp.status_code == 403, f"expected block for UA: {ua}"
