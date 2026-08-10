"""Streamlit 대시보드 공용 헬퍼: 캐시 래퍼, 테이블 렌더링, 사이드바, 공통 입력 폼.

src/ui/streamlit_app.py 에서 분리 (원본 5,078줄 모듈화 1단계).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import pandas as pd
import streamlit as st

from config.settings import ROOT as APP_ROOT, DATABASE_URL
ROOT = APP_ROOT
from src.database.repository import fetch_trades_df
from src.analysis.recommend import (
    recommend_gap_investment, recommend_rental_yield, recommend_buy_outright,
    recommend_investment_focus, region_sentiment_summary,
)
from src.analysis.forecast import forecast_monthly_price
from src.analysis.loan import dsr_loan_capacity_man


@st.cache_data(ttl=600)
def _load_region_coords() -> dict:
    p = APP_ROOT / "config" / "region_coords.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


@st.cache_data(ttl=600, show_spinner="📈 가격 예측 중...")
def _cached_forecast(region_code: str, months_data: int, periods: int) -> pd.DataFrame:
    from datetime import date, timedelta
    df = fetch_trades_df(region_code=region_code,
                         date_from=date.today() - timedelta(days=30 * months_data))
    return forecast_monthly_price(df, periods=periods)


# ─── 추천 함수 캐싱 래퍼 (10분 TTL) ───
# 동일 입력으로 호출 시 DB·계산 생략하여 즉시 반환
@st.cache_data(ttl=600, show_spinner="🔍 추천 계산 중...")
def _cached_gap(seed_man: int, months: int, min_deals: int,
                ownership: str, first_time: bool,
                dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_gap_investment(
        seed_man, months=months,
        min_trade_deals=min_deals, min_rent_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="🔍 추천 계산 중...")
def _cached_yield(seed_man: int, months: int, min_deals: int,
                  ownership: str, first_time: bool, use_loan: bool,
                  dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_rental_yield(
        seed_man, months=months,
        min_trade_deals=min_deals, min_rent_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time, use_loan=use_loan,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="🔍 추천 계산 중...")
def _cached_outright(seed_man: int, months: int, min_deals: int,
                     ownership: str, first_time: bool, use_loan: bool,
                     dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_buy_outright(
        seed_man, months=months, min_trade_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time, use_loan=use_loan,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="🚀 호재·모멘텀 분석 중...")
def _cached_investment(seed_man: int, months: int, min_deals: int,
                        ownership: str, first_time: bool, use_loan: bool,
                        catalyst_weight: float,
                        tier_weight: float = 0.6,
                        prestige_weight: float = 0.10,
                        dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_investment_focus(
        seed_man, months=months, min_trade_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time, use_loan=use_loan,
        catalyst_weight=catalyst_weight, tier_weight=tier_weight,
        prestige_weight=prestige_weight,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="📊 지역별 매수심리 집계 중...")
def _cached_region_sentiment() -> pd.DataFrame:
    return region_sentiment_summary()


@st.cache_data(ttl=1800, show_spinner="📋 거래 내역 로드 중...")
def _cached_all_trades(months: int) -> pd.DataFrame:
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=30 * months)
    return fetch_trades_df(date_from=cutoff)


st.set_page_config(page_title="부동산 분석", layout="wide")

with open(APP_ROOT / "config" / "regions.json", encoding="utf-8") as f:
    REGIONS = json.load(f)


# 컬럼 영문명 → (한국어명, 단위유형)
# 단위유형:
#   "ueok"    : 만원 -> 억원 변환, 소수점 2자리
#   "man"     : 만원 단위, 콤마
#   "ppyeong" : 만원/평 단위, 콤마
#   "area"    : 면적 m²
#   "pct"     : 퍼센트
#   "cnt"     : 거래건수 (콤마 int)
#   "year"    : 연도 (콤마 없음)
#   "raw_int" : 정수, 콤마
#   "txt"     : 문자
COL_SPEC = {
    "naver_url":        ("📲 네이버", "link"),
    "rank":             ("추천순위", "raw_int"),
    "ym":               ("년월", "txt"),
    "deals":            ("거래건수", "cnt"),
    "avg_price":        ("평균매매가", "ueok"),
    "median_price":     ("중위매매가", "ueok"),
    "min_price":        ("최저매매가", "ueok"),
    "max_price":        ("최고매매가", "ueok"),
    "avg_ppp":          ("평당가", "ppyeong"),
    "avg_area_m2":      ("평균전용면적", "area"),
    "avg_price_yoy_%":  ("매매가 전년대비", "pct"),
    "avg_ppp_yoy_%":    ("평당가 전년대비", "pct"),
    "apt_name":         ("단지명", "txt"),
    "build_year":       ("준공연도", "year"),
    "area_bucket":      ("전용면적", "area"),
    "trade_median":     ("매매중위가", "ueok"),
    "trade_count":      ("매매거래수", "cnt"),
    "rent_median":      ("전세환산중위가", "ueok"),
    "rent_count":       ("전월세거래수", "cnt"),
    "gap":              ("갭(매매-전세)", "ueok"),
    "gap_ratio_%":      ("갭비율", "pct"),
    "deposit_median":   ("보증금중위", "ueok"),
    "monthly_median":   ("월세중위", "man"),
    "invest":           ("실투자금", "ueok"),
    "annual_yield_%":   ("연수익률", "pct"),
    "recent_ppp":       ("최근평당가", "ppyeong"),
    "recent_deals":     ("최근거래수", "cnt"),
    "prior_ppp":        ("이전평당가", "ppyeong"),
    "prior_deals":      ("이전거래수", "cnt"),
    "change_%":         ("변동률", "pct"),
    "region":           ("지역", "txt"),
    "opportunities":    ("추천매물수", "cnt"),
    "unique_apts":      ("추천단지수", "cnt"),
    "avg_score":        ("평균점수", "pct"),
    "best_score":       ("최고점수", "pct"),
    "avg_prestige":     ("평균 대장점수", "pct"),
    "n_buyable":        ("매수가능매물수", "cnt"),
    "n_apts":           ("단지수", "cnt"),
    "score":            ("종합점수", "pct"),
    "jeonse_ratio":     ("전세가율", "pct"),
    "value_ratio":      ("저평가비율", "pct"),
    "activity":         ("거래활성도", "cnt"),
    "ppp_median":       ("평당가중위", "ppyeong"),
    "region_median_ppp":("지역평균평당가", "ppyeong"),
    "best_yield_%":     ("최고수익률", "pct"),
    "min_gap":          ("최저갭", "ueok"),
    "min_trade":        ("최저매매가", "ueok"),
    "ltv_%":            ("LTV", "pct"),
    "zone":             ("규제구분", "txt"),
    "loan_capacity":    ("대출가능액", "ueok"),
    "required_equity":  ("필요자기자본", "ueok"),
    "max_buy_price":    ("최대매수가", "ueok"),
    "affordable":       ("매수가능", "txt"),
    "price_growth_%":   ("평당가상승률(분석기간½)", "pct"),
    "leverage":         ("레버리지(배)", "pct"),
    "expected_roi_%":   ("예상자기자본수익률(분석기간½·비연환산)", "pct"),
    "expected_gain":    ("예상평가차익(억·비연환산)", "ueok"),
    "seed_usage_%":     ("시드활용도", "pct"),
    "best_roi_%":       ("최고예상수익률", "pct"),
    "avg_growth_%":     ("평균상승률", "pct"),
    "catalyst_score":   ("호재종합점수", "pct"),
    "manual_catalyst":  ("호재점수(수동)", "pct"),
    "tier_score":       ("상급지등급점수", "pct"),
    "tier_label":       ("급지", "txt"),
    "vol_score":        ("거래량점수", "pct"),
    "new_build_score":  ("신축점수", "pct"),
    "volume_momentum":  ("거래량모멘텀(배)", "pct"),
    "catalysts":        ("등록호재", "txt"),
    "catalyst_text":    ("등록호재", "txt"),
    "sentiment_score":  ("매수심리점수", "pct"),
    "accel_score":      ("가격가속도점수", "pct"),
    "skew_score":       ("고가매수점수", "pct"),
    "price_acceleration_%": ("가격가속도", "pct"),
    "mean_median_skew_%":   ("평균-중위격차", "pct"),
    "avg_sentiment":    ("평균매수심리", "pct"),
    "avg_volume_momentum": ("평균거래량모멘텀(배)", "pct"),
    "avg_accel":        ("평균가격가속도", "pct"),
    "avg_skew":         ("평균고가매수격차", "pct"),
    "n_complexes":      ("단지수", "cnt"),
    "location_score":   ("입지점수(카카오)", "pct"),
    "n_subway":         ("주변지하철", "cnt"),
    "n_school":         ("주변학교", "cnt"),
    "n_mart":           ("주변마트", "cnt"),
    "n_hospital":       ("주변병원", "cnt"),
    "supply_pressure":  ("공급압박지수", "pct"),
    "supply_units":     ("입주물량(호)", "raw_int"),
    "rs_score":            ("단지상대강도점수", "pct"),
    "jeonse_accel_score":  ("전세가율가속도점수", "pct"),
    "jeonse_accel_%p":     ("전세가율가속도(%p)", "pct"),
    "jeonse_quality_score": ("전세가율적정점수", "pct"),
    "jeonse_risk":          ("역전세리스크", "txt"),
    "leverage_mult":        ("갭레버리지(배)", "pct"),
    "supply_pressure_score": ("입주물량점수(역)", "pct"),
    "supply_units_12mo":   ("12개월입주물량(호)", "raw_int"),
    "population_score":    ("인구순유입점수", "pct"),
    "net_inflow_12mo":     ("12개월순유입(명)", "raw_int"),
    # 적정가 분석
    "jeonse_median":    ("전세환산중위가", "ueok"),
    "fair_value":       ("적정가(역산)", "ueok"),
    "fv_premium_%":     ("현재가-적정가(%)", "pct"),
    "verdict":          ("판정", "txt"),
    "annual_rent":      ("연간임대수입", "man"),
    "monthly_median":   ("월세중위", "man"),
    "avg_ppp":          ("평균평당가", "ppyeong"),
    "ma_ppp":           ("이동평균평당가", "ppyeong"),
    "overshoot_%":      ("이동평균대비(%)", "pct"),
    "recent_ppp":       ("최근평당가(단지)", "ppyeong"),
    "total_deals":      ("총거래수", "cnt"),
    # raw trade columns (단지 검색 시)
    "region_code":      ("지역코드", "txt"),
    "deal_date":        ("거래일", "txt"),
    "dong":             ("법정동", "txt"),
    "jibun":            ("지번", "txt"),
    "road_name":        ("도로명", "txt"),
    "area_m2":          ("전용면적", "area"),
    "floor":            ("층", "raw_int"),
    "deal_amount":      ("실거래가", "ueok"),
    "price_per_pyeong": ("평당가", "ppyeong"),
    "deal_year":        ("년", "year"),
    "deal_month":       ("월", "raw_int"),
    "deal_day":         ("일", "raw_int"),
}


def _label_with_unit(name: str, kind: str) -> str:
    # 단위를 두 번째 줄에 넣어 헤더가 좁을 때 자동으로 두 줄 표시되게 함
    return {
        "ueok":    f"{name}\n(억원)",
        "man":     f"{name}\n(만원)",
        "ppyeong": f"{name}\n(만원/평)",
        "area":    f"{name}\n(㎡)",
        "pct":     f"{name}\n(%)",
        "cnt":     f"{name}",
        "year":    f"{name}",
        "raw_int": f"{name}",
        "txt":     f"{name}",
        "link":    f"{name}",
    }[kind]


def _column_config(label: str, kind: str):
    NumberColumn = st.column_config.NumberColumn
    fmt = {
        "ueok":    "%.2f",
        "man":     "%,d",
        "ppyeong": "%,d",
        "area":    "%.1f",
        "pct":     "%.2f",
        "cnt":     "%,d",
        "year":    "%d",
        "raw_int": "%,d",
    }
    if kind == "txt":
        return None
    if kind == "link":
        return st.column_config.LinkColumn(
            label=label, display_text="🔗 보기", width="small",
            help="네이버 부동산 검색 결과로 이동",
        )
    return NumberColumn(label=label, format=fmt[kind])


_HIDDEN_COLS = {"region_code"}  # 사용자에게 노출 안 함


def _simplify_apt_name(name: str) -> str:
    """단지명을 검색 친화적으로 정리.

    - 괄호 부가설명 제거: "(101동102동)", "(영동한양)" 등
    - 영문↔한글 경계, camelCase 경계에 공백 삽입: "운서SKVIEWSkycity" → "운서 SKVIEW Skycity"
    - 잡음 문자 정리
    """
    import re
    s = str(name)
    # 괄호 부가설명 제거
    s = re.sub(r"\([^)]*\)", "", s)
    # 한글-영문 경계 공백
    s = re.sub(r"([가-힣])([A-Za-z])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])([가-힣])", r"\1 \2", s)
    # 한글-숫자 경계 공백 (예: "동탄2신도시" 유지 — 숫자가 한글 사이일 때만; "현대14차" 유지)
    # → 굳이 안 함. 식별자 보존.
    # camelCase 경계: 소문자→대문자, 또는 대문자가 소문자로 시작하는 단어 앞 (Skycity, SKVIEW)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)        # "Skycity" → 그대로 (s→k는 안 잡힘)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)  # "SKVIEWSkycity" → "SKVIEW Skycity"
    # 잡음 문자
    s = re.sub(r"[·∙•．,\.]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def naver_land_url(region: str | None, apt_name: str | None) -> str | None:
    """네이버 통합검색(모바일) URL — 부동산 패널이 자동으로 매칭되어 단지 정보·매물 노출.

    검색어 = '{시군구 마지막 단어} {동} {정리된 단지명}'.
    m.land.naver.com 직링보다 통합검색이 매칭 관대 + fallback(웹문서/지도) 자동 제공.
    """
    if not apt_name:
        return None
    import urllib.parse as _ul
    clean = _simplify_apt_name(apt_name)
    tokens = []
    if region:
        toks = str(region).strip().split()
        if toks:
            # 시군구 표시명 마지막 단어가 동이면 '시군구 두번째 + 동', 아니면 시군구 마지막만
            last = toks[-1]
            if any(last.endswith(suf) for suf in ("동", "읍", "면", "리", "가")):
                # 마지막이 동/읍/면 → 그 직전(구/시) + 동 함께 사용
                if len(toks) >= 2:
                    tokens.append(toks[-2])
                tokens.append(last)
            else:
                tokens.append(last)
    tokens.append(clean)
    q = " ".join(t for t in tokens if t)
    enc = _ul.quote(q, safe="")
    return f"https://m.search.naver.com/search.naver?query={enc}"


def render_table(df: pd.DataFrame, height: int | None = None):
    """영문 컬럼 → 한국어 + 단위 + 포맷, HTML 테이블로 가운데 정렬 출력."""
    if df is None or df.empty:
        st.info("표시할 데이터가 없습니다.")
        return
    out = df.copy()
    drop_cols = [c for c in out.columns if c in _HIDDEN_COLS]
    if drop_cols:
        out = out.drop(columns=drop_cols)

    col_labels: list[str] = []
    col_kinds: list[str] = []
    for col in out.columns:
        spec = COL_SPEC.get(col)
        if spec:
            name, kind = spec
            if kind == "ueok" and pd.api.types.is_numeric_dtype(out[col]):
                out[col] = (out[col].astype(float) / 10000.0).round(2)
        else:
            name, kind = col, "txt"
        col_labels.append(_label_with_unit(name, kind))
        col_kinds.append(kind)

    _TH = "style='background:#f1f5f9;color:#374151;padding:7px 10px;text-align:center;border-bottom:2px solid #cbd5e1;white-space:nowrap;font-weight:600;border:1px solid #e2e8f0'"
    _TD = "style='padding:5px 10px;border-bottom:1px solid #e2e8f0;text-align:center;white-space:nowrap'"
    _TD_E = "style='padding:5px 10px;border-bottom:1px solid #e2e8f0;text-align:center;white-space:nowrap;background:#f9fafb'"

    def _fmt(val, kind: str) -> str:
        try:
            if val is None or pd.isna(val):
                return "—"
        except Exception:
            pass
        if kind == "link":
            return f"<a href='{val}' target='_blank' style='color:#2563eb;text-decoration:none'>🔗 보기</a>" if val else "—"
        if kind in ("ueok", "pct", "area"):
            try:
                return f"{float(val):,.2f}"
            except Exception:
                return str(val)
        if kind in ("man", "ppyeong", "cnt", "raw_int"):
            try:
                return f"{int(float(val)):,}"
            except Exception:
                return str(val)
        if kind == "year":
            try:
                return f"{int(float(val))}"
            except Exception:
                return str(val)
        return str(val)

    header_row = "<tr>" + "".join(
        f"<th {_TH}>{lbl.replace(chr(10), '<br>')}</th>" for lbl in col_labels
    ) + "</tr>"

    body_rows = []
    for i, (_, row) in enumerate(out.iterrows()):
        td = _TD_E if i % 2 else _TD
        cells = "".join(
            f"<td {td}>{_fmt(row[col], kind)}</td>"
            for col, kind in zip(out.columns, col_kinds)
        )
        body_rows.append(f"<tr>{cells}</tr>")

    scroll = f"max-height:{height}px;overflow-y:auto;" if height else ""
    tbl_style = "style='width:100%;border-collapse:collapse;font-size:13px'"
    st.markdown(
        f"<div style='{scroll}overflow-x:auto'>"
        f"<table {tbl_style}><thead>{header_row}</thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_df(df: pd.DataFrame, height: int | None = None, **_):
    """일반 DataFrame을 가운데 정렬 HTML 테이블로 출력 (st.dataframe 대체)."""
    if df is None or df.empty:
        st.info("표시할 데이터가 없습니다.")
        return
    _TH = "style='background:#f1f5f9;color:#374151;padding:7px 10px;text-align:center;border:1px solid #e2e8f0;white-space:nowrap;font-weight:600'"
    _TD = "style='padding:5px 10px;border-bottom:1px solid #e2e8f0;text-align:center;white-space:nowrap'"
    _TD_E = "style='padding:5px 10px;border-bottom:1px solid #e2e8f0;text-align:center;white-space:nowrap;background:#f9fafb'"

    def _v(v):
        try:
            if pd.isna(v): return "—"
        except Exception:
            pass
        return str(v) if v is not None else "—"

    header = "<tr>" + "".join(f"<th {_TH}>{c}</th>" for c in df.columns) + "</tr>"
    rows = []
    for i, (_, row) in enumerate(df.iterrows()):
        td = _TD_E if i % 2 else _TD
        rows.append("<tr>" + "".join(f"<td {td}>{_v(row[c])}</td>" for c in df.columns) + "</tr>")

    scroll = f"max-height:{height}px;overflow-y:auto;" if height else ""
    st.markdown(
        f"<div style='{scroll}overflow-x:auto'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:13px'>"
        f"<thead>{header}</thead><tbody>{''.join(rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _data_freshness() -> dict:
    """각 데이터의 마지막 갱신 시점 + 경과일."""
    import json as _json
    from datetime import date as _date
    from sqlalchemy import text
    from src.database.models import engine as _engine
    out = {}
    try:
        with _engine.connect() as conn:
            for tbl, col, label in [
                ("apt_trade", "deal_date", "실거래 매매"),
                ("apt_rent", "deal_date", "실거래 전월세"),
            ]:
                try:
                    row = conn.execute(
                        text(f"SELECT MAX({col}), COUNT(*) FROM {tbl}")
                    ).fetchone()
                    last, n = row
                    if last:
                        d = _date.fromisoformat(str(last)[:10])
                        out[label] = {
                            "last": d, "days_ago": (_date.today() - d).days, "rows": n,
                        }
                    else:
                        out[label] = {"last": None, "days_ago": None, "rows": 0}
                except Exception:
                    out[label] = {"last": None, "days_ago": None, "rows": 0}
    except Exception:
        pass
    # config 파일
    for fname, label in [("catalysts.json", "호재(catalysts)"),
                         ("region_tiers.json", "등급(tiers)"),
                         ("supply.json", "수동 공급(supply)")]:
            try:
                with open(ROOT / "config" / fname, encoding="utf-8") as f:
                    j = _json.load(f)
                upd = j.get("_meta", {}).get("updated", "?")
                out[label] = {"last": upd, "days_ago": None, "rows": None}
            except Exception:
                out[label] = {"last": "?", "days_ago": None, "rows": None}
    return out


def _refresh_recent_data(months: int = 3, regions: list[str] | None = None,
                          do_supply: bool = False) -> dict:
    """원클릭 데이터 갱신.

    1) 국토부 실거래(매매·전월세): 모든 보유 시군구의 최근 N개월 (incremental upsert)
    2) (옵션) KOSIS 입주물량 — 2026-05 시뮬레이션 후 점수 산식에서 제외됨. default off.
    인구이동·호재·등급은 수동 (KOSIS CSV / JSON 편집).
    """
    import sqlite3
    from datetime import date as _date
    from src.collectors.molit_api import MolitCollector
    from src.database.repository import upsert_trades, upsert_rents
    from src.collectors.kosis_api import KosisCollector
    summary = {"trade": 0, "rent": 0, "supply": 0, "errors": []}

    # 1) 최근 N개월 ymd 리스트
    today = _date.today()
    ymds = []
    y, m = today.year, today.month
    for _ in range(months):
        ymds.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    ymds = list(reversed(ymds))

    # 2) 보유 시군구
    if regions is None:
        conn = sqlite3.connect(str(DATABASE_URL).replace("sqlite:///", ""))
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT region_code FROM apt_trade ORDER BY region_code")
        regions = [r[0] for r in cur.fetchall()]
        conn.close()

    # 3) 국토부 수집 (시군구 × 월)
    try:
        mc = MolitCollector()
    except Exception as e:
        summary["errors"].append(f"MOLIT 키 미설정: {e}")
        return summary

    prog = st.progress(0.0, text="국토부 실거래 수집 시작…")
    total = len(regions) * len(ymds)
    done = 0
    for region in regions:
        for ymd in ymds:
            try:
                rows = mc.fetch_trades(region, ymd)
                ins_t = upsert_trades(rows)
                summary["trade"] += ins_t
                rows = mc.fetch_rents(region, ymd)
                ins_r = upsert_rents(rows)
                summary["rent"] += ins_r
            except Exception as e:
                summary["errors"].append(f"{region}/{ymd}: {e}")
            done += 1
            prog.progress(done / total, text=f"실거래 {region} {ymd} ({done}/{total})")
    prog.empty()

    # 4) KOSIS 입주물량 (시도 17개 × 최근 12개월)
    if do_supply:
        try:
            from src.database.models import SupplySchedule, SessionLocal
            from src.database.repository import _make_upsert
            col = KosisCollector()
            today = _date.today()
            y, m = today.year, today.month
            for _ in range(11):
                m -= 1
                if m == 0:
                    m = 12; y -= 1
            start_ym = f"{y:04d}{m:02d}"
            end_ym = f"{today.year:04d}{today.month:02d}"
            rows = col.fetch_supply_schedule(start_ym, end_ym)
            if rows:
                payload = []
                for r in rows:
                    region = r.get("C1") or ""
                    ym = r.get("PRD_DE") or ""
                    units = int(float(r.get("DT") or 0))
                    if not region or len(region) != 2 or units <= 0:
                        continue
                    payload.append({
                        "region_code": region,
                        "move_in_date": _date(int(ym[:4]), int(ym[4:6]), 1),
                        "units": units, "source": "kosis_sido",
                    })
                if payload:
                    with SessionLocal() as s:
                        stmt = _make_upsert(SupplySchedule, payload)
                        s.execute(stmt)
                        s.commit()
                    summary["supply"] = len(payload)
        except Exception as e:
            summary["errors"].append(f"KOSIS 공급: {e}")

    return summary


def _sidebar_nav() -> str:
    """사이드바: 페이지 네비게이션 + 캐시 클리어 + 데이터 최신화. 모든 페이지 공통."""
    with st.sidebar:
        if "_nav_section" not in st.session_state:
            st.session_state["_nav_section"] = "analysis"

        def _on_analysis_nav():
            st.session_state["_nav_section"] = "analysis"

        _sec = st.session_state["_nav_section"]

        # ── 섹션 1: 부동산 분석 ──────────────────────────────
        st.markdown("#### 🏠 부동산 분석")
        page_radio = st.radio(
            "페이지",
            ["💰 나의 한도", "🚀 투자 추천", "💎 저평가 매물", "📊 지역 분석", "🗺️ 지도", "🚦 시장 진단"],
            label_visibility="collapsed",
            key="nav_page",
            on_change=_on_analysis_nav,
        )

        # ── 섹션 2: 도구 ─────────────────────────────────────
        st.markdown("#### 🛠️ 도구")
        if st.button(
            "🔬 전략 백테스트",
            use_container_width=True,
            key="nav_backtest",
            type="primary" if _sec == "backtest" else "secondary",
        ):
            st.session_state["_nav_section"] = "backtest"
            st.rerun()

        if st.button(
            "🏘️ 처분·매수 전략 플래너",
            use_container_width=True,
            key="nav_portfolio",
            type="primary" if _sec == "portfolio" else "secondary",
        ):
            st.session_state["_nav_section"] = "portfolio"
            st.rerun()

        if st.session_state["_nav_section"] == "backtest":
            page = "🔬 전략 백테스트"
        elif st.session_state["_nav_section"] == "portfolio":
            page = "🏘️ 처분·매수 전략"
        else:
            page = page_radio

        # ── 섹션 3: 유틸 ─────────────────────────────────────
        st.markdown("#### ⚙️ 유틸")
        if st.button("🔄 캐시 비우기", use_container_width=True, key="nav_clear",
                     help="데이터 수집 후 또는 강제 재계산 시"):
            st.cache_data.clear()
            st.success("캐시 비움")

        with st.expander("🗓️ 데이터 최신화", expanded=False):
            fresh = _data_freshness()
            st.caption("권장 주기: **분기 1회**")
            for label, info in fresh.items():
                last = info.get("last")
                days = info.get("days_ago")
                if isinstance(last, str):
                    # config 파일
                    icon = "📝"
                    line = f"{icon} **{label}**: {last[:30]}"
                elif last is None:
                    icon = "❌"
                    line = f"{icon} **{label}**: 데이터 없음"
                else:
                    if days is not None and days <= 30:
                        icon = "✅"
                    elif days is not None and days <= 90:
                        icon = "🟡"
                    else:
                        icon = "🔴"
                    line = f"{icon} **{label}**: {last} ({days}일 전)"
                st.caption(line)

            st.markdown("")
            # 시/도 선택 (첫 수집 또는 특정 지역만 갱신)
            sido_options = list(REGIONS.keys())
            selected_sido = st.multiselect(
                "수집할 시/도 선택", sido_options, default=[],
                key="nav_sido_select",
                help="비워두면 DB에 있는 기존 지역만 갱신. 처음엔 원하는 시/도를 선택하세요.",
            )
            selected_regions = None
            if selected_sido:
                selected_regions = [
                    code for s in selected_sido
                    for code in REGIONS.get(s, {}).keys()
                ]

            if st.button("🔄 데이터 수집 (최근 3개월)",
                         width='stretch', type="primary", key="nav_refresh"):
                with st.spinner("국토부 실거래 수집 중… 5~10분 소요"):
                    res = _refresh_recent_data(months=3, do_supply=False,
                                               regions=selected_regions)
                msg = f"✅ 매매 {res['trade']:,}건 / 전월세 {res['rent']:,}건 신규 upsert"
                st.success(msg)
                if res["errors"]:
                    st.error(f"⚠️ {len(res['errors'])}개 오류:\n" + "\n".join(res["errors"][:5]))
                st.cache_data.clear()

            st.caption(
                "**자동 갱신**\n"
                "• 실거래 매매·전월세 (국토부 API) ← 점수 산정에 사용\n\n"
                "**수동 갱신**\n"
                "• 호재(`config/catalysts.json`): GTX·신도시 확정 시 직접 편집\n"
                "• 등급(`config/region_tiers.json`): 정보 표시용 (점수 산식 X)\n"
                "• 대출규제(`config/loan_regulations.json`): 변경 감지 시 확인 후 직접 편집\n\n"
                "**중단된 수집** (점수 산식에서 제외됨)\n"
                "• KOSIS 입주물량·인구이동 → 백테스트 결과 효과 없음"
            )

            # ── 규제 뉴스 변경 감지 알림 ──
            try:
                from src.collectors.regulation_news import load_regulation_news
                _reg = load_regulation_news()
            except Exception:
                _reg = None
            if _reg and _reg.get("count", 0) > 0:
                st.markdown("")
                with st.expander(
                    f"⚠️ 규제 관련 뉴스 {_reg['count']}건 감지 "
                    f"(수집일: {_reg.get('collected_at', '')})",
                    expanded=False,
                ):
                    st.caption(
                        "자동 반영 **아님** — 내용 확인 후 "
                        "`config/loan_regulations.json` 직접 수정하세요."
                    )
                    for _art in _reg["articles"][:10]:
                        st.markdown(
                            f"- [{_art['datetime']}] [{_art['title']}]({_art['url']})"
                        )

        with st.expander("📜 개발 히스토리", expanded=False):
            st.markdown(
                """
