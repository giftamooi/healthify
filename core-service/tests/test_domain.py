from app.domain import (
    DayCondition,
    readiness_advice,
    risk_level,
    risk_score,
    stock_days_left,
)


def days(humidity, rain, n=7):
    return [DayCondition(f"2026-12-0{i+1}", humidity, rain) for i in range(n)]


def test_dry_week_is_low_risk():
    assert risk_level(risk_score(days(60, 0), [])) == "rendah"


def test_wet_humid_week_is_high_risk():
    assert risk_score(days(90, 20), []) == 100
    assert risk_level(100) == "tinggi"


def test_vulnerability_raises_score():
    base = risk_score(days(85, 0), [])          # 60
    boosted = risk_score(days(85, 0), ["asma"])  # 72
    assert boosted > base


def test_stock_days_left_uses_fastest_running_out():
    meds = [
        {"dose_per_intake": 1, "intakes_per_day": 2, "stock_units": 20},  # 10 hari
        {"dose_per_intake": 1, "intakes_per_day": 1, "stock_units": 3},   # 3 hari
    ]
    assert stock_days_left(meds) == 3


def test_advice_warns_when_stock_short_and_risk_high():
    assert "menambah stok" in readiness_advice("tinggi", 3, 7)
    assert "cukup" in readiness_advice("rendah", 3, 7)
