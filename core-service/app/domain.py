"""Logika inti Healther (subdomain core): skor risiko musiman + kesiapan stok.

Sengaja berupa fungsi murni (tanpa database/HTTP) supaya mudah diuji dan
menjadi tempat aturan bisnis dari makalah DDD.
"""
from dataclasses import dataclass

HUMID_DAY_THRESHOLD = 80      # % kelembaban rata-rata -> "hari lembab"
RAINY_DAY_THRESHOLD_MM = 10   # mm curah hujan -> "hari hujan lebat"
VULNERABILITY_BOOST = 1.2     # pengguna rentan -> skor x1.2 (maks 100)


@dataclass(frozen=True)
class DayCondition:
    """Istilah domain kita sendiri (hasil terjemahan dari data Open-Meteo)."""
    date: str
    humidity_mean: float
    rain_mm: float

    @property
    def is_humid(self) -> bool:
        return self.humidity_mean >= HUMID_DAY_THRESHOLD

    @property
    def is_rainy(self) -> bool:
        return self.rain_mm >= RAINY_DAY_THRESHOLD_MM


def risk_score(days: list[DayCondition], vulnerabilities: list[str]) -> int:
    """Skor 0-100. Makin banyak hari lembab/hujan, makin tinggi."""
    if not days:
        return 0
    humid_ratio = sum(d.is_humid for d in days) / len(days)
    rainy_ratio = sum(d.is_rainy for d in days) / len(days)
    score = 100 * (0.6 * humid_ratio + 0.4 * rainy_ratio)
    if vulnerabilities:
        score *= VULNERABILITY_BOOST
    return min(100, round(score))


def risk_level(score: int) -> str:
    if score >= 67:
        return "tinggi"
    if score >= 34:
        return "sedang"
    return "rendah"


def stock_days_left(medicines: list[dict]) -> float | None:
    """Sisa hari stok untuk obat yang paling cepat habis. None bila tak ada obat."""
    left = []
    for m in medicines:
        daily_use = m["dose_per_intake"] * m["intakes_per_day"]
        if daily_use > 0:
            left.append(m["stock_units"] / daily_use)
    return min(left) if left else None


def readiness_advice(level: str, days_left: float | None, horizon_days: int) -> str:
    if days_left is None:
        return "Belum ada obat rutin yang dicatat."
    if level != "rendah" and days_left < horizon_days:
        return (
            f"Risiko {level} diperkirakan dalam {horizon_days} hari ke depan, "
            f"sedangkan stok obat hanya cukup sekitar {days_left:.0f} hari. "
            "Pertimbangkan menambah stok sebelum periode rawan."
        )
    return "Stok obat cukup untuk periode ini."