**v0.1 — 초기 시스템 (2026-05)**
- 호재 + 상급지(tier) + 다양한 선행지표(전세가율·인구·공급·RS) 종합 점수
- 사용자가 슬라이더로 호재·tier 가중치 조절

**v0.2 — KOSIS 데이터 통합**
- 인구이동·입주물량(시도 단위) 추가 → 시도 단위 입주물량을 시군구로 분배
- 화성시 4구 분구 코드(41591/93/95/97) 발견 후 별도 수집

**v0.3 — prestige 시그널 (시군구 내 대장 단지)**
- 단지 평당가가 시군구 평균 대비 얼마나 높은지 백분위
- 대장 아파트 가산점

**v0.4 — market 시그널 (시군구 자체의 시장가치)**
- 시군구 중위 평당가의 전국 백분위
- tier(규제 기준)가 못 잡는 시장 평가 보완 (마포 80→93)

**v0.5 — 호재 슬라이더 통합**
- 호재 점수를 region_score에 가산하는 강도로 재정의
- 평택처럼 시장가 낮지만 잠재력 큰 곳 발굴 도구

**v1.0 — 단순화 (현재, 다중 시점 백테스트 기반)**
- 핵심 결과: **"좋은 동네의 대장 단지가 가장 잘 오른다"** (마태 효과 ρ +0.62)
- **저평가 가설 데이터로 기각** — 평당가 낮은 곳이 더 안 오름 (ρ -0.61)
- 최종 점수 = `market 70% + prestige 30% + 호재 가산`
- 제외된 신호: tier(약), jeonse_accel(역상관), population(역상관), supply_pressure(약)
- tier·jeonse·population·supply는 데이터 수집 또는 점수 산식에서 제외
                """
            )
            st.caption("자세한 백테스트 결과/메서드는 별도 메모리에 저장됨.")

        st.caption(
            "각 페이지가 자체 입력을 가집니다.\n\n"
            "💰 한도 = 시드/소득 기반 매수가\n"
            "🚀 추천 = 매물 검색\n"
            "📊 지역 = 단일 시군구 시계열\n"
            "🗺️ 지도 = 전국 시각화\n"
            "🚦 진단 = 시장 환경\n"
            "🔬 백테스트 = 전략별 예측력 검증"
        )
    return page


def _personal_inputs_block(key_prefix: str = "p") -> dict:
    """개인 정보 입력 블록 (한도/추천 페이지 공용).

    레이아웃: 3개 섹션 (자금 · 가구 · 대출 조건). 각 섹션은 3 컬럼 동일 그리드.
    """
    # ── 자금 ──────────────────────────────────────────
    st.markdown("**💰 자금**")
    c1, c2, c3 = st.columns(3)
    seed_eok = c1.number_input(
        "자기자본 시드 (억원)", min_value=0.1, max_value=200.0,
        value=2.5, step=0.5, format="%.1f", key=f"{key_prefix}_seed",
    )
    annual_income = c2.number_input(
        "본인 연소득 (만원)", min_value=0, max_value=100000,
        value=7500, step=500, key=f"{key_prefix}_inc",
        help="세전 연소득",
    )
    is_couple = c3.checkbox(
        "💑 기혼 (부부합산 소득 적용)", value=False, key=f"{key_prefix}_couple",
        help="체크 시 DSR·정책대출에 부부합산 소득 사용",
    )
    if is_couple:
        c1b, c2b, c3b = st.columns(3)
        spouse_income = c2b.number_input(
            "배우자 연소득 (만원)", min_value=0, max_value=100000,
            value=0, step=500, key=f"{key_prefix}_spouse",
        )
    else:
        spouse_income = 0

    # ── 가구 ──────────────────────────────────────────
    st.markdown("**👨‍👩‍👧 가구 정보**")
    c1, c2, c3 = st.columns(3)
    ownership = c1.selectbox(
        "보유 주택 수", ["무주택", "1주택", "다주택"], key=f"{key_prefix}_own",
    )
    children = c2.number_input(
        "자녀 수", min_value=0, max_value=10, value=0, key=f"{key_prefix}_kids",
        help="2명 이상이면 정책대출 한도 우대",
    )
    with c3:
        first_time = st.checkbox(
            "생애최초 구매", key=f"{key_prefix}_ft",
            help="LTV +20%p 우대",
        )
        is_newlywed = st.checkbox(
            "🎀 신혼부부 (혼인 7년 이내)", key=f"{key_prefix}_new",
            disabled=not is_couple,
            help="기혼인 경우만. 정책대출 우대",
        )

    # ── 대출 조건 ────────────────────────────────────
    st.markdown("**🏦 대출 조건**")
    c1, c2, c3 = st.columns(3)
    interest_rate = c1.slider(
        "대출 금리 (%)", 2.0, 8.0, 4.5, 0.1, key=f"{key_prefix}_rate",
        help="신청 시점 명목 금리",
    )
    existing_debt_monthly = c2.number_input(
        "기존 부채 월 원리금 (만원)", min_value=0, max_value=2000,
        value=0, step=10, key=f"{key_prefix}_debt",
        help="신용·차·카드 등 월 원리금 합",
    )
    with c3:
        use_loan = st.checkbox(
            "대출 사용", value=True, key=f"{key_prefix}_loan",
            help="갭투자는 무관 (전세=임차인 부담)",
        )
        use_dsr = st.checkbox(
            "DSR 40% 적용", value=True, key=f"{key_prefix}_dsr",
            help="체크 권장. 미체크 시 LTV/한도cap만",
        )
    # KB시세 보정
    kbc1, kbc2 = st.columns([3, 2])
    kb_direct_eok = kbc1.number_input(
        "KB시세 직접 입력 (억원)", min_value=0.0, max_value=300.0,
        value=0.0, step=0.5, format="%.1f", key=f"{key_prefix}_kb_direct",
        help="KB부동산 앱 → 단지 검색 → 시세 탭. 은행은 이 값 기준으로 LTV 계산. 0이면 오른쪽 비율 보정 사용.",
    )
    kb_ratio_pct = kbc2.slider(
        "KB시세/실거래가 (%)", min_value=75, max_value=100, value=90, step=1,
        key=f"{key_prefix}_kb",
        help="직접 입력이 없을 때 일괄 보정값. 통상 90~97%.",
    )
    kb_ratio = kb_ratio_pct / 100
    kb_direct_man = int(kb_direct_eok * 10000) if kb_direct_eok > 0 else 0

    # 합산 소득 (DSR/정책대출 기준)
    household_income = annual_income + (spouse_income if is_couple else 0)

    # DSR 한도 즉시 계산 (가구 소득 기준)
    dsr_cap_man = None
    if use_dsr:
        dsr_cap_man = dsr_loan_capacity_man(
            annual_income_man=household_income,
            existing_monthly_payment_man=existing_debt_monthly,
            interest_rate_pct=interest_rate,
            dsr_limit_pct=40,
        )

    return dict(
        seed_eok=seed_eok, seed_man=int(seed_eok * 10000),
        ownership=ownership, first_time=first_time, use_loan=use_loan,
        annual_income=annual_income, spouse_income=spouse_income,
        household_income=household_income,
        is_couple=is_couple, is_newlywed=is_newlywed, children=children,
        existing_debt_monthly=existing_debt_monthly,
        interest_rate=interest_rate, use_dsr=use_dsr,
        dsr_cap_man=dsr_cap_man,
        kb_ratio=kb_ratio, kb_ratio_pct=kb_ratio_pct,
        kb_direct_man=kb_direct_man,
    )
