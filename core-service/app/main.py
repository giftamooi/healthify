"""Healthify core service: semua endpoint ada di bawah prefix /api."""
import json
import sqlite3
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import domain, weather
from .db import get_db, init_db
from .security import (
    create_token,
    current_user,
    hash_password,
    require_api_key,
    verify_password,
)

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
HORIZON_DAYS = 7


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Healthify Core Service",
    version="0.1.0",
    description="Skor risiko musiman + kesiapan stok obat. Data uji saja, bukan diagnosis.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
router = APIRouter(prefix="/api")


# ---------- skema ----------
class Credentials(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class ProfileIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    vulnerabilities: list[str] = Field(default_factory=list, max_length=10)


class MedicineIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    dose_per_intake: float = Field(gt=0)
    intakes_per_day: int = Field(ge=1, le=12)
    stock_units: float = Field(ge=0)


def _weather_or_503(lat: float, lon: float):
    try:
        return weather.fetch_forecast(lat, lon, HORIZON_DAYS)
    except weather.WeatherUnavailable:
        raise HTTPException(503, "Data cuaca sementara tidak tersedia, coba lagi nanti")


# ---------- umum ----------
@router.get("/health", tags=["umum"])
def health():
    return {"status": "ok"}


# ---------- identitas & akses ----------
@router.post("/auth/register", status_code=201, tags=["auth"])
def register(body: Credentials, db=Depends(get_db)):
    try:
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (body.email.lower(), hash_password(body.password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Email sudah terdaftar")
    return {"message": "Pendaftaran berhasil"}


@router.post("/auth/login", tags=["auth"])
def login(body: Credentials, db=Depends(get_db)):
    row = db.execute("SELECT * FROM users WHERE email = ?", (body.email.lower(),)).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Email atau password salah")
    return {"access_token": create_token(row["id"]), "token_type": "bearer"}


# ---------- profil kesehatan ----------
@router.put("/profile", tags=["profil"])
def put_profile(body: ProfileIn, user=Depends(current_user), db=Depends(get_db)):
    db.execute(
        "UPDATE users SET latitude=?, longitude=?, vulnerabilities=? WHERE id=?",
        (body.latitude, body.longitude, json.dumps(body.vulnerabilities), user["id"]),
    )
    db.commit()
    return body


@router.get("/profile", tags=["profil"])
def get_profile(user=Depends(current_user)):
    return {
        "email": user["email"],
        "latitude": user["latitude"],
        "longitude": user["longitude"],
        "vulnerabilities": json.loads(user["vulnerabilities"]),
    }


# ---------- manajemen obat ----------
@router.post("/medicines", status_code=201, tags=["obat"])
def add_medicine(body: MedicineIn, user=Depends(current_user), db=Depends(get_db)):
    cur = db.execute(
        "INSERT INTO medicines (user_id, name, dose_per_intake, intakes_per_day, stock_units) "
        "VALUES (?, ?, ?, ?, ?)",
        (user["id"], body.name, body.dose_per_intake, body.intakes_per_day, body.stock_units),
    )
    db.commit()
    return {"id": cur.lastrowid, **body.model_dump()}


@router.get("/medicines", tags=["obat"])
def list_medicines(user=Depends(current_user), db=Depends(get_db)):
    rows = db.execute("SELECT * FROM medicines WHERE user_id = ?", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@router.delete("/medicines/{medicine_id}", status_code=204, tags=["obat"])
def delete_medicine(medicine_id: int, user=Depends(current_user), db=Depends(get_db)):
    cur = db.execute(
        "DELETE FROM medicines WHERE id = ? AND user_id = ?", (medicine_id, user["id"])
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Obat tidak ditemukan")


# ---------- risiko musiman (inti) ----------
@router.get("/readiness", tags=["risiko"])
def readiness(user=Depends(current_user), db=Depends(get_db)):
    """Skor risiko pengguna + saran kesiapan stok (butuh JWT)."""
    if user["latitude"] is None:
        raise HTTPException(400, "Lengkapi profil (lokasi) dulu lewat PUT /api/profile")
    days = _weather_or_503(user["latitude"], user["longitude"])
    vulns = json.loads(user["vulnerabilities"])
    score = domain.risk_score(days, vulns)
    level = domain.risk_level(score)
    meds = [dict(r) for r in db.execute("SELECT * FROM medicines WHERE user_id = ?", (user["id"],))]
    days_left = domain.stock_days_left(meds)
    return {
        "risk_score": score,
        "risk_level": level,
        "humid_days": sum(d.is_humid for d in days),
        "rainy_days": sum(d.is_rainy for d in days),
        "stock_days_left": None if days_left is None else round(days_left, 1),
        "advice": domain.readiness_advice(level, days_left, HORIZON_DAYS),
        "disclaimer": "Bukan diagnosis; bukan pengganti saran tenaga medis.",
    }


@router.get("/public/risk", tags=["publik"])
def public_risk(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    _key: str = Depends(require_api_key),
):
    """Skor risiko per lokasi untuk kelompok lain (butuh header X-API-Key)."""
    days = _weather_or_503(lat, lon)
    score = domain.risk_score(days, [])
    return {
        "lat": lat,
        "lon": lon,
        "risk_score": score,
        "risk_level": domain.risk_level(score),
        "humid_days": sum(d.is_humid for d in days),
        "rainy_days": sum(d.is_rainy for d in days),
        "horizon_days": HORIZON_DAYS,
    }


app.include_router(router)
