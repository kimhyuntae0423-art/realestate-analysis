"""src/parsers/price_parser.py — 국토부 API 응답 파싱 검증."""
from __future__ import annotations

from datetime import date

from src.parsers.price_parser import parse_trade_item, parse_rent_item, PYEONG


def test_parse_trade_item_basic_fields():
    item = {
        "dealYear": "2025", "dealMonth": "6", "dealDay": "15",
        "aptNm": " 래미안강남 ", "umdNm": "역삼동", "jibun": "123-4",
        "roadNm": "테헤란로", "excluUseAr": "84.99", "floor": "10",
        "buildYear": "2015", "dealAmount": "150,000",
    }
    out = parse_trade_item(item, region_code="11680")
    assert out["deal_date"] == date(2025, 6, 15)
    assert out["apt_name"] == "래미안강남"
    assert out["deal_amount"] == 150000
    assert out["area_m2"] == 84.99
    assert out["price_per_pyeong"] == int(150000 / (84.99 / PYEONG))


def test_parse_trade_item_uses_alias_fields_when_primary_missing():
    item = {
        "dealYear": "2025", "dealMonth": "6", "dealDay": "1",
        "apartmentName": "자이", "excluUseAr": "59.9", "tradeAmount": "80000",
    }
    out = parse_trade_item(item, region_code="11680")
    assert out["apt_name"] == "자이"
    assert out["deal_amount"] == 80000


def test_parse_trade_item_zero_area_avoids_division_by_zero():
    item = {"dealYear": "2025", "dealMonth": "1", "dealDay": "1",
            "aptNm": "A", "excluUseAr": "0", "dealAmount": "50000"}
    out = parse_trade_item(item, region_code="11680")
    assert out["price_per_pyeong"] == 0


def test_parse_trade_item_missing_optional_fields_default_empty():
    item = {"dealYear": "2025", "dealMonth": "1", "dealDay": "1",
            "aptNm": "A", "excluUseAr": "84.9", "dealAmount": "100000"}
    out = parse_trade_item(item, region_code="11680")
    assert out["dong"] == ""
    assert out["cancel_deal_type"] == ""


def test_parse_rent_item_jeonse_and_wolse():
    jeonse = parse_rent_item({
        "dealYear": "2025", "dealMonth": "3", "dealDay": "10",
        "aptNm": "A", "excluUseAr": "84.9", "deposit": "70,000", "monthlyRent": "0",
    }, region_code="11680")
    assert jeonse["deposit"] == 70000
    assert jeonse["monthly_rent"] == 0

    wolse = parse_rent_item({
        "dealYear": "2025", "dealMonth": "3", "dealDay": "10",
        "aptNm": "A", "excluUseAr": "84.9", "deposit": "10,000", "monthlyRent": "80",
    }, region_code="11680")
    assert wolse["monthly_rent"] == 80


def test_parse_rent_item_malformed_numeric_string_falls_back_to_default():
    item = {"dealYear": "2025", "dealMonth": "1", "dealDay": "1",
            "aptNm": "A", "excluUseAr": "84.9", "deposit": "N/A", "monthlyRent": "-"}
    out = parse_rent_item(item, region_code="11680")
    assert out["deposit"] == 0
    assert out["monthly_rent"] == 0
