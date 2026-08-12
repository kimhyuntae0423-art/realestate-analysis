"""앱 페이지 설정 + 지역 코드 매핑 (REGIONS, REGION_MAP).

src/ui/shared.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import json
import streamlit as st

from config.settings import ROOT as APP_ROOT

st.set_page_config(page_title="부동산 분석", layout="wide")

with open(APP_ROOT / "config" / "regions.json", encoding="utf-8") as f:
    REGIONS = json.load(f)


def _build_region_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for sido, gus in REGIONS.items():
        for code, name in gus.items():
            out[code] = f"{sido} {name}"
    return out


REGION_MAP = _build_region_map()
