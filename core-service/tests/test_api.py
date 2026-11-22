import os

import pytest
from fastapi.testclient import TestClient

from app import weather
from app.domain import DayCondition


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("API_KEYS", "kunci-uji")
    # Jangan memanggil internet saat tes: pakai cuaca palsu (lembab + hujan)
    fake = [DayCondition(f"2026-12-0{i+1}", 90.0, 15.0) for i in range(7)]
    monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon, days=7: fake)
    from app.main import app

    with TestClient(app) as c:
        yield c


def auth_header(client):
    creds = {"email": "a@b.co", "password": "rahasia123"}
    client.post("/api/auth/register", json=creds)
    token = client.post("/api/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_duplicate_register_is_409(client):
    creds = {"email": "a@b.co", "password": "rahasia123"}
    assert client.post("/api/auth/register", json=creds).status_code == 201
    assert client.post("/api/auth/register", json=creds).status_code == 409


def test_wrong_password_is_401(client):
    creds = {"email": "a@b.co", "password": "rahasia123"}
    client.post("/api/auth/register", json=creds)
    bad = client.post("/api/auth/login", json={**creds, "password": "salahsalah"})
    assert bad.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/medicines").status_code == 401


def test_full_flow_readiness_warns_about_low_stock(client):
    h = auth_header(client)
    client.put("/api/profile", headers=h, json={"latitude": -6.89, "longitude": 107.61, "vulnerabilities": ["asma"]})
    client.post("/api/medicines", headers=h, json={"name": "Salbutamol", "dose_per_intake": 1, "intakes_per_day": 2, "stock_units": 6})
    r = client.get("/api/readiness", headers=h).json()
    assert r["risk_level"] == "tinggi"
    assert r["stock_days_left"] == 3.0
    assert "menambah stok" in r["advice"]


def test_readiness_without_profile_is_400(client):
    assert client.get("/api/readiness", headers=auth_header(client)).status_code == 400


def test_public_risk_needs_api_key(client):
    assert client.get("/api/public/risk?lat=-6.89&lon=107.61").status_code == 401
    ok = client.get("/api/public/risk?lat=-6.89&lon=107.61", headers={"X-API-Key": "kunci-uji"})
    assert ok.status_code == 200 and ok.json()["risk_level"] == "tinggi"


def test_weather_down_gives_503(client, monkeypatch):
    def boom(*a, **k):
        raise weather.WeatherUnavailable("down")

    monkeypatch.setattr(weather, "fetch_forecast", boom)
    r = client.get("/api/public/risk?lat=-6.89&lon=107.61", headers={"X-API-Key": "kunci-uji"})
    assert r.status_code == 503
