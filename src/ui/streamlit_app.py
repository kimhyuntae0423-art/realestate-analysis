"""Streamlit 부동산 분석 대시보드

실행: streamlit run src/ui/streamlit_app.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import plotly.express as px

from config.settings import ROOT as APP_ROOT, DATABASE_URL
ROOT = APP_ROOT
from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.price_trend import monthly_summary, apt_summary, yoy_change
from src.analysis.gap_analysis import gap_table
from src.analysis.yield_calc import rental_yield
from src.analysis.ranking import region_ranking, apt_growth
from src.analysis.recommend import (
    recommend_gap_investment, recommend_rental_yield, recommend_buy_outright,
    recommend_investment_focus, region_sentiment_summary,
)
from src.analysis.forecast import forecast_monthly_price
from src.analysis.supply import supply_for_region, supply_pressure_score, supply_table
from src.analysis.location import is_kakao_ready, enrich_with_location
from src.analysis.costs import total_acquisition_cost_man, best_policy_loan
from src.analysis.scenario import project_5y_scenarios, stress_test
from src.analysis.macro import macro_dashboard
from src.analysis.loan import (
    dsr_loan_capacity_man, max_purchase_man as calc_max_purchase,
    loan_capacity_man, get_ltv_pct, get_zone,
)


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
    "price_growth_%":   ("평당가상승률", "pct"),
    "leverage":         ("레버리지(배)", "pct"),
    "expected_roi_%":   ("예상자기자본수익률", "pct"),
    "expected_gain":    ("예상평가차익", "ueok"),
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
    """영문 컬럼 → 한국어 + 단위 + 콤마 포맷으로 변환하여 출력."""
    if df is None or df.empty:
        st.info("표시할 데이터가 없습니다.")
        return
    out = df.copy()
    # 사용자 노출 금지 컬럼 제거
    drop_cols = [c for c in out.columns if c in _HIDDEN_COLS]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    rename = {}
    cfg = {}
    for col in out.columns:
        spec = COL_SPEC.get(col)
        if not spec:
            rename[col] = col
            continue
        name, kind = spec
        # 만원 → 억원 변환
        if kind == "ueok" and pd.api.types.is_numeric_dtype(out[col]):
            out[col] = (out[col].astype(float) / 10000.0).round(2)
        label = _label_with_unit(name, kind)
        rename[col] = label
        col_cfg = _column_config(label, kind)
        if col_cfg is not None:
            cfg[label] = col_cfg
    out = out.rename(columns=rename)
    kwargs = {"width": "stretch", "column_config": cfg}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(out, **kwargs)


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
        st.markdown("## 🏠 부동산 분석")
        page = st.radio(
            "페이지",
            [
                "🏠 나의 한도",
                "🚀 투자 추천",
                "📊 지역 분석",
                "🗺️ 지도",
                "🚦 시장 진단",
                "🔬 전략 백테스트",
            ],
            label_visibility="collapsed",
            key="nav_page",
        )
        st.divider()
        if st.button("🔄 캐시 비우기", width='stretch', key="nav_clear",
                     help="데이터 수집 후 또는 강제 재계산 시"):
            st.cache_data.clear()
            st.success("캐시 비움")

        # ── 데이터 최신화 섹션 ──────────────────────────────
        st.divider()
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
                "• 호재(`config/catalysts.json`): GTX·신도시 확정 시 직접 편집 → 호재 슬라이더에 자동 반영\n"
                "• 등급(`config/region_tiers.json`): 정보 표시용 (점수 산식 X)\n\n"
                "**중단된 수집** (점수 산식에서 제외됨)\n"
                "• KOSIS 입주물량·인구이동 → 백테스트 결과 효과 없음"
            )

        # ── 개발 히스토리 ─────────────────────────────────
        st.divider()
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

        st.divider()
        st.caption(
            "각 페이지가 자체 입력을 가집니다.\n\n"
            "🏠 한도 = 시드/소득 기반 매수가\n"
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
        value=5.0, step=0.5, format="%.1f", key=f"{key_prefix}_seed",
    )
    annual_income = c2.number_input(
        "본인 연소득 (만원)", min_value=0, max_value=100000,
        value=6000, step=500, key=f"{key_prefix}_inc",
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
    )


def page_my_capacity():
    """🏠 나의 한도 — 시드+대출+정책대출+부대비용 시뮬."""
    st.title("🏠 나의 매수 한도")
    st.caption("자기자본·소득·LTV·DSR·정책대출·부대비용을 모두 반영한 최대 매수가")

    with st.container(border=True):
        st.markdown("##### 입력")
        p = _personal_inputs_block(key_prefix="cap")

    if p["use_dsr"] and p["dsr_cap_man"] is not None:
        st.info(f"💳 DSR 대출 한도 산정: **{p['dsr_cap_man']/10000:.2f} 억** "
                f"(연소득 {p['annual_income']:,}만 / 금리 {p['interest_rate']}% / 스트레스+3%)")

    # 헤드라인 카드 (기존 함수 재활용)
    inputs_compat = {
        "seed_eok": p["seed_eok"],
        "ownership": p["ownership"],
        "first_time": p["first_time"],
        "annual_income": p["annual_income"],
    }
    _render_headline_card(inputs_compat, p["seed_man"], p["dsr_cap_man"])

    # 추가 안내
    st.markdown("---")
    st.markdown("### ℹ️ 어떻게 활용하나요?")
    st.markdown(
        "- **나의 한도** 페이지: 본인 자금으로 어디까지 살 수 있는지 한눈에 파악\n"
        "- **🚀 투자 추천** 페이지: 위 한도 내 실제 매물 후보 검색\n"
        "- **📊 지역 분석** 페이지: 관심 지역 시세 추이·갭·수익률 등 깊이 분석\n"
        "- **🗺️ 지도**: 전국 평당가·거래량 시각적 비교\n"
        "- **🚦 시장 진단**: 매크로 환경 · 지역별 매수심리"
    )


def page_invest():
    """🚀 투자 추천 - 시드+대출 기반 전국 매수 매물 검색."""
    st.title("🚀 투자 추천")
    st.caption("자기자본 + 대출(LTV/한도cap/DSR)로 매수 가능한 매물 중 미래 상승 잠재력 상위 단지 추천")

    with st.container(border=True):
        st.markdown("##### 👤 매수자 조건")
        p = _personal_inputs_block(key_prefix="inv")

    with st.container(border=True):
        st.markdown("##### 🎯 검색 조건")
        with st.form("inv_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            strategy = c1.selectbox(
                "투자 전략",
                ["🔀 전략 비교", "🚀 투자수익", "갭투자", "임대수익", "자가매입"],
                index=0,
                help="🔀 전략 비교 = 3전략 동시 실행 후 교집합 하이라이트",
            )
            months = c2.slider("분석 기간 (개월)", 3, 36, 24,
                                 help="과거 N개월 데이터 사용")
            catalyst_weight = c3.slider(
                "호재 가중치", 0.0, 0.5, 0.10, 0.05,
                help="호재 점수를 등급에 가산하는 강도. 0=호재 무시, 0.3=호재 100점 지역이 tier +30점 효과. "
                     "백테스트: 0.10이 균형, 0.30이면 Top10 적중률↑ 대신 전체 순위 ρ↓.",
            )

            c4, c5, c6 = st.columns(3)
            min_deals = c4.slider("최소 매매 거래수", 1, 500, 50, step=10)
            top_n = c5.slider("추천 단지 개수", 10, 200, 50)
            tier_weight = c6.slider(
                "지역(평당가) 가중치", 0.0, 1.0, 0.7, 0.05,
                help="시군구 중위 평당가 백분위가 점수에 차지하는 비중 (나머지는 대장단지 가중치). "
                     "예: 0.7이면 '동네가 좋은지' 70%, '동네 내 대장 단지인지' 30%. "
                     "백테스트 권장: 0.7.",
            )

            c7, c8, c9 = st.columns(3)
            with c7:
                area_range = st.slider(
                    "전용면적 범위 (㎡)",
                    min_value=0, max_value=200,
                    value=(80, 110), step=5,
                    help="기본 24~33평(80~110㎡). 1평 ≈ 3.3㎡ (30평 ≈ 99㎡, 40평 ≈ 132㎡)",
                )
            with c8:
                _this_year = date.today().year
                year_range = st.slider(
                    "준공연도 범위",
                    min_value=1970, max_value=_this_year + 5,
                    value=(_this_year - 10, _this_year + 5), step=1,
                    help=f"기본 최근 10년({_this_year-10}~{_this_year+5}). 구축까지 보려면 하한 내리기.",
                )
            with c9:
                prestige_weight = st.slider(
                    "대장단지 가중치", 0.0, 1.0, 0.30, 0.05,
                    help="시군구 내 단지 평당가 백분위가 점수에 차지하는 비중. "
                         "지역 가중치와 합해 100% 정규화. 백테스트 권장: 0.30.",
                )

            submitted = st.form_submit_button(
                "🔍 검색", type="primary", width='stretch',
            )

    inputs = dict(
        **p,
        strategy=strategy, months=months,
        min_deals=min_deals, top_n=top_n, catalyst_weight=catalyst_weight,
        tier_weight=tier_weight, prestige_weight=prestige_weight,
        area_range=area_range, year_range=year_range,
        submitted=submitted,
    )
    render_recommend_tab(inputs)


def invest_sidebar_inputs() -> dict:
    """투자 시뮬레이션 사이드바 입력만 수집.

    - 시드, 주택, 생애최초, 대출, 전략, DSR, 인적사항
    - 검색 버튼 눌렀을 때만 갱신
    """
    with st.sidebar:
        st.markdown("### 💎 투자 조건")
        months = st.slider(
            "분석 기간 (개월)", 3, 36, 24, key="i_months",
            help="과거 N개월 데이터를 분석에 사용",
        )

        with st.form("rec_form", clear_on_submit=False):
            seed_eok = st.number_input(
                "자기자본 시드 (억원)", min_value=0.1, max_value=200.0,
                value=5.0, step=0.5, format="%.1f",
            )
            ownership = st.selectbox("보유 주택 수", ["무주택", "1주택", "다주택"])
            cc1, cc2 = st.columns(2)
            first_time = cc1.checkbox("생애최초", help="LTV 보너스")
            use_loan = cc2.checkbox(
                "대출 사용", value=True,
                help="갭투자는 무관 (전세=임차인 부담)",
            )
            strategy = st.selectbox(
                "투자 전략",
                ["🔀 전략 비교", "🚀 투자수익", "갭투자", "임대수익", "자가매입"],
                index=0,
                help="🔀 전략 비교 = 3전략 동시 실행 후 교집합 하이라이트",
            )
            with st.expander("💳 DSR (선택) - 정확한 대출 한도"):
                use_dsr = st.checkbox(
                    "DSR 적용", value=False,
                    help="체크 시 LTV·한도cap·DSR 모두 적용. 미체크 시 LTV·한도cap만"
                )
                annual_income = st.number_input(
                    "연 소득 (만원)", min_value=0, max_value=100000,
                    value=6000, step=500,
                    help="세전 연소득"
                )
                existing_debt_monthly = st.number_input(
                    "기존 부채 월 원리금 (만원)", min_value=0, max_value=2000,
                    value=0, step=10,
                    help="신용대출/자동차/카드 등 기존 월 원리금 합"
                )
                interest_rate = st.slider(
                    "대출 금리 (%)", 2.0, 8.0, 4.5, 0.1,
                    help="신청 시점 명목 금리"
                )
                dsr_limit = st.slider("DSR 한도 (%)", 30, 50, 40,
                                        help="1금융 40, 2금융 50")

            with st.expander("👤 인적 사항 (선택)"):
                age = st.number_input("나이", min_value=20, max_value=80, value=35)
                family_size = st.number_input("부양가족 수", min_value=0, max_value=10, value=0)
                residence_type = st.selectbox(
                    "거주방식", ["실거주", "전세임대"],
                    help="전세임대는 다주택 보유시 양도세에 영향"
                )
                risk_profile = st.selectbox(
                    "투자 성향", ["중립", "공격적", "보수적"],
                    help="추천 점수에 ±15% 가중치 보정 (현재는 표시만)"
                )
                commute_hubs = st.multiselect(
                    "출퇴근 거점 (선택)",
                    ["강남", "판교", "광화문", "여의도", "송도", "수원", "화성", "평택", "천안"],
                    help="추후 거점 거리 필터링용"
                )

            with st.expander("⚙️ 고급 필터"):
                min_deals = st.slider("최소 매매 거래수", 1, 500, 50, step=10)
                top_n = st.slider("추천 단지 개수", 10, 200, 50)
                catalyst_weight = st.slider(
                    "호재 가중치", 0.0, 1.0, 0.0, 0.05,
                    help="0=과거 모멘텀만 / 1=호재만 (백테스트 권장: 0)",
                )
                tier_weight = st.slider(
                    "상급지 가중치", 0.0, 1.0, 0.6, 0.05,
                    help="규제지역 해제 순서 기반 등급 가산점. "
                         "강남3구·용산=100점, 서울 비강남=80, 인천/경기=60, 지방 광역시=40. "
                         "슬라이더 하나로 전 지역 가중치 동시 조절.",
                )
            submitted = st.form_submit_button(
                "🔍 검색", type="primary", width='stretch',
            )

        st.divider()
        if st.button("🔄 캐시 비우기", width='stretch', key="i_clear",
                     help="새 데이터 수집 후 또는 강제 재계산 시"):
            st.cache_data.clear()
            st.success("캐시 비움. 다음 검색은 재실행됩니다.")

    return dict(
        months=months,
        seed_eok=seed_eok, ownership=ownership, first_time=first_time,
        use_loan=use_loan, strategy=strategy,
        min_deals=min_deals, top_n=top_n, catalyst_weight=catalyst_weight,
        tier_weight=tier_weight,
        submitted=submitted,
        use_dsr=use_dsr, annual_income=annual_income,
        existing_debt_monthly=existing_debt_monthly,
        interest_rate=interest_rate, dsr_limit=dsr_limit,
        age=age, family_size=family_size,
        residence_type=residence_type, risk_profile=risk_profile,
        commute_hubs=commute_hubs,
    )


def chart_monthly_price(monthly: pd.DataFrame, label: str):
    # 만원 → 억원 변환
    df = monthly.copy()
    df["평균매매가(억원)"] = (df["avg_price"] / 10000).round(2)
    df["중위매매가(억원)"] = (df["median_price"] / 10000).round(2)
    fig = px.line(df, x="ym", y=["평균매매가(억원)", "중위매매가(억원)"],
                  labels={"value": "가격 (억원)", "ym": "년월", "variable": "구분"},
                  title=f"{label} 월별 평균/중위 매매가")
    fig.update_layout(legend_title_text="")
    return fig


def chart_monthly_ppp(monthly: pd.DataFrame):
    fig = px.line(monthly, x="ym", y="avg_ppp",
                  labels={"avg_ppp": "평당가 (만원/평)", "ym": "년월"},
                  title="월별 평당가 추이")
    return fig


def page_strategy_backtest():
    """🔬 전략 백테스트 — 투자수익·갭투자·임대수익 예측력 비교."""
    from src.analysis.gap_backtest import (
        gap_score_backtest, jeonse_risk_backtest,
        gap_simulation_backtest, gap_walk_forward,
        rental_yield_backtest,
    )
    from src.analysis.backtest import apt_backtest, region_backtest

    st.title("🔬 전략 백테스트")
    st.caption("투자수익·갭투자·임대수익 전략의 점수 예측력을 Spearman ρ로 실증 검증합니다.")

    with st.expander("📖 백테스트란? — 지표 읽는 법", expanded=False):
        st.markdown("""
**백테스트 구조**

> 과거 특정 시점에 "지금 이 단지 점수가 높다" → 이후 실제로 더 올랐는가?

- **학습 기간**: 점수를 계산할 때 참고하는 과거 데이터 범위
- **검증 기간**: 점수 산출 이후, 실제 가격이 얼마나 올랐는지 측정하는 기간
- 두 기간이 겹치지 않아야 진짜 예측력 검증 (out-of-sample)

---

**Spearman ρ (스피어만 순위 상관계수)**

점수 순위와 실제 상승률 순위가 얼마나 일치하는지를 -1 ~ +1로 표현합니다.

| ρ 범위 | 의미 | 판단 |
|---|---|---|
| **+0.5 이상** | 점수 높은 단지가 실제로도 많이 올랐다 | ✅ 강한 예측력 |
| **+0.3 ~ +0.5** | 어느 정도 예측 가능 | ✅ 유의미 |
| **-0.3 ~ +0.3** | 점수와 상승률이 무관 | ❌ 예측력 없음 |
| **-0.3 이하** | 점수 높을수록 오히려 덜 올랐다 | ❌ 역효과 |

ρ = 0.3 선을 넘어야 "이 점수를 믿고 투자 판단에 활용할 수 있다"고 봅니다.

---

**상위10% 적중률**

점수 상위 10% 단지 중 실제 상승률 상위 20%에 포함된 비율입니다.

- **랜덤 기대치: 20%** — 아무렇게나 골라도 상위 20%에 들어갈 확률이 20%
- **50%** → 랜덤 대비 2.5배 정확하게 좋은 단지를 고른 것
- **30% 이상**이면 실무에서 참고할 만한 선별력으로 봅니다
        """)

    with st.container(border=True):
        st.markdown("##### ⚙️ 공통 파라미터")
        st.caption("⚠️ DB 보유 데이터: 약 2024년~현재. 학습 기간 + 검증 기간 합계가 24개월 이하여야 오류 없이 동작합니다.")
        c1, c2, c3, c4 = st.columns(4)
        train_months = c1.slider("학습 기간 (개월)", 6, 24, 12, key="bt_train",
                                  help="점수 산출에 사용할 과거 데이터 기간. 길수록 노이즈 감소, 짧을수록 최근 트렌드 반영. DB 데이터는 2024년~이므로 학습+검증 합계 24개월 이하 권장")
        test_months  = c2.slider("검증 기간 (개월)", 6, 18, 12, key="bt_test",
                                  help="점수 산출 후 실제 성과를 측정할 기간. 학습+검증 합계가 DB 보유 기간을 초과하면 데이터 부족 오류 발생")
        min_deals    = c3.slider("최소 거래수", 3, 30, 5, key="bt_min",
                                  help="학습 기간을 전반/후반으로 나눴을 때 각각 이 건수 이상인 단지만 포함. 12개월 학습이면 '6개월당 5건 이상' 조건 → 실질적으로 연 10건 이상 거래 단지만 반영됨")
        fall_thr     = c4.slider("역전세 기준 (%p)", 1.0, 10.0, 3.0, 0.5, key="bt_fall",
                                  help="전세가율이 이 수치 이상 하락하면 역전세 '발생'으로 판정")

    _used_months = train_months + test_months
    _remaining = max(0, 24 - _used_months)
    st.caption(
        f"📅 현재 설정 사용 기간: **{_used_months}개월** (학습 {train_months} + 검증 {test_months}) | "
        f"DB 누적 목표: **24개월 이상** — "
        + (f"약 {_remaining}개월 더 쌓이면 갭투자·임대수익 점수 수식 재검토 권장"
           if _remaining > 0 else "✅ 24개월 이상 누적 — 수식 재검토 적기")
    )

    tab_compare, tab_invest, tab_gap, tab_yield = st.tabs([
        "📊 전략 비교",
        "🚀 투자수익",
        "🏠 갭투자",
        "💰 임대수익",
    ])

    # ── 전략 비교 ──────────────────────────────────────────────────
    with tab_compare:
        st.markdown("#### 전략별 Spearman ρ 비교")
        st.markdown(
            "세 전략의 종합점수가 실제 매매가 상승률을 얼마나 잘 예측하는지 한눈에 비교합니다.  \n"
            "**초록 점선(ρ = 0.3)을 넘는 전략만 실제 투자 판단에 활용할 수 있습니다.**"
        )

        st.info(
            "**자가매입 전략은 제외됩니다.**  \n"
            "저평가 가설(평당가 낮은 곳이 더 오른다)을 다중 시점 백테스트로 검증: **ρ = −0.61** — 음의 상관.  \n"
            "비싼 지역·대장 단지가 더 오르는 '마태 효과' 확인. 자가매입 기준은 투자수익(market+prestige) 점수로 흡수됨."
        )

        if st.button("▶ 3전략 전체 실행", key="run_compare", type="primary"):
            compare_rows = []
            col_status = st.empty()

            for label, runner in [
                ("🚀 투자수익", lambda: apt_backtest(train_months=train_months, test_months=test_months)),
                ("🏠 갭투자",   lambda: gap_score_backtest(train_months=train_months, test_months=test_months, min_deals=min_deals)),
                ("💰 임대수익", lambda: rental_yield_backtest(train_months=train_months, test_months=test_months, min_deals=min_deals)),
            ]:
                col_status.text(f"{label} 계산 중...")
                try:
                    r = runner()
                    compare_rows.append({
                        "전략": label, "ρ": r.spearman, "표본수": r.n,
                        "상위10% 적중률(%)": round(r.top10_hit * 100, 1),
                    })
                except Exception as e:
                    compare_rows.append({"전략": label, "ρ": None, "표본수": 0,
                                         "상위10% 적중률(%)": 0, "오류": str(e)})
            col_status.empty()

            df_cmp = pd.DataFrame(compare_rows)
            valid_cmp = df_cmp[df_cmp["ρ"].notna()].copy()

            if not valid_cmp.empty:
                # ── 신뢰도 판정 ──
                def _reliability(rho, hit, label=""):
                    if "갭투자" in label:
                        # 갭투자는 매매가 상승 예측이 목적이 아님 — ρ 음수도 정상
                        if rho >= 0.3:   return "🟢 높음", f"갭 조건 좋은 곳이 실제 상승도 높음 (상위10% 중 {hit:.0f}% 적중)"
                        if rho >= 0.0:   return "🟡 중립", "ρ≥0 — 탭 C ROE 시뮬레이션이 핵심 지표입니다"
                        return "⚪ 해당없음", "갭투자 점수는 매매가 상승 예측 목적이 아닙니다. 탭 C ROE를 확인하세요"
                    # 투자수익 · 임대수익 공통 (두 전략 모두 양의 ρ 목표)
                    if rho >= 0.5:   return "🟢 높음", f"점수가 실제 상승을 잘 예측합니다 (상위10% 중 {hit:.0f}% 적중)"
                    if rho >= 0.3:   return "🟡 보통", f"어느 정도 예측 가능합니다 (상위10% 중 {hit:.0f}% 적중)"
                    if rho >= 0.0:   return "🔴 낮음", f"예측력이 약합니다 (점수와 상승률 거의 무관)"
                    return "🔴 역방향", f"점수 높은 곳이 오히려 덜 올랐습니다 — 수식 점검 필요"

                c_m = st.columns(len(valid_cmp))
                for col, (_, row) in zip(c_m, valid_cmp.iterrows()):
                    badge, desc = _reliability(row["ρ"], row["상위10% 적중률(%)"], row["전략"])
                    col.markdown(f"**{row['전략']}**")
                    col.markdown(f"### {badge}")
                    col.caption(desc)
                    col.caption(f"표본 {row['표본수']:,}건 | 상위10% 적중 {row['상위10% 적중률(%)']:.0f}% (랜덤 기대치 20%)")

                st.markdown("---")

                # ── 차트: ρ 값은 참고용으로만 표시 ──
                valid_cmp["신뢰도"] = valid_cmp.apply(
                    lambda r: _reliability(r["ρ"], r["상위10% 적중률(%)"], r["전략"])[0], axis=1)
                fig_cmp = px.bar(
                    valid_cmp, x="전략", y="ρ",
                    color="ρ", color_continuous_scale="RdYlGn", range_color=[-0.7, 0.7],
                    text="신뢰도",
                    title="전략별 점수 예측력 — 초록 점선(0.3) 이상이어야 믿을 수 있음",
                    height=400,
                )
                fig_cmp.add_hline(y=0.3, line_dash="dash", line_color="green",
                                   annotation_text="신뢰 기준선")
                fig_cmp.add_hline(y=0, line_dash="solid", line_color="gray")
                fig_cmp.update_traces(textposition="outside")
                fig_cmp.update_layout(coloraxis_showscale=False,
                                       yaxis_title="예측력 (Spearman ρ, 참고용)")
                st.plotly_chart(fig_cmp, width='stretch')

                st.markdown("**수치 상세** — 상위10% 적중률 랜덤 기대치 = **20%**, 30% 이상이면 활용 가능")
                display_cmp = valid_cmp[["전략", "신뢰도", "표본수", "상위10% 적중률(%)", "ρ"]].copy()
                display_cmp["ρ"] = display_cmp["ρ"].apply(lambda v: f"{v:+.3f}")
                st.dataframe(display_cmp, hide_index=True, width='stretch')

            for _, row in df_cmp[df_cmp["ρ"].isna()].iterrows():
                st.warning(f"{row['전략']}: {row.get('오류', '알 수 없는 오류')}")

    # ── 투자수익 탭 ────────────────────────────────────────────────
    with tab_invest:
        st.markdown("#### 🚀 투자수익 전략 검증")
        st.markdown(
            "**이 전략의 핵심 질문:** 시장 강도(매수 심리)와 단지 명성(prestige)이 높은 곳이 실제로 더 오르는가?  \n"
            "점수 = `region_score(시장강도+상급지) × 0.6 + prestige × 0.1 + 모멘텀 시그널 × 0.3`  \n"
            "ρ > 0.3 이면 이 점수가 미래 상승을 예측한다는 것이 통계적으로 입증됩니다."
        )

        with st.expander("📜 백테스트 결론 및 개발 히스토리", expanded=True):
            st.markdown(
                """
**결론 (2026-05 다중시점 백테스트)**

| 모델 / 요소 | Spearman ρ | 채택 |
|-------------|-----------|------|
| **market×0.7 + prestige×0.3 (단지)** | **+0.62** | ✅ |
| **market×0.7 + prestige×0.3 (시군구)** | **+0.62** | ✅ |
| 저평가 점수 (자가매입 기준) | −0.61 | ❌ 기각 |
| tier만 (규제해제 순서) | 약함 | 보조만 |
| jeonse_accel | 역상관 | ❌ |
| population 순유입 | 역상관 | ❌ |
| supply_pressure | 효과 없음 | ❌ |

**자가매입 전략 제외 이유:** 저평가 가설 데이터로 기각 (ρ −0.61).
"싼 곳이 더 오른다"는 반대 — 비싼 지역·대장 단지가 더 오르는 **마태 효과** 확인.
자가매입 추천은 투자수익 점수(market+prestige)로 통합되어 별도 백테스트 불필요.
                """
            )

        c1_inv, c2_inv = st.columns(2)
        cw_inv = c1_inv.slider("호재 가중치", 0.0, 0.3, 0.1, 0.05, key="bt_inv_cw",
                               help="개발·교통 호재의 점수 반영 강도. 높일수록 호재 지역이 상위권 차지")
        tw_inv = c2_inv.slider("상급지 가중치", 0.0, 1.0, 0.3, 0.05, key="bt_inv_tw",
                               help="강남·마포 등 상급지 보너스 강도. 현재 최적값은 0.3~0.6")

        if st.button("▶ 투자수익 재실행", key="run_invest"):
            with st.spinner("계산 중..."):
                try:
                    ri_apt = apt_backtest(
                        train_months=train_months, test_months=test_months,
                        catalyst_weight=cw_inv, tier_weight=tw_inv,
                    )
                    ri_reg = region_backtest(
                        train_months=train_months, test_months=test_months,
                        catalyst_weight=cw_inv, tier_weight=tw_inv,
                    )
                    ci1, ci2 = st.columns(2)
                    with ci1:
                        st.markdown("**단지 단위** — 개별 아파트 단지 예측력")
                        st.metric("Spearman ρ", f"{ri_apt.spearman:+.3f}",
                                  help="점수 순위 ↔ 실제 상승률 순위 일치도")
                        st.metric("상위10% 적중률", f"{ri_apt.top10_hit*100:.1f}%",
                                  help="점수 상위 10% 중 실제 상위 20%에 포함된 비율. 랜덤 기대치=20%")
                        st.metric("표본 수", f"{ri_apt.n:,}")
                    with ci2:
                        st.markdown("**시군구 단위** — 지역(구·군) 예측력")
                        st.metric("Spearman ρ", f"{ri_reg.spearman:+.3f}")
                        st.metric("상위10% 적중률", f"{ri_reg.top10_hit*100:.1f}%")
                        st.metric("표본 수", f"{ri_reg.n:,}")
                    st.markdown("**요소별 단독 ρ (단지)** — 각 요소가 혼자서 얼마나 예측하는가")
                    st.caption("ρ가 양수(↑)면 이 요소가 높은 단지가 실제 더 올랐다는 뜻, 음수(↓)면 반대")
                    comp_inv = pd.DataFrame([
                        {"요소": k, "ρ": v,
                         "방향": "↑ 양 (높을수록 오름)" if v > 0.05 else ("↓ 음 (높을수록 덜 오름)" if v < -0.05 else "→ 중립")}
                        for k, v in ri_apt.component_corr.items()
                    ]).sort_values("ρ", ascending=False)
                    st.dataframe(comp_inv, hide_index=True, width='stretch')
                    st.caption(
                        f"📌 단지 ρ={ri_apt.spearman:+.3f} / 시군구 ρ={ri_reg.spearman:+.3f}. "
                        + ("두 단위 모두 유의미 — 점수를 신뢰할 수 있습니다." if min(ri_apt.spearman, ri_reg.spearman) >= 0.3
                           else "한 단위 이상이 기준 미달 — 가중치 조정을 시도해 보세요.")
                    )
                except ValueError as e:
                    st.error(f"계산 실패: {e}")

    # ── 갭투자 탭 ──────────────────────────────────────────────────
    with tab_gap:
        st.markdown("#### 🏠 갭투자 전략 백테스트 (4종)")
        st.markdown(
            "**갭투자 점수 구성:** 상급지 등급(tier) **80%** + 거래활성도 **20%**  \n"
            "갭투자도 결국 시세차익이 핵심 — 갭 크기는 진입 필터(시드 조건)로만 사용하고, "
            "점수는 얼마나 오를 곳인가를 기준으로 산정합니다.  \n"
            "leverage_mult·jeonse_quality·market_score는 역상관 또는 노이즈 확인으로 점수에서 제외됐으며, 표시 목적으로만 출력됩니다."
        )

        inner_a, inner_b, inner_c, inner_d = st.tabs([
            "A. 점수-수익률",
            "B. 역전세 리스크",
            "C. 수익 시뮬",
            "D. Walk-forward",
        ])

        with inner_a:
            st.markdown("#### A. 갭투자 점수 vs 실제 매매가 상승률")
            st.markdown(
                "갭투자 점수가 높은 단지가 실제 매매가도 더 올랐는가?  \n"
                "ρ가 **음수**여도 괜찮습니다 — 갭투자의 목적은 '싸게 들어가서 레버리지 수익'이지, "
                "'가장 빨리 오를 곳 고르기'가 아니기 때문입니다. 탭 C의 ROE 시뮬레이션이 더 중요합니다."
            )
            if st.button("▶ 실행 (A)", key="run_a"):
                with st.spinner("계산 중..."):
                    try:
                        ra = gap_score_backtest(train_months=train_months, test_months=test_months, min_deals=min_deals)
                        ca1, ca2, ca3 = st.columns(3)
                        ca1.metric("표본 수", f"{ra.n:,}건")
                        ca2.metric("종합 점수 ρ", f"{ra.spearman:+.3f}",
                                   help="점수 순위 ↔ 상승률 순위 상관. 음수=점수 높은 곳이 덜 오름 (정상 현상)")
                        ca3.metric("상위10% 적중률", f"{ra.top10_hit*100:.1f}%",
                                   help="랜덤 기대치=20%. 이 지표보다 ρ와 탭C ROE가 더 핵심")
                        st.markdown("**요소별 단독 ρ** — 각 요소가 매매가 상승과 어떤 관계인지")
                        st.caption("요소가 양의 ρ면 그 요소가 높은 곳이 실제 더 올랐다는 뜻")
                        comp = pd.DataFrame([
                            {"요소": k, "ρ": v,
                             "방향": "↑ 양 (상승 연관)" if v > 0.05 else ("↓ 음 (역연관)" if v < -0.05 else "→ 중립")}
                            for k, v in ra.component_corr.items()
                        ]).sort_values("ρ", ascending=False)
                        st.dataframe(comp, hide_index=True, width='stretch')
                        if not ra.raw.empty:
                            fig = px.scatter(
                                ra.raw, x="score", y="actual_growth",
                                hover_data=["region_code", "apt_name"],
                                labels={"score": "갭투자 점수", "actual_growth": "실제 상승률 (%)"},
                                title=f"갭투자 점수 vs 실제 매매가 상승률 (ρ={ra.spearman:+.3f})",
                                trendline="ols",
                            )
                            st.plotly_chart(fig, width='stretch')
                            st.caption("점들이 우상향(/)이면 점수가 상승 예측, 우하향(\\)이면 역상관")
                    except ValueError as e:
                        st.error(f"계산 실패: {e}")

        with inner_b:
            st.markdown("#### B. 역전세 리스크 레이블 분류 정확도")
            st.markdown(
                f"갭투자 점수의 ⚠️·🔶 위험 레이블이 실제 전세가율 **{fall_thr}%p 이상 하락**을 얼마나 잘 잡아냈는가?  \n"
                "**Precision**: 위험 경고 중 실제 위험이었던 비율 (낮으면 헛경보가 많음)  \n"
                "**Recall**: 실제 위험 중 경고를 발령한 비율 (낮으면 위험을 놓침)  \n"
                "**F1**: 둘의 조화평균. **0.5 이상**이면 실무에서 참고할 만한 수준"
            )
            if st.button("▶ 실행 (B)", key="run_b"):
                with st.spinner("계산 중..."):
                    try:
                        rb = jeonse_risk_backtest(
                            train_months=train_months, test_months=test_months,
                            min_deals=min_deals, fall_threshold_pct=fall_thr,
                        )
                        cb1, cb2, cb3, cb4 = st.columns(4)
                        cb1.metric("표본 수", f"{rb.n:,}건")
                        cb2.metric("Precision", f"{rb.precision:.3f}",
                                   help="위험 경고 중 실제 역전세 발생 비율. 높을수록 헛경보 少")
                        cb3.metric("Recall", f"{rb.recall:.3f}",
                                   help="실제 역전세 중 경고 발령 비율. 높을수록 위험을 놓치지 않음")
                        cb4.metric("F1", f"{rb.f1:.3f}",
                                   help="Precision과 Recall의 균형. 0.5 이상=실용적")
                        st.markdown(f"**실제 역전세 발생**: {rb.n_actual_risk}건 / {rb.n}건 ({rb.n_actual_risk/rb.n*100:.1f}%)")
                        c = rb.confusion
                        conf_df = pd.DataFrame({
                            "": ["예측: 위험", "예측: 안전"],
                            "실제: 위험": [c["TP"], c["FN"]],
                            "실제: 안전": [c["FP"], c["TN"]],
                        }).set_index("")
                        st.markdown("**혼동 행렬 (Confusion Matrix)**")
                        st.caption("TP=맞게 위험 경고, FP=헛경보(실제 안전), FN=놓친 위험, TN=맞게 안전 판정")
                        st.dataframe(conf_df, width='content')
                        st.caption(
                            f"📌 F1={rb.f1:.3f} → "
                            + ("실용적 수준 — 역전세 회피에 이 지표를 활용할 수 있습니다." if rb.f1 >= 0.5
                               else "아직 개선 여지 — 역전세 기준(%p)을 조정해 보세요.")
                            + f" | 역전세 기준: {fall_thr}%p 하락"
                        )
                    except ValueError as e:
                        st.error(f"계산 실패: {e}")

        with inner_c:
            st.markdown("#### C. 갭투자 TOP-N 수익 시뮬레이션")
            st.markdown(
                "과거 시점에 갭투자 점수 **상위 N개 단지**를 실제로 매수했다면 얼마나 벌었는가?  \n"
                "**ROE (자기자본 수익률)** = 매매가 상승액 ÷ 초기 갭(내 실투자금)  \n"
                "예: 갭 1억에 매수 후 매매가 3천만 오르면 ROE = +30%"
            )
            top_n_c = st.slider("TOP-N 단지 수", 5, 50, 20, key="top_n_c")
            if st.button("▶ 실행 (C)", key="run_c"):
                with st.spinner("계산 중..."):
                    try:
                        rc = gap_simulation_backtest(
                            train_months=train_months, hold_months=test_months,
                            top_n=top_n_c, min_deals=min_deals,
                        )
                        cc1, cc2, cc3, cc4 = st.columns(4)
                        cc1.metric("매칭 단지", f"{rc.n_matched}건")
                        cc2.metric("평균 매매가 상승", f"{rc.avg_price_growth_pct:+.2f}%")
                        cc3.metric("평균 ROE", f"{rc.avg_roe_pct:+.2f}%",
                                   help="자기자본(갭) 대비 매매가 상승 수익률")
                        cc4.metric("중앙값 ROE", f"{rc.median_roe_pct:+.2f}%")
                        if not rc.raw.empty:
                            show = rc.raw[["apt_name", "region_code", "gap",
                                            "price_growth_%", "roe_%", "score"]].copy()
                            show["gap_억"] = (show["gap"] / 10000).round(2)
                            show = show.drop(columns="gap").sort_values("roe_%", ascending=False)
                            show.insert(0, "rank", range(1, len(show) + 1))
                            fig_roe = px.bar(
                                show.head(top_n_c), x="apt_name", y="roe_%",
                                color="roe_%", color_continuous_scale="RdYlGn",
                                labels={"apt_name": "단지명", "roe_%": "ROE (%)"},
                                title=f"TOP-{top_n_c} 자기자본 수익률",
                            )
                            fig_roe.update_xaxes(tickangle=45)
                            st.plotly_chart(fig_roe, width='stretch')
                            st.dataframe(show, hide_index=True, width='stretch')
                        st.caption(
                            f"📌 갭 1억으로 ROE {rc.avg_roe_pct:+.2f}% = "
                            f"평균 {abs(rc.avg_roe_pct)/100:.2f}억 수익. 보유 {rc.hold_months}개월."
                        )
                    except ValueError as e:
                        st.error(f"계산 실패: {e}")

        with inner_d:
            st.markdown("#### D. Walk-forward: 여러 시점 반복 검증")
            st.markdown(
                "한 시점 결과는 운일 수 있습니다. 여러 과거 시점에서 반복 실행해 **평균과 편차**를 확인합니다.  \n"
                "편차(±)가 작을수록 일관성 있는 전략, 클수록 시점에 따라 들쭉날쭉한 전략입니다."
            )
            cd1, cd2 = st.columns(2)
            n_windows = cd1.slider("시점 수", 2, 8, 4, key="bt_n_win")
            top_n_d   = cd2.slider("시뮬레이션 TOP-N", 5, 50, 20, key="top_n_d")
            if st.button("▶ 실행 (D — 시간 오래 걸림)", key="run_d"):
                progress = st.progress(0, text="Walk-forward 실행 중...")
                wf_results = {}
                methods = [("score", "A. 점수-수익률"), ("risk", "B. 역전세 리스크"),
                           ("simulation", "C. 수익 시뮬레이션")]
                for idx, (mkey, mlabel) in enumerate(methods):
                    progress.progress((idx + 1) / len(methods), text=f"{mlabel} 계산 중...")
                    try:
                        rd = gap_walk_forward(
                            n_windows=n_windows, test_months=test_months, train_months=train_months,
                            method=mkey, min_deals=min_deals,
                            fall_threshold_pct=fall_thr, top_n=top_n_d,
                        )
                        wf_results[mkey] = rd
                    except Exception as e:
                        st.warning(f"{mlabel} 실패: {e}")
                progress.empty()
                if "score" in wf_results:
                    rd = wf_results["score"]
                    st.markdown("**A. 점수-수익률 walk-forward**")
                    st.metric("평균 ρ", f"{rd.avg_spearman:+.3f}", delta=f"±{rd.std_spearman:.3f}")
                    if not rd.summary.empty and "spearman" in rd.summary.columns:
                        valid_s = rd.summary[rd.summary["spearman"].notna()]
                        if not valid_s.empty:
                            fig_a = px.bar(valid_s, x="as_of", y="spearman",
                                            labels={"as_of": "기준 시점", "spearman": "ρ"}, title="시점별 ρ")
                            fig_a.add_hline(y=0, line_dash="dash", line_color="gray")
                            st.plotly_chart(fig_a, width='stretch')
                    st.dataframe(rd.summary, hide_index=True, width='stretch')
                if "risk" in wf_results:
                    rd = wf_results["risk"]
                    st.markdown("**B. 역전세 리스크 walk-forward**")
                    st.metric("평균 F1", f"{rd.avg_f1:.3f}", delta=f"±{rd.std_f1:.3f}")
                    st.dataframe(rd.summary, hide_index=True, width='stretch')
                if "simulation" in wf_results:
                    rd = wf_results["simulation"]
                    st.markdown("**C. 수익 시뮬레이션 walk-forward**")
                    st.metric("평균 ROE", f"{rd.avg_roe_pct:+.2f}%", delta=f"±{rd.std_roe_pct:.2f}%")
                    if not rd.summary.empty and "avg_roe_%" in rd.summary.columns:
                        fig_c = px.bar(
                            rd.summary[rd.summary["avg_roe_%"].notna()],
                            x="as_of", y="avg_roe_%",
                            labels={"as_of": "기준 시점", "avg_roe_%": "평균 ROE (%)"},
                            title="시점별 평균 ROE",
                        )
                        fig_c.add_hline(y=0, line_dash="dash", line_color="gray")
                        st.plotly_chart(fig_c, width='stretch')
                    st.dataframe(rd.summary, hide_index=True, width='stretch')

    # ── 임대수익 탭 ───────────────────────────────────────────────
    with tab_yield:
        st.markdown("#### 💰 임대수익 전략 백테스트")
        st.markdown(
            "**이 전략의 핵심 질문:** 현금흐름(월세 수익률)과 상승잠재력(상급지×시장강도)을 동시에 만족하는 단지를 찾는가?  \n\n"
            "**점수 구성:** 상승예상(tier+시장강도) **70%** + 수익률품질(yield × 상급지 보정) **30%**  \n"
            "`yield_quality = annual_yield_% × appreciation_score/100` — 같은 수익률이면 상급지 매물을 우대, 저가지역 고수익률 역상관 효과를 제거  \n\n"
            "**기대 결과:** ρ ≥ 0 (수식 개선 전 역상관이었으나, yield_quality 도입으로 양의 상관 목표)"
        )
        if st.button("▶ 실행", key="run_yield"):
            with st.spinner("계산 중..."):
                try:
                    ry = rental_yield_backtest(
                        train_months=train_months, test_months=test_months, min_deals=min_deals,
                    )
                    cy1, cy2, cy3 = st.columns(3)
                    cy1.metric("표본 수", f"{ry.n:,}건")
                    cy2.metric("종합점수 ρ", f"{ry.spearman:+.3f}",
                               help="양수이면 점수 높은 곳이 실제로도 상승 — 0.3 이상이면 활용 가능")
                    cy3.metric("상위10% 적중률", f"{ry.top10_hit*100:.1f}%",
                               help="랜덤 기대치=20%. 30% 이상이면 선별력 있음")

                    st.markdown("**요소별 단독 ρ** — 각 요소와 매매가 상승률의 관계")
                    st.caption("yield_quality(수익률품질)가 annual_yield(%)(원시 수익률)보다 높은 ρ를 보이면 수식 개선 효과가 입증됨")
                    comp_y = pd.DataFrame([
                        {"요소": k, "ρ": v,
                         "해석": "양의 상관 (높을수록 시세도 오름)" if v > 0.1
                                 else ("역상관" if v < -0.1 else "중립")}
                        for k, v in ry.component_corr.items()
                    ]).sort_values("ρ", ascending=False)
                    st.dataframe(comp_y, hide_index=True, width='stretch')

                    if not ry.raw.empty and "yield_quality" in ry.raw.columns:
                        fig_y = px.scatter(
                            ry.raw, x="yield_quality", y="actual_growth",
                            hover_data=["region_code", "apt_name", "annual_yield_%"],
                            labels={"yield_quality": "수익률품질 (yield×상급지)", "actual_growth": "실제 상승률 (%)"},
                            title=f"수익률품질 vs 실제 매매가 상승률 (종합ρ={ry.spearman:+.3f})",
                            trendline="ols",
                        )
                        st.caption("우상향(/) 추세선이면 yield_quality 높은 곳이 실제로도 올랐다는 것")
                        st.plotly_chart(fig_y, width='stretch')

                    if ry.spearman >= 0.3:
                        st.success(f"📌 ρ = {ry.spearman:+.3f} — 현금흐름·상승잠재력 동시 선별 확인")
                    elif ry.spearman >= 0.0:
                        st.info(f"📌 ρ = {ry.spearman:+.3f} — 약한 양의 상관 | n={ry.n:,}. 가중치 추가 조정 여지 있음")
                    else:
                        st.warning(
                            f"📌 ρ = {ry.spearman:+.3f} — 여전히 역상관. "
                            "annual_yield_%와 appreciation_score 역방향이 강한 데이터 구간일 수 있습니다."
                        )
                except ValueError as e:
                    st.error(f"계산 실패: {e}")


def main():
    page = _sidebar_nav()

    if page.startswith("🏠"):
        page_my_capacity()
    elif page.startswith("🚀"):
        page_invest()
    elif page.startswith("📊"):
        page_region()
    elif page.startswith("🗺️"):
        page_map()
    elif page.startswith("🚦"):
        page_market_signals()
    elif page.startswith("🔬"):
        page_strategy_backtest()
    else:
        page_my_capacity()


def page_region():
    """📊 지역 분석 - 단일 시군구 시계열 깊이 분석."""
    st.title("📊 지역 분석")
    st.caption("특정 시군구의 추이·단지·갭·수익률·상승률을 한 번에")

    with st.container(border=True):
        st.markdown("##### 분석 대상")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            sido = st.selectbox("시/도", list(REGIONS.keys()), key="rg_sido")
        sub = REGIONS[sido]
        code_by_name = {n: c for c, n in sub.items()}
        with c2:
            gu_name = st.selectbox(
                "시군구", list(code_by_name.keys()), key="rg_gu",
            )
        code = code_by_name[gu_name]
        label = gu_name
        with c3:
            months = st.slider("최근 N개월", 3, 36, 12, key="rg_months")

    date_from = date.today() - timedelta(days=30 * months)
    df_t = fetch_trades_df(region_code=code, date_from=date_from)
    df_r = fetch_rents_df(region_code=code, date_from=date_from)

    st.markdown(f"### {label}")
    st.caption(f"최근 {months}개월 데이터 기준")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("매매 거래", f"{len(df_t):,} 건")
    c2.metric("전월세 거래", f"{len(df_r):,} 건")
    c3.metric("분석 단지 수", f"{df_t['apt_name'].nunique() if not df_t.empty else 0:,} 개")
    avg_ppp = int(df_t["price_per_pyeong"].mean()) if not df_t.empty else 0
    c4.metric("평균 평당가", f"{avg_ppp:,} 만원/평")

    if df_t.empty:
        st.warning(f"{label} 데이터가 없습니다. scripts/collect_data.py 로 먼저 수집하세요.")
        st.code(f"python scripts/collect_data.py --region {code} --months {months}")
        return

    # 🔬 지역 상세 진단 (매수심리·호재·공급 등 종합)
    with st.expander("🔬 지역 상세 진단 (매수심리·호재·공급)", expanded=True):
        _render_region_detail(code)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📈 추이", "🏢 단지", "↔ 갭분석", "💰 수익률", "🔥 상승률"]
    )

    with tab1:
        st.subheader("월별 매매가 추이")
        st.caption("금액 단위: 억원 (1억원 = 10,000 만원). 평당가는 만원/평.")
        monthly = yoy_change(monthly_summary(df_t))
        if not monthly.empty:
            st.plotly_chart(chart_monthly_price(monthly, label), width='stretch')
            st.plotly_chart(chart_monthly_ppp(monthly), width='stretch')
            render_table(monthly)

        st.markdown("---")
        st.markdown("### 📈 Prophet 시계열 예측 (실험적)")
        st.caption(
            "최근 24개월 월별 중위 매매가에 Prophet을 적용해 향후 6개월 예측. "
            "**과거 추세 외삽이며 단순 통계 모델입니다. 미래를 보장하지 않습니다.**"
        )
        forecast_df = _cached_forecast(code, months_data=24, periods=6)
        if forecast_df.empty:
            st.info("예측을 위한 데이터가 부족합니다 (최소 6개월 이상 필요).")
        else:
            f = forecast_df.copy()
            f["가격(억원)"] = (f["yhat"] / 10000).round(2)
            f["하한(억원)"] = (f["yhat_lower"] / 10000).round(2)
            f["상한(억원)"] = (f["yhat_upper"] / 10000).round(2)
            f["구분"] = f["is_forecast"].map({True: "예측", False: "실측"})
            fig = px.line(f, x="ds", y="가격(억원)", color="구분",
                          color_discrete_map={"실측": "#1f77b4", "예측": "#d62728"},
                          labels={"ds": "년월"},
                          title=f"{label} 매매가 예측 (다음 6개월)")
            fig.add_scatter(x=f["ds"], y=f["하한(억원)"], mode="lines",
                            line=dict(color="rgba(214,39,40,0.2)"), name="하한",
                            showlegend=False)
            fig.add_scatter(x=f["ds"], y=f["상한(억원)"], mode="lines",
                            line=dict(color="rgba(214,39,40,0.2)"), name="상한",
                            fill="tonexty", fillcolor="rgba(214,39,40,0.1)",
                            showlegend=False)
            st.plotly_chart(fig, width='stretch')
            fc_only = f[f["is_forecast"]].copy()
            st.markdown("**향후 6개월 예측값**")
            st.dataframe(
                fc_only[["ds", "가격(억원)", "하한(억원)", "상한(억원)"]]
                .rename(columns={"ds": "년월"}),
                width='stretch', hide_index=True,
            )

    with tab2:
        st.subheader("단지별 거래 요약")
        st.caption("금액: 억원, 평당가: 만원/평, 면적: ㎡")
        apts = apt_summary(df_t, top=100)
        render_table(apts, height=600)

        sel = st.text_input("단지명 검색", "")
        if sel:
            sub = df_t[df_t["apt_name"].str.contains(sel, na=False)]
            if not sub.empty:
                sub_m = monthly_summary(sub)
                if not sub_m.empty:
                    fig = px.line(
                        sub_m.assign(평균매매가_억원=(sub_m["avg_price"]/10000).round(2)),
                        x="ym", y="평균매매가_억원",
                        labels={"평균매매가_억원": "평균매매가 (억원)", "ym": "년월"},
                        title=f"'{sel}' 월별 평균가",
                    )
                    st.plotly_chart(fig, width='stretch')
                st.markdown("**최근 거래 내역 (최대 200건)**")
                recent = sub.sort_values("deal_date", ascending=False).head(200)
                show_cols = ["deal_date", "apt_name", "dong", "area_m2", "floor",
                             "deal_amount", "price_per_pyeong", "build_year"]
                render_table(recent[show_cols])

    with tab3:
        st.subheader("매매-전세 갭")
        st.caption("같은 단지·면적의 최근 매매 중위가 − 전세환산 중위가 (월세는 ×100 환산). 금액: 억원.")
        gap = gap_table(df_t, df_r, area_tol=5.0, months=min(months, 6))
        render_table(gap, height=600)

    with tab4:
        st.subheader("임대 수익률 추정")
        st.caption("연수익률 = (월세 × 12) ÷ (매매가 − 보증금) × 100. 금액: 억원, 월세: 만원.")
        yld = rental_yield(df_t, df_r, area_tol=5.0, months=months)
        render_table(yld, height=600)

    with tab5:
        st.subheader("단지별 가격 상승률")
        st.caption(f"최근 {max(months//2, 3)}개월 평당가 중위값 vs 그 이전 같은 기간. 평당가: 만원/평.")
        growth = apt_growth(df_t, lookback_months=max(months // 2, 3), min_deals=3)
        render_table(growth, height=600)
        if not growth.empty:
            top = growth.head(20)
            fig = px.bar(top, x="apt_name", y="change_%",
                         labels={"apt_name": "단지명", "change_%": "변동률 (%)"},
                         title="평당가 상승률 TOP 20")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, width='stretch')



# === 지역 코드 → 시도+이름 매핑 (추천 탭에서 사용) ===
def _build_region_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for sido, gus in REGIONS.items():
        for code, name in gus.items():
            out[code] = f"{sido} {name}"
    return out


REGION_MAP = _build_region_map()


def _render_headline_card(inputs: dict, seed_man: int, dsr_cap_man: float | None):
    """최대 매수가 헤드라인 카드. 강남구 기준 예시 + 일반 비규제 기준 비교."""
    ownership = inputs["ownership"]
    first_time = inputs["first_time"]
    # 정책대출은 부부합산 소득 기준
    household_income = inputs.get("household_income", inputs.get("annual_income", 0))
    is_couple = inputs.get("is_couple", False)
    is_newlywed = inputs.get("is_newlywed", False)
    children = inputs.get("children", 0)

    # 규제/비규제 양쪽 매수가능 최고가
    p_reg = calc_max_purchase(seed_man, "11680", ownership, first_time, dsr_cap_man)
    p_nonreg = calc_max_purchase(seed_man, "99999", ownership, first_time, dsr_cap_man)

    # 부대비용 (규제지역 기준)
    costs = total_acquisition_cost_man(p_reg, ownership, first_time)
    actual_p_reg = p_reg - costs["total"]
    actual_p_nonreg_costs = total_acquisition_cost_man(p_nonreg, ownership, first_time)
    actual_p_nonreg = p_nonreg - actual_p_nonreg_costs["total"]

    # 정책대출 적격 (부부합산·신혼·자녀 반영)
    policy = best_policy_loan(
        household_income, p_reg, ownership,
        is_couple=is_couple, is_newlywed=is_newlywed,
        children=children, first_time_buyer=first_time,
    )

    st.markdown("## 💰 최대 매수 가능 시뮬레이션")

    cc1, cc2 = st.columns([1, 1])
    with cc1:
        st.markdown("##### 🏙️ 규제지역 (서울25 + 경기12)")
        st.metric("최대 매수가", f"{actual_p_reg/10000:.2f} 억",
                  help=f"부대비용 {costs['total']/10000:.2f}억 차감 후 실매수가")
        loan_reg = loan_capacity_man(p_reg, "11680", ownership, first_time, dsr_cap_man)
        st.caption(
            f"매매가 {p_reg/10000:.2f}억 = 시드 {seed_man/10000:.1f}억 + 대출 {loan_reg/10000:.2f}억 - 부대비 {costs['total']/10000:.2f}억"
        )
        st.caption(
            f"취득세 {costs['acquisition_tax']/10000:.2f}억 · "
            f"중개 {costs['broker_fee']/10000:.2f}억 · "
            f"등기·이사 {costs['registration_etc']/10000:.2f}억"
        )

    with cc2:
        st.markdown("##### 🏞️ 비규제지역 (수도권 외곽 등)")
        st.metric("최대 매수가", f"{actual_p_nonreg/10000:.2f} 억",
                  help="LTV 70%로 더 큰 레버리지 가능")
        loan_nonreg = loan_capacity_man(p_nonreg, "99999", ownership, first_time, dsr_cap_man)
        st.caption(
            f"매매가 {p_nonreg/10000:.2f}억 = 시드 {seed_man/10000:.1f}억 + 대출 {loan_nonreg/10000:.2f}억 - 부대비 {actual_p_nonreg_costs['total']/10000:.2f}억"
        )
        st.caption(
            f"취득세 {actual_p_nonreg_costs['acquisition_tax']/10000:.2f}억 · "
            f"중개 {actual_p_nonreg_costs['broker_fee']/10000:.2f}억 · "
            f"등기·이사 {actual_p_nonreg_costs['registration_etc']/10000:.2f}억"
        )

    # 정책대출 적격성 표시
    if policy["eligible"]:
        st.success(
            f"✅ **{policy['name']} 정책대출 적격** — 최대 {policy['max_loan_man']/10000:.1f}억 "
            f"@ 약 {policy['rate_pct']:.1f}% (일반 주담대보다 유리)"
        )
    else:
        with st.expander("ℹ️ 정책대출 적격성 (디딤돌/보금자리) — 불가 사유"):
            for name, r in policy["all_results"].items():
                st.markdown(f"- **{name}**: {'✅' if r['eligible'] else '❌'} {r['reason']}")


def _render_macro_signals():
    st.markdown("---")
    st.markdown("### 🚦 매크로 환경 신호등")
    st.caption("현재 시장 환경 6요인. 녹=우호 / 황=중립 / 적=불리")
    signals = macro_dashboard()
    cols = st.columns(len(signals))
    color_map = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    for col, sig in zip(cols, signals):
        with col:
            st.markdown(f"**{color_map[sig['level']]} {sig['name']}**")
            st.markdown(f"<span style='font-size:20px;font-weight:600'>{sig['value']}</span>",
                        unsafe_allow_html=True)
            st.caption(sig["detail"])


def _render_stress_test(inputs: dict, selected_row: dict):
    """선택 단지 1개에 대한 5년 시나리오 + 스트레스 테스트."""
    st.markdown("---")
    st.markdown(f"### 🧪 스트레스 테스트 — {selected_row.get('apt_name', '?')}")

    price_man = float(selected_row.get("trade_median", 0))
    loan_man = float(selected_row.get("loan_capacity", 0))
    equity_man = float(selected_row.get("required_equity", price_man - loan_man))
    growth_pct = float(selected_row.get("price_growth_%", 0))
    interest_rate = inputs.get("interest_rate", 4.5)

    # 시뮬레이션 슬라이더
    c1, c2 = st.columns(2)
    with c1:
        rate_bump = st.slider("금리 가산 (%)", 0.0, 3.0, 0.0, 0.25,
                                help="기준 금리 대비 추가 인상폭 가정")
    with c2:
        price_drop = st.slider("가격 변동 (%)", -30, 20, 0, 5,
                                 help="음수=하락, 양수=상승")

    # 스트레스 테스트
    stress = stress_test(price_man, loan_man, equity_man,
                          price_drop_pct=price_drop, rate_bump_pct=rate_bump,
                          interest_rate_pct=interest_rate)

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("월 상환액", f"{stress['new_monthly_payment_man']:,} 만원",
                help=f"가산 금리 {interest_rate + rate_bump:.2f}%")
    sc2.metric("자기자본 잔존", f"{stress['equity_remaining_man']/10000:.2f} 억",
                delta=f"{-stress['equity_loss_pct']:.1f}%",
                delta_color="inverse")
    sc3.metric("매도시 가격", f"{stress['scenario_price_man']/10000:.2f} 억")
    sc4.metric("자기자본 소멸 임계점", f"{stress['breakeven_drop_pct']:.1f}%",
                help="가격이 이만큼 떨어지면 자기자본 0",
                delta_color="off")

    # 24개월 이자만 감당 가능?
    months_24_interest = stress["new_monthly_payment_man"] * 24
    seed_remaining = inputs["seed_eok"] * 10000 - equity_man
    if seed_remaining < months_24_interest:
        st.warning(
            f"⚠️ 매수 후 24개월 이자/원리금 합계 {months_24_interest:,}만원 "
            f"> 시드 잔여 {seed_remaining:,}만원. 현금흐름 부담 주의."
        )

    # 5년 시나리오
    st.markdown("#### 📊 5년 후 시나리오")
    scenarios = project_5y_scenarios(
        price_man, growth_pct, equity_man, loan_man,
        interest_rate_pct=interest_rate,
    )
    if scenarios:
        rows = []
        for name, s in scenarios.items():
            rows.append({
                "시나리오": name,
                "연 상승률(%)": s["growth_pct_annual"],
                "5년 후 가격(억)": round(s["future_price_man"] / 10000, 2),
                "잔존 대출(억)": round(s["remaining_loan_man"] / 10000, 2),
                "누적 이자(억)": round(s["total_interest_5y_man"] / 10000, 2),
                "매도 시 자기자본(억)": round(s["equity_at_exit_man"] / 10000, 2),
                "연환산 수익률(%)": s["roi_annual_pct"],
            })
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)


def page_map():
    """🗺️ 지도 페이지 — 전국 시각화."""
    st.title("🗺️ 전국 분포 지도")
    st.caption("시군구 중심 좌표 기준 평균 평당가(색) + 거래량(크기)")
    with st.container(border=True):
        c1, c2 = st.columns([1, 1])
        with c1:
            months = st.slider("최근 N개월", 3, 36, 12, key="map_months")
        with c2:
            st.caption("좌측 슬라이더로 분석 기간 조절. 지도 옵션은 아래.")
    render_map_tab(months)


def page_market_signals():
    """🚦 시장 진단 - 매크로 신호등 + 지역별 매수심리."""
    st.title("🚦 시장 진단")
    st.caption("현재 시장 환경 6요인 + 수도권 지역별 매수심리 순위")

    _render_macro_signals()

    st.markdown("---")
    st.markdown("### 📊 지역별 매수심리 순위 (수도권)")
    st.caption(
        "매수심리 점수 = 거래량 모멘텀(50%) + 가격 가속도(30%) + 평균-중위 격차(20%). "
        "100점에 가까울수록 매수세 강함 (KB 매수우위지수와 유사 개념)."
    )
    sent = _cached_region_sentiment()
    if sent.empty:
        st.info("표시할 데이터가 없습니다.")
        return
    disp = sent.copy()
    disp["region"] = disp["region_code"].map(REGION_MAP).fillna(disp["region_code"])
    disp = disp[[
        "region", "avg_sentiment", "manual_catalyst",
        "avg_volume_momentum", "avg_accel", "avg_skew",
        "n_complexes", "catalyst_text",
    ]].rename(columns={"catalyst_text": "등록호재"})
    render_table(disp, height=500)


def render_map_tab(months: int):
    """전국 매물 지도 — 시군구 중심 좌표 기반.

    각 시군구를 점으로 그리고, 색=평당가 / 크기=거래량.
    apt 단위 정확 좌표가 없어서 시군구 단위 집계 표시 (한계).
    """
    st.subheader("🗺️ 전국 거래 분포 지도")
    st.caption(
        "시군구 중심 좌표 기준 평균 평당가(색) + 거래량(크기). "
        "단지별 정확 좌표는 카카오 지오코딩 도입 시 추가 예정."
    )

    coords = _load_region_coords()
    if not coords:
        st.error("config/region_coords.json 이 없습니다.")
        return

    from datetime import date, timedelta
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    agg = df.groupby("region_code").agg(
        deals=("deal_amount", "count"),
        avg_ppp=("price_per_pyeong", "mean"),
        median_price=("deal_amount", "median"),
        apt_count=("apt_name", "nunique"),
    ).round(0).reset_index()

    rows = []
    for _, r in agg.iterrows():
        c = coords.get(r["region_code"])
        if not c:
            continue
        rows.append({
            "region_code": r["region_code"],
            "region": REGION_MAP.get(r["region_code"], r["region_code"]),
            "lat": c[0], "lon": c[1],
            "거래량": int(r["deals"]),
            "평당가(만원/평)": int(r["avg_ppp"] or 0),
            "중위매매가(억원)": round((r["median_price"] or 0) / 10000, 2),
            "단지수": int(r["apt_count"]),
        })
    map_df = pd.DataFrame(rows)
    if map_df.empty:
        st.info("좌표를 찾을 수 있는 지역이 없습니다.")
        return

    c1, c2, c3 = st.columns(3)
    metric = c1.selectbox(
        "색상 기준", ["평당가(만원/평)", "거래량", "중위매매가(억원)"], index=0,
    )
    style = c2.selectbox(
        "지도 스타일",
        ["open-street-map", "carto-positron", "carto-darkmatter"],
        index=1,
    )
    size_max = c3.slider("점 최대 크기", 20, 80, 40)

    fig = px.scatter_mapbox(
        map_df, lat="lat", lon="lon",
        hover_name="region",
        hover_data={
            "lat": False, "lon": False,
            "거래량": True, "평당가(만원/평)": True,
            "중위매매가(억원)": True, "단지수": True,
        },
        color=metric, size="거래량",
        color_continuous_scale="RdYlBu_r",
        size_max=size_max, zoom=8.5,
        mapbox_style=style,
        center={"lat": 37.55, "lon": 127.0},
        height=650,
    )
    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0})
    st.plotly_chart(fig, width='stretch')

    st.markdown("### 지역 요약 (테이블)")
    show = map_df.drop(columns=["lat", "lon", "region_code"]).sort_values("평당가(만원/평)", ascending=False)
    st.dataframe(show, width='stretch', hide_index=True, height=400)


def _render_region_detail(region_code: str, rec_df: pd.DataFrame | None = None,
                          sent_df: pd.DataFrame | None = None):
    """선택된 지역의 모든 지표를 한 화면에 표시.

    rec_df=None이면 추천단지 TOP10 섹션 생략 (page_region 등 단일 지역 페이지용).
    sent_df=None이면 내부에서 매수심리 데이터를 자동 로드.
    """
    from src.analysis.recommend import _load_catalysts

    if sent_df is None:
        sent_df = _cached_region_sentiment()

    region_name = REGION_MAP.get(region_code, region_code)
    st.markdown(f"#### 📍 {region_name}")

    # 매수심리 (지역 단위)
    if sent_df is not None and not sent_df.empty and region_code in sent_df["region_code"].values:
        row = sent_df[sent_df["region_code"] == region_code].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("매수심리 점수", f"{row['avg_sentiment']:.1f} / 100",
                  delta="강세" if row['avg_sentiment'] >= 60 else ("약세" if row['avg_sentiment'] < 40 else "중립"))
        c2.metric("거래량 모멘텀", f"{row['avg_volume_momentum']:.2f} x",
                  help="1.0=평소, 2.0=2배 급증")
        c3.metric("가격 가속도", f"{row['avg_accel']:+.2f} %p",
                  help="최근 3mo 변화율 - 이전 3mo 변화율")
        c4.metric("호재점수(수동)", f"{row['manual_catalyst']:.0f} / 100")

    # 입주물량 (공급 부담)
    supply_units = supply_for_region(region_code, lookahead_months=12)
    supply_score = supply_pressure_score(region_code, lookahead_months=12)
    sc1, sc2 = st.columns(2)
    sc1.metric("향후 12개월 입주 예정", f"{supply_units:,} 호",
               help="등록된 분양 데이터 기준. config/supply.json")
    sc2.metric("공급 부담 지수", f"{supply_score:.1f} / 100",
               delta=("부담" if supply_score > 50 else "보통"),
               delta_color="inverse",
               help="높을수록 공급 과잉 (가격 상승에 불리)")

    # 등록된 호재 카드 형태로
    cat = _load_catalysts()
    items = cat.get("region_catalysts", {}).get(region_code, [])
    if items:
        st.markdown("**등록된 호재**")
        for c in items:
            st.markdown(f"- 🏷️ **[{c.get('type','?')}]** {c.get('name','')}  — 점수 {c.get('score',0)}")
    else:
        st.caption("⚠️ 이 지역에는 등록된 수동 호재가 없습니다. "
                   "config/catalysts.json 에 직접 추가 가능합니다.")

    # 이 지역에서 추천된 단지 TOP 10 (rec_df가 있을 때만 — 추천 페이지 컨텍스트)
    if rec_df is not None and not rec_df.empty:
        region_rec = rec_df[rec_df["region_code"] == region_code]
        if not region_rec.empty:
            st.markdown(f"**이 지역의 추천 단지 TOP 10**")
            cols = ["apt_name", "area_bucket", "trade_median", "required_equity",
                    "catalyst_score", "sentiment_score", "price_growth_%", "expected_roi_%"]
            cols = [c for c in cols if c in region_rec.columns]
            render_table(region_rec[cols].head(10))


def _render_compare_view(
    seed_man: int, months: int, min_deals: int,
    ownership: str, first_time: bool, use_loan: bool,
    catalyst_weight: float, tier_weight: float, prestige_weight: float,
    dsr_cap_man, top_n: int, area_range, year_range,
):
    """3전략 동시 비교 — 겹치는 단지가 높은 확신도."""
    st.markdown("### 🔀 3전략 동시 비교")
    st.caption(
        "같은 조건으로 투자수익·갭투자·임대수익을 동시 실행합니다. "
        "여러 전략 상위권에 겹치는 단지일수록 확신도가 높습니다."
    )

    with st.spinner("3전략 계산 중..."):
        rec_inv = _cached_investment(seed_man, months, min_deals, ownership, first_time,
                                      use_loan, catalyst_weight, tier_weight, prestige_weight, dsr_cap_man)
        rec_gap = _cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man)
        rec_yld = _cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)

    def _prep(df):
        if df.empty:
            return df
        df = df.copy()
        if area_range and "area_bucket" in df.columns:
            df = df[(df["area_bucket"] >= area_range[0]) & (df["area_bucket"] <= area_range[1])]
        if year_range and "build_year" in df.columns:
            df = df[df["build_year"].notna()
                    & (df["build_year"] >= year_range[0])
                    & (df["build_year"] <= year_range[1])]
        df["지역"] = df["region_code"].map(REGION_MAP).fillna(df["region_code"])
        return df.head(top_n).reset_index(drop=True)

    inv = _prep(rec_inv)
    gap = _prep(rec_gap)
    yld = _prep(rec_yld)

    def _keys(df):
        if df.empty or not {"apt_name", "region_code", "area_bucket"}.issubset(df.columns):
            return set()
        return set(zip(df["apt_name"], df["region_code"], df["area_bucket"]))

    k_inv, k_gap, k_yld = _keys(inv), _keys(gap), _keys(yld)
    all3 = k_inv & k_gap & k_yld
    any2 = ((k_inv & k_gap) | (k_inv & k_yld) | (k_gap & k_yld)) - all3

    def _badge(r):
        k = (r["apt_name"], r["region_code"], r["area_bucket"])
        if k in all3: return "🏆 3전략"
        if k in any2: return "🔶 2전략"
        return ""

    for df in [inv, gap, yld]:
        if not df.empty:
            df["일치"] = df.apply(_badge, axis=1)

    # ── 교집합 섹션 ──
    if all3:
        st.success(f"🏆 **3전략 모두 상위권 — {len(all3)}개 단지** | 시세차익 + 갭 진입 + 월세수익 동시 유망")
        over = inv[inv["일치"] == "🏆 3전략"][["지역", "apt_name", "area_bucket", "trade_median", "score"]].copy()
        over.insert(0, "순위", range(1, len(over) + 1))
        over["매매가(억)"] = (over["trade_median"] / 10000).round(2)
        st.dataframe(over[["순위", "지역", "apt_name", "area_bucket", "매매가(억)", "score"]]
                     .rename(columns={"apt_name": "단지", "area_bucket": "면적(㎡)", "score": "투자수익점수"}),
                     hide_index=True, width='stretch')
    elif any2:
        st.info(f"🔶 **2전략 이상 상위권 — {len(any2)}개 단지**")
    else:
        st.caption("현재 조건에서 두 전략 이상 겹치는 단지 없음 — 단지 수(top_n) 늘리거나 최소 거래수 낮춰보세요.")

    if any2:
        with st.expander(f"🔶 2전략 이상 겹치는 단지 ({len(any2)}개)", expanded=bool(not all3)):
            rows = []
            for df, label in [(inv, "🚀투자수익"), (gap, "🏠갭투자"), (yld, "💰임대수익")]:
                if df.empty: continue
                sub = df[df["일치"].isin(["🏆 3전략", "🔶 2전략"])].copy()
                sub["전략"] = label
                rows.append(sub[["지역", "apt_name", "area_bucket", "trade_median", "전략"]])
            if rows:
                m = pd.concat(rows)
                m["매매가(억)"] = (m["trade_median"] / 10000).round(2)
                piv = m.groupby(["지역", "apt_name", "area_bucket", "매매가(억)"])["전략"].apply(
                    lambda x: " · ".join(sorted(set(x)))
                ).reset_index()
                st.dataframe(piv.rename(columns={"apt_name": "단지", "area_bucket": "면적(㎡)"}),
                             hide_index=True, width='stretch')

    st.markdown("---")

    # ── 전략별 탭 ──
    tab_inv, tab_gap, tab_yld = st.tabs(["🚀 투자수익", "🏠 갭투자", "💰 임대수익"])

    with tab_inv:
        if inv.empty:
            st.warning("해당 조건의 투자수익 매물 없음")
        else:
            show = inv.copy()
            show.insert(0, "순위", range(1, len(show) + 1))
            show["매매가(억)"] = (show["trade_median"] / 10000).round(2)
            cols = ["순위", "일치", "지역", "apt_name", "area_bucket", "매매가(억)", "score"]
            if "expected_roi_%" in show.columns: cols.append("expected_roi_%")
            if "tier_label" in show.columns: cols.append("tier_label")
            st.dataframe(show[cols].rename(columns={
                "apt_name": "단지", "area_bucket": "면적(㎡)", "score": "점수",
                "expected_roi_%": "예상수익률(%)", "tier_label": "지역등급",
            }), hide_index=True, width='stretch')

    with tab_gap:
        if gap.empty:
            st.warning("해당 조건의 갭투자 매물 없음")
        else:
            show = gap.copy()
            show.insert(0, "순위", range(1, len(show) + 1))
            show["매매가(억)"] = (show["trade_median"] / 10000).round(2)
            show["갭(억)"] = (show["gap"] / 10000).round(2)
            cols = ["순위", "일치", "지역", "apt_name", "area_bucket", "매매가(억)", "갭(억)", "jeonse_ratio", "score"]
            if "jeonse_risk" in show.columns: cols.append("jeonse_risk")
            st.dataframe(show[[c for c in cols if c in show.columns]].rename(columns={
                "apt_name": "단지", "area_bucket": "면적(㎡)", "score": "점수",
                "jeonse_ratio": "전세가율(%)", "jeonse_risk": "역전세리스크",
            }), hide_index=True, width='stretch')

    with tab_yld:
        if yld.empty:
            st.warning("해당 조건의 임대수익 매물 없음")
        else:
            show = yld.copy()
            show.insert(0, "순위", range(1, len(show) + 1))
            show["매매가(억)"] = (show["trade_median"] / 10000).round(2)
            if "required_equity" in show.columns:
                show["필요자본(억)"] = (show["required_equity"] / 10000).round(2)
            cols = ["순위", "일치", "지역", "apt_name", "area_bucket", "매매가(억)", "score"]
            if "annual_yield_%" in show.columns: cols.append("annual_yield_%")
            if "필요자본(억)" in show.columns: cols.append("필요자본(억)")
            st.dataframe(show[[c for c in cols if c in show.columns]].rename(columns={
                "apt_name": "단지", "area_bucket": "면적(㎡)", "score": "점수",
                "annual_yield_%": "연수익률(%)",
            }), hide_index=True, width='stretch')


def render_recommend_tab(inputs: dict):
    seed_eok = inputs["seed_eok"]
    ownership = inputs["ownership"]
    first_time = inputs["first_time"]
    use_loan = inputs["use_loan"]
    strategy = inputs["strategy"]
    months = inputs["months"]
    min_deals = inputs["min_deals"]
    top_n = inputs["top_n"]
    catalyst_weight = inputs["catalyst_weight"]
    tier_weight = inputs.get("tier_weight", 0.6)
    prestige_weight = inputs.get("prestige_weight", 0.10)
    area_range = inputs.get("area_range")
    year_range = inputs.get("year_range")
    submitted = inputs["submitted"]
    use_dsr = inputs.get("use_dsr", False)
    # DSR 한도는 _personal_inputs_block 에서 이미 계산해서 전달
    dsr_cap_man = inputs.get("dsr_cap_man")

    if not submitted and not st.session_state.get("rec_has_run", False):
        st.info(
            "👈 왼쪽 사이드바에서 **추천 검색 조건**을 설정하고 "
            "**🔍 검색** 버튼을 누르세요."
        )
        return
    if submitted:
        st.session_state["rec_has_run"] = True

    seed_man = int(seed_eok * 10000)

    # 헤더 - 현재 조건 요약
    from src.analysis.loan import get_ltv_pct, max_purchase_man
    ltv_규제 = get_ltv_pct("11680", ownership, first_time)
    ltv_비규제 = get_ltv_pct("99999", ownership, first_time)
    # 규제·비규제 별 실제 최대 매수가 (시드 + LTV + cap + DSR 다 반영)
    max_buy_reg = max_purchase_man(seed_man, "11680", ownership, first_time, dsr_cap_man) if use_loan else seed_man
    max_buy_nonreg = max_purchase_man(seed_man, "99999", ownership, first_time, dsr_cap_man) if use_loan else seed_man

    # 부대비용 포함 실제 최대 매수가 (격자 탐색 1000만원 단위)
    from src.analysis.costs import total_acquisition_cost_man as _tacm
    from src.analysis.loan import loan_capacity_man as _lcm
    def _max_buy_net(seed, rc, own, ft, dsr, loan_ok):
        best = 0
        for p in range(1000, 300000, 1000):
            lv = _lcm(p, rc, own, ft, dsr) if loan_ok else 0
            eq = p - lv
            if eq > seed:
                break
            if eq + _tacm(p, own, ft)["total"] <= seed:
                best = p
        return best
    max_buy_reg_net    = _max_buy_net(seed_man, "11680", ownership, first_time, dsr_cap_man, use_loan)
    max_buy_nonreg_net = _max_buy_net(seed_man, "99999", ownership, first_time, dsr_cap_man, use_loan)
    costs_reg    = _tacm(max_buy_reg_net,    ownership, first_time)
    costs_nonreg = _tacm(max_buy_nonreg_net, ownership, first_time)
    header = (
        f"**조건:** 시드 {seed_eok}억 · {ownership}"
        f"{' · 생애최초' if first_time else ''}"
        f"{' · 대출O' if use_loan else ' · 대출X'}"
        f"  ·  LTV 규제 {ltv_규제:.0f}% / 비규제 {ltv_비규제:.0f}%"
        f"  ·  규제지역 한도 cap 6억(15억↓) / 4억(15~25) / 2억(25↑)"
    )
    if use_dsr and dsr_cap_man is not None:
        header += f"  ·  💳 **DSR 대출 한도 {dsr_cap_man/10000:.2f}억**"
    st.markdown(header)


    if use_dsr and dsr_cap_man is not None and dsr_cap_man < 60000:
        st.warning(
            f"⚠️ DSR 한도({dsr_cap_man/10000:.2f}억)가 LTV 한도(6억)보다 작습니다. "
            "실제 대출은 DSR 쪽이 binding 됩니다."
        )

    if strategy == "🔀 전략 비교":
        _render_compare_view(
            seed_man=seed_man,
            months=months,
            min_deals=min_deals,
            ownership=ownership,
            first_time=first_time,
            use_loan=use_loan,
            catalyst_weight=catalyst_weight,
            tier_weight=tier_weight,
            prestige_weight=prestige_weight,
            dsr_cap_man=dsr_cap_man,
            top_n=top_n,
            area_range=area_range,
            year_range=year_range,
        )
        return

    if strategy == "🚀 투자수익":
        st.info(
            f"💡 **투자수익 전략** — 미래 상승을 노리는 **레버리지 매수**\n\n"
            f"- 자금구조: 자기자본 {seed_eok}억 + **LTV 대출** = 매매가\n"
            f"- 매수 후 매도까지 보유 (실거주 또는 단순 보유)\n"
            f"- 매월 이자 부담 있음 (≈ 대출액 × 4~5% / 12)\n"
            f"- 종합점수 = **호재({int(catalyst_weight*100)}%)** + **상급지등급({int(tier_weight*100)}%)** + **대장단지({int(prestige_weight*100)}%)** + 과거상승 + 레버리지수익률 + 시드활용\n"
            f"- 상급지등급: 2022~23 규제지역 해제 순서 기반 (강남3구·용산=100, 서울 비강남=80, 인천/경기=60, 지방=40)\n"
            f"- 대장단지: 시군구 내 평당가 백분위(60%) + 동(dong) 평당가 백분위(40%). 그 지역의 1군 단지에 가산점.\n\n"
            f"⚙️ `config/catalysts.json`·`config/region_tiers.json` 직접 편집 가능"
        )
        rec = _cached_investment(seed_man, months, min_deals,
                                  ownership, first_time, use_loan, catalyst_weight,
                                  tier_weight, prestige_weight, dsr_cap_man)
        metric_col = "expected_roi_%"

        # 등록된 호재 보기
        from src.analysis.recommend import _load_catalysts, manual_catalyst_text
        with st.expander("📋 등록된 호재 목록 (config/catalysts.json)"):
            cat = _load_catalysts()
            rc = cat.get("region_catalysts", {})
            if not rc:
                st.write("등록된 호재 없음")
            else:
                rows = []
                for code, items in rc.items():
                    rname = REGION_MAP.get(code, code) if "REGION_MAP" in globals() else code
                    for c in items:
                        rows.append({
                            "지역": rname,
                            "유형": c.get("type", ""),
                            "내용": c.get("name", ""),
                            "점수": c.get("score", 0),
                        })
                st.dataframe(pd.DataFrame(rows), width='stretch', height=400)
            st.caption("호재 추가/수정: `config/catalysts.json` 직접 편집. 저장 후 사이드바 [🔄 캐시 비우기].")
    elif strategy == "갭투자":
        st.info(
            f"💡 **갭투자 전략** — 전세 끼고 매수, 차익 노림수\n\n"
            f"- 자금구조: 자기자본 {seed_eok}억 = **매매가 − 전세보증금(갭)**\n"
            f"- 대출 X (전세보증금이 임차인 부담분) · 매월 이자 부담 없음\n\n"
            f"**종합점수 구성**\n"
            f"- 전세가율 적정구간 25% — 65~78%가 최적(역U자형). 너무 높으면 역전세 위험\n"
            f"- 전세가율 상승 추세 20% — 갭이 줄어드는 방향 = 매매전환 신호\n"
            f"- 상급지 등급 20% — 나중에 팔기 쉬운 지역\n"
            f"- 갭 레버리지 배수 20% — 매매가÷갭 (적은 돈으로 큰 자산)\n"
            f"- 거래 활성도 15% — 유동성\n\n"
            f"⚠️ **역전세 리스크**: 전세가율 90%↑ 위험 · 83%↑ 또는 전세가 하락 추세 주의"
        )
        rec = _cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man)
        metric_col = "gap"
    elif strategy == "임대수익":
        st.info(
            f"💡 **임대수익 전략**: 자기자본 + 보증금 + LTV 대출로 매수, 월세로 수익. "
            "필요자기자본 = 매매가 − 보증금중위 − 대출가능액."
        )
        rec = _cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        metric_col = "annual_yield_%"
    else:  # 자가매입
        st.info(
            f"💡 **자가매입 전략**: 자기자본(시드 {seed_eok}억) + LTV 대출로 매수. "
            "지역 평균 평당가 대비 저평가된 곳을 상위 배치."
        )
        rec = _cached_outright(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        metric_col = "ppp_median"

    if rec.empty:
        st.warning(
            f"해당 조건을 만족하는 매물이 없습니다.\n\n"
            f"- 시드를 늘려보세요\n"
            f"- 분석 기간을 늘려보세요\n"
            f"- 최소 거래수를 낮춰보세요"
        )
        return

    # 부대비용 컬럼 추가 (모든 필터에 공통 사용)
    rec["_acq_cost"] = rec["trade_median"].apply(
        lambda p: _tacm(p, ownership, first_time)["total"]
    )
    # 🛡️ 안전망: 부대비용 포함 실제 현금(자기자본+부대비용) ≤ 시드
    if "required_equity" in rec.columns:
        rec = rec[(rec["required_equity"] > 0)
                  & (rec["required_equity"] + rec["_acq_cost"] <= seed_man)].reset_index(drop=True)
    elif "gap" in rec.columns:
        rec = rec[(rec["gap"] > 0)
                  & (rec["gap"] + rec["_acq_cost"] <= seed_man)].reset_index(drop=True)

    # 평형/준공연도 사용자 필터
    if area_range and "area_bucket" in rec.columns:
        a_lo, a_hi = area_range
        rec = rec[(rec["area_bucket"] >= a_lo) & (rec["area_bucket"] <= a_hi)].reset_index(drop=True)
    if year_range and "build_year" in rec.columns:
        y_lo, y_hi = year_range
        # build_year NaN 매물은 제외
        rec = rec[rec["build_year"].notna()
                  & (rec["build_year"] >= y_lo)
                  & (rec["build_year"] <= y_hi)].reset_index(drop=True)

    if rec.empty:
        st.warning(
            f"시드 {seed_eok}억 + 대출(LTV·DSR 반영)로 매수 가능한 매물이 없습니다.\n\n"
            f"- 규제지역 최대 매수가: **{max_buy_reg/10000:.2f}억**\n"
            f"- 비규제지역 최대 매수가: **{max_buy_nonreg/10000:.2f}억**\n\n"
            f"시드를 늘리거나 비규제지역을 검토하세요."
        )
        return

    # 지역명 컬럼 추가
    rec_disp = rec.copy()
    rec_disp["region"] = rec_disp["region_code"].map(REGION_MAP).fillna(rec_disp["region_code"])

    # 입지 점수 (카카오 키 있을 때만 활성)
    if is_kakao_ready():
        cc1, cc2 = st.columns([1, 5])
        with cc1:
            enable_loc = st.checkbox("🚇 입지점수 계산", value=False,
                                      help="상위 TOP N 단지에 한해 카카오 API 호출 (캐시 사용)")
        with cc2:
            if enable_loc:
                st.caption(
                    "단지 주변 1km 지하철·학교·마트·병원 개수를 점수화 (캐시: data/processed/apt_locations.json)"
                )
        if enable_loc:
            rec_disp = enrich_with_location(rec_disp.head(top_n), max_calls=30,
                                              region_map=REGION_MAP)
    else:
        st.caption("💡 카카오 REST API 키를 .env 에 추가하면 입지점수 기능 활성화됩니다.")

    # 규제/비규제 실제 대출액 + 바인딩 요인 계산
    _loan_reg = max_buy_reg - seed_man
    _loan_nonreg = max_buy_nonreg - seed_man
    # LTV가 허용하는 대출 (시드 / (1 - LTV%) × LTV%)
    _ltv_loan_reg = seed_man * ltv_규제 / (100 - ltv_규제)
    _ltv_loan_nonreg = seed_man * ltv_비규제 / (100 - ltv_비규제)
    # 한도 cap: 매매가에 따라 다름 (규제지역만 적용)
    _cap_reg = (60000 if max_buy_reg <= 150000
                else 40000 if max_buy_reg <= 250000
                else 20000)
    # 바인딩 요인 판별 — 세 한도 중 가장 작은 값이 실제 대출을 결정
    _limits_reg = [(_ltv_loan_reg, f"LTV {ltv_규제:.0f}%"),
                   (_cap_reg,       f"한도 cap {_cap_reg//10000}억")]
    if dsr_cap_man is not None:
        _limits_reg.append((dsr_cap_man, f"DSR 한도 {dsr_cap_man/10000:.1f}억"))
    _bind_reg = min(_limits_reg, key=lambda x: x[0])[1]

    _limits_nonreg = [(_ltv_loan_nonreg, f"LTV {ltv_비규제:.0f}%")]
    if dsr_cap_man is not None:
        _limits_nonreg.append((dsr_cap_man, f"DSR 한도 {dsr_cap_man/10000:.1f}억"))
    _bind_nonreg = min(_limits_nonreg, key=lambda x: x[0])[1]

    # 툴팁용 값 미리 계산
    _loan_reg_net    = _lcm(max_buy_reg_net,    "11680", ownership, first_time, dsr_cap_man)
    _loan_nonreg_net = _lcm(max_buy_nonreg_net, "99999", ownership, first_time, dsr_cap_man)
    _eq_reg_net    = (max_buy_reg_net    - _loan_reg_net)    / 10000
    _eq_nonreg_net = (max_buy_nonreg_net - _loan_nonreg_net) / 10000
    _cash_reg    = (_eq_reg_net    + costs_reg["total"]    / 10000)
    _cash_nonreg = (_eq_nonreg_net + costs_nonreg["total"] / 10000)
    _dsr_str = f"{dsr_cap_man/10000:.2f}억" if dsr_cap_man else "미적용"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("매물 후보", f"{len(rec):,} 건")
    c2.metric("단지 수", f"{rec['apt_name'].nunique():,} 개")
    c3.metric("지역 수", f"{rec['region_code'].nunique():,} 개")
    c4.metric("🏙️ 규제지역 최대 매수가", f"{max_buy_reg_net/10000:.2f} 억",
              help=(
                  f"【부대비용 포함 실제 한도】\n"
                  f"매수가 {max_buy_reg_net/10000:.2f}억 = 자기자본 {_eq_reg_net:.2f}억 + 대출 {_loan_reg_net/10000:.2f}억\n"
                  f"총 필요 현금: 자기자본 {_eq_reg_net:.2f}억 + 부대비용 {costs_reg['total']/10000:.2f}억 = {_cash_reg:.2f}억 (시드 {seed_man/10000:.1f}억 이내)\n"
                  f"  · 취득세 {costs_reg['acquisition_tax']:,}만 / 중개 {costs_reg['broker_fee']:,}만 / 등기 {costs_reg['registration_etc']:,}만\n\n"
                  f"【대출 결정 요인: {_bind_reg}】\n"
                  f"① LTV {ltv_규제:.0f}%: 허용 대출 {_ltv_loan_reg/10000:.2f}억\n"
                  f"② 한도 cap: {_cap_reg//10000}억 (매매가 {max_buy_reg_net/10000:.1f}억 기준)\n"
                  f"③ DSR: {_dsr_str}\n\n"
                  f"※ 부대비용 전 이론 한도 {max_buy_reg/10000:.2f}억 → 포함 시 {max_buy_reg_net/10000:.2f}억\n"
                  "※ LTV: 강남3구·용산 40% / 기타 규제 50% / 생애최초 +10%p"
              ))
    c5.metric("🏞️ 비규제지역 최대 매수가", f"{max_buy_nonreg_net/10000:.2f} 억",
              help=(
                  f"【부대비용 포함 실제 한도】\n"
                  f"매수가 {max_buy_nonreg_net/10000:.2f}억 = 자기자본 {_eq_nonreg_net:.2f}억 + 대출 {_loan_nonreg_net/10000:.2f}억\n"
                  f"총 필요 현금: 자기자본 {_eq_nonreg_net:.2f}억 + 부대비용 {costs_nonreg['total']/10000:.2f}억 = {_cash_nonreg:.2f}억 (시드 {seed_man/10000:.1f}억 이내)\n"
                  f"  · 취득세 {costs_nonreg['acquisition_tax']:,}만 / 중개 {costs_nonreg['broker_fee']:,}만 / 등기 {costs_nonreg['registration_etc']:,}만\n\n"
                  f"【대출 결정 요인: {_bind_nonreg}】\n"
                  f"① LTV {ltv_비규제:.0f}%: 허용 대출 {_ltv_loan_nonreg/10000:.2f}억\n"
                  f"② DSR: {_dsr_str}\n\n"
                  f"※ 부대비용 전 이론 한도 {max_buy_nonreg/10000:.2f}억 → 포함 시 {max_buy_nonreg_net/10000:.2f}억\n"
                  "※ LTV: 무주택 70% (생애최초 80%) / 1주택 60% / 다주택 50%, 한도 cap 없음"
              ))
    if strategy == "🚀 투자수익":
        c6.metric("최고 예상수익률(자기자본)", f"{rec['expected_roi_%'].max():.2f} %")
    elif strategy == "임대수익":
        c6.metric("최고 연수익률", f"{rec['annual_yield_%'].max():.2f} %")
    elif strategy == "갭투자":
        c6.metric("최저 갭", f"{rec['gap'].min()/10000:.2f} 억")
    else:
        c6.metric("최저 자기자본", f"{rec['required_equity'].min()/10000:.2f} 억")

    if strategy == "🚀 투자수익":
        st.markdown("### 🏆 지역 추천순위")
        st.caption(
            f"✅ 시드 {seed_eok}억 기준 (부대비용 포함) · "
            f"규제지역 최대 **{max_buy_reg_net/10000:.2f}억** / "
            f"비규제지역 최대 **{max_buy_nonreg_net/10000:.2f}억** 이내 매물이 "
            "1건 이상 있는 지역만 표시."
        )
        st.caption(
            f"종합점수 = 매수심리×{int((1-tier_weight)*60)}% + 상급지등급×{int(tier_weight*100)}% + 호재×{int((1-tier_weight)*40)}%. "
            "상급지 가중치 슬라이더로 가산점 비중 조절."
        )

        sent_df = _cached_region_sentiment()
        from src.analysis.recommend import region_tier_score, region_tier_label
        from src.analysis.loan import max_purchase_man

        # 매수가능 매물 (시드 통과 + UI 한도 컷 반영)
        buyable_rec = rec[(rec["required_equity"] + rec["_acq_cost"] <= seed_man)].copy()
        # 지역별 매매가 한도 컷 (단지 추천표와 동일 규칙 적용 — 일관성)
        if not buyable_rec.empty:
            mb_map = {
                c: (max_purchase_man(seed_man, c, ownership, first_time, dsr_cap_man)
                    if use_loan else seed_man)
                for c in buyable_rec["region_code"].unique()
            }
            buyable_rec["_max_buy"] = buyable_rec["region_code"].map(mb_map)
            buyable_rec = buyable_rec[buyable_rec["trade_median"] <= buyable_rec["_max_buy"]].drop(columns="_max_buy")
        # UI 필터 적용 (사이드바에서 받은 면적·연도)
        if area_range and "area_bucket" in buyable_rec.columns:
            a_lo, a_hi = area_range
            buyable_rec = buyable_rec[(buyable_rec["area_bucket"] >= a_lo) & (buyable_rec["area_bucket"] <= a_hi)]
        if year_range and "build_year" in buyable_rec.columns:
            y_lo, y_hi = year_range
            buyable_rec = buyable_rec[buyable_rec["build_year"].notna()
                                     & (buyable_rec["build_year"] >= y_lo)
                                     & (buyable_rec["build_year"] <= y_hi)]

        # ─── 시군구 단위 요약 표 (한눈에 비교) ──────────────────
        if not buyable_rec.empty:
            sig = buyable_rec.groupby("region_code").agg(
                n_buyable=("apt_name", "count"),
                n_apts=("apt_name", "nunique"),
                max_score=("score", "max"),
                avg_score=("score", "mean"),
                best_roi_=("expected_roi_%", "max"),
                avg_growth_=("price_growth_%", "mean"),
                min_trade=("trade_median", "min"),
                avg_prestige=("prestige_score", "mean"),
            ).reset_index()
            sig["region"] = sig["region_code"].map(REGION_MAP).fillna(sig["region_code"])
            sig["tier_label"] = (
                sig["region_code"].apply(region_tier_label).astype(str)
                .str.extract(r"^(\d)", expand=False)
            )
            sig = sig.sort_values("max_score", ascending=False).reset_index(drop=True)
            sig["rank"] = range(1, len(sig) + 1)
            sig["best_score"] = sig["max_score"].round(1)
            sig["avg_score"] = sig["avg_score"].round(1)
            sig["best_roi_%"] = sig["best_roi_"].round(2)
            sig["avg_growth_%"] = sig["avg_growth_"].round(2)
            sig["avg_prestige"] = sig["avg_prestige"].round(1)
            cols_sig = ["rank", "region", "tier_label",
                        "n_buyable", "n_apts",
                        "best_score", "avg_score", "avg_prestige",
                        "best_roi_%", "avg_growth_%", "min_trade"]
            st.markdown("#### 📊 시군구 한눈 요약 (점수·매물수·수익률)")
            st.caption("매수가능 매물 기준 시군구 집계. 최고점수 내림차순.")
            render_table(sig[cols_sig].head(30), height=380)
            st.markdown("")
        # ────────────────────────────────────────────────────
        if "dong" in buyable_rec.columns:
            buyable_rec["dong"] = buyable_rec["dong"].fillna("").astype(str).str.strip()
            buyable_rec.loc[buyable_rec["dong"] == "", "dong"] = "(동 미상)"
        else:
            buyable_rec["dong"] = "(동 미상)"

        # (시군구, 동) 단위 집계 — 동탄/새솔동 같은 sub-지역이 분리됨
        dong_stats = buyable_rec.groupby(["region_code", "dong"]).agg(
            n_buyable=("apt_name", "count"),
            min_equity=("required_equity", "min"),
            min_trade=("trade_median", "min"),
            avg_score=("score", "mean"),
            avg_prestige=("prestige_score", "mean") if "prestige_score" in buyable_rec.columns else ("apt_name", "count"),
        ).reset_index()
        dong_stats = dong_stats[dong_stats["n_buyable"] > 0].copy()

        if dong_stats.empty:
            st.info("매수 가능한 매물이 있는 지역이 없습니다.")
        else:
            # 시군구 메타 (sentiment / catalyst / tier)
            sent_meta = sent_df[["region_code", "avg_sentiment", "manual_catalyst", "catalyst_text"]] if not sent_df.empty else pd.DataFrame(columns=["region_code"])
            dong_stats = dong_stats.merge(sent_meta, on="region_code", how="left")
            dong_stats["avg_sentiment"] = dong_stats.get("avg_sentiment", pd.Series(50.0)).fillna(50.0)
            dong_stats["manual_catalyst"] = dong_stats.get("manual_catalyst", pd.Series(0.0)).fillna(0.0)
            dong_stats["region"] = dong_stats["region_code"].map(REGION_MAP).fillna(dong_stats["region_code"])
            dong_stats["tier_label"] = (
                dong_stats["region_code"].apply(region_tier_label)
                .astype(str).str.extract(r"^(\d)", expand=False)
            )
            dong_stats["tier_score"] = dong_stats["region_code"].apply(region_tier_score)

            # (동 단위) 종합점수: 단지 추천 score 평균이 가장 직접적인 sub-지역 강도
            #   + 상급지 가중치 반영
            tw = max(0.0, min(1.0, tier_weight))
            rest = 1.0 - tw
            dong_stats["region_rank_score"] = (
                dong_stats["avg_score"].fillna(50) * (rest * 0.50)
                + dong_stats["tier_score"] * tw
                + dong_stats["avg_prestige"].fillna(50) * (rest * 0.30)
                + dong_stats["avg_sentiment"] * (rest * 0.10)
                + dong_stats["manual_catalyst"] * (rest * 0.10)
            ).round(1)

            dong_stats = dong_stats.sort_values("region_rank_score", ascending=False).reset_index(drop=True)
            dong_top = dong_stats.head(40).copy()
            dong_top["rank"] = range(1, len(dong_top) + 1)
            dong_top["min_equity_억"] = (dong_top["min_equity"] / 10000).round(2)
            dong_top["min_trade_억"] = (dong_top["min_trade"] / 10000).round(2)

            st.caption("👇 각 (지역·동)을 펼치면 그 동 안의 매수가능 매물이 전부 나옵니다. "
                       "최대한 작은 단위(동)로 쪼개 표시.")

            for _, row in dong_top.iterrows():
                code = row["region_code"]
                dong = row["dong"]
                name = row["region"]
                rk = int(row["rank"])
                score = row["region_rank_score"]
                n_buy = int(row["n_buyable"])
                min_eq_eok = row["min_equity_억"]
                min_tr_eok = row["min_trade_억"]
                tier = row["tier_label"] or "-"

                full_name = f"{name} · {dong}" if dong != "(동 미상)" else f"{name} · (동 미상)"
                header = (
                    f"#{rk:>2}  {full_name}   "
                    f"급지 {tier}  ·  점수 {score:.1f}  ·  "
                    f"매물 {n_buy}건  ·  최저 자기자본 {min_eq_eok:.2f}억 / 매매가 {min_tr_eok:.2f}억"
                )
                with st.expander(header, expanded=(rk == 1)):
                    max_buy_sel = (
                        max_purchase_man(seed_man, code, ownership, first_time, dsr_cap_man)
                        if use_loan else seed_man
                    )
                    rgn_rec = buyable_rec[
                        (buyable_rec["region_code"] == code)
                        & (buyable_rec["dong"] == dong)
                    ].copy()
                    if "required_equity" in rgn_rec.columns:
                        rgn_rec = rgn_rec[
                            (rgn_rec["required_equity"] > 0)
                            & (rgn_rec["trade_median"] <= max_buy_sel)
                        ]
                    rgn_rec = rgn_rec.sort_values("score", ascending=False).reset_index(drop=True)
                    rgn_rec["apt_rank"] = range(1, len(rgn_rec) + 1)

                    if rgn_rec.empty:
                        st.info("매수 가능 매물이 없습니다.")
                        continue

                    # 네이버 검색은 '지역 동 단지명' 으로 좀 더 정확히
                    naver_q = f"{name} {dong}" if dong != "(동 미상)" else name
                    rgn_rec["naver_url"] = [
                        naver_land_url(naver_q, an) for an in rgn_rec["apt_name"]
                    ]

                    drill_cols = ["naver_url", "apt_rank", "apt_name", "trade_median", "required_equity",
                                   "tier_label", "area_bucket", "build_year",
                                   "catalyst_score", "sentiment_score",
                                   "price_growth_%", "expected_roi_%", "score"]
                    drill_cols = [c for c in drill_cols if c in rgn_rec.columns]
                    rgn_show = rgn_rec[drill_cols].copy()
                    rgn_show = rgn_show.rename(columns={"apt_rank": "rank"})
                    if "tier_label" in rgn_show.columns:
                        rgn_show["tier_label"] = (
                            rgn_show["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
                        )
                    render_table(rgn_show)
                    cat_text = row.get("catalyst_text")
                    if isinstance(cat_text, str) and cat_text:
                        st.caption(f"📌 등록호재: {cat_text}")

    elif strategy == "갭투자":
        st.markdown("### 🏆 지역별 갭투자 요약")
        st.caption("역전세 리스크 낮고 상급지인 지역 우선. 최고점수 내림차순.")

        gap_rec = rec[(rec["gap"] > 0) & (rec["gap"] + rec["_acq_cost"] <= seed_man)].copy()
        if not gap_rec.empty:
            # 역전세 리스크 분포
            risk_dist = gap_rec["jeonse_risk"].value_counts().reset_index()
            risk_dist.columns = ["리스크레벨", "건수"]

            rc1, rc2 = st.columns([1, 3])
            with rc1:
                st.markdown("**역전세 리스크 분포**")
                st.dataframe(risk_dist, hide_index=True, width='stretch')

            # 지역별 요약 집계
            rg = gap_rec.groupby("region_code").agg(
                n_opp=("apt_name", "count"),
                n_apts=("apt_name", "nunique"),
                min_gap=("gap", "min"),
                avg_ratio=("jeonse_ratio", "mean"),
                avg_leverage=("leverage_mult", "mean"),
                avg_accel=("jeonse_accel_%p", "mean"),
                max_score=("score", "max"),
            ).reset_index()
            rg["region"] = rg["region_code"].map(REGION_MAP).fillna(rg["region_code"])
            rg["safe_n"] = gap_rec.groupby("region_code")["jeonse_risk"].apply(
                lambda x: ((x == "✅ 적정") | (x == "🟢 갭여유")).sum()
            ).values
            rg["risk_n"] = gap_rec.groupby("region_code")["jeonse_risk"].apply(
                lambda x: (x == "⚠️ 역전세위험").sum()
            ).values
            rg = rg.sort_values("max_score", ascending=False).reset_index(drop=True)
            rg.insert(0, "rank", range(1, len(rg) + 1))
            rg["최저갭(억)"] = (rg["min_gap"] / 10000).round(2)
            rg["평균전세가율(%)"] = rg["avg_ratio"].round(1)
            rg["전세가율추세(%p)"] = rg["avg_accel"].round(2)
            rg["평균레버리지(배)"] = rg["avg_leverage"].round(1)
            rg["최고점수"] = rg["max_score"].round(1)

            show_cols = ["rank", "region", "n_opp", "최저갭(억)",
                         "평균전세가율(%)", "전세가율추세(%p)",
                         "safe_n", "risk_n",
                         "평균레버리지(배)", "최고점수"]
            rg_show = rg[show_cols].rename(columns={
                "n_opp": "기회수",
                "safe_n": "안전·적정",
                "risk_n": "역전세위험",
            })
            with rc2:
                st.dataframe(rg_show, hide_index=True, width='stretch', height=380)

    st.markdown(f"### 🎯 단지·평형 추천 TOP {top_n}")
    # 🛡️ 시드 안전망 + 매매가 한도 안전망 (지역별 max_purchase 계산해서 매매가 자체도 컷)
    from src.analysis.loan import max_purchase_man
    # 지역코드별 max_purchase 캐싱 (rec에 등장한 지역만)
    unique_codes = rec_disp["region_code"].unique() if "region_code" in rec_disp.columns else []
    max_buy_by_region = {
        c: max_purchase_man(seed_man, c, ownership, first_time, dsr_cap_man) if use_loan else seed_man
        for c in unique_codes
    }
    if "required_equity" in rec_disp.columns:
        before = len(rec_disp)
        # (1) 자기자본+부대비용 ≤ 시드, (2) 매매가 ≤ 지역별 매수 한도
        rec_disp["_max_buy"] = rec_disp["region_code"].map(max_buy_by_region)
        rec_disp = rec_disp[
            (rec_disp["required_equity"] > 0)
            & (rec_disp["required_equity"] + rec_disp["_acq_cost"] <= seed_man)
            & (rec_disp["trade_median"] <= rec_disp["_max_buy"])
        ].drop(columns=["_max_buy", "_acq_cost"]).reset_index(drop=True)
        dropped = before - len(rec_disp)
        if dropped > 0:
            st.caption(f"⚠️ 시드+대출한도+부대비용({seed_eok}억 기준) 초과 매물 {dropped}건 제외됨")
    if rec_disp.empty:
        st.warning(
            f"시드 {seed_eok}억 + 대출(LTV·DSR 반영)로 매수 가능한 매물이 없습니다. "
            f"위 '규제지역 최대 매수가' / '비규제지역 최대 매수가' 카드를 확인하세요."
        )
        return
    st.caption(
        f"✅ 자기자본 **{seed_eok}억** + 규제별 LTV·한도cap·DSR 반영해 매매가 자체가 매수 한도 이내인 매물만 표시. "
        f"필요자기자본 = 매매가 − 실대출, 매수 시 본인 부담 금액."
    )
    # 컬럼 순서: 네이버링크 → 추천순위 → 단지·가격 → 급지·면적·연도 → 분석지표
    if strategy == "🚀 투자수익":
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "tier_label",
                      "area_bucket", "build_year",
                      "catalyst_score", "sentiment_score",
                      "price_growth_%", "expected_roi_%",
                      "catalysts", "score"]
    elif strategy == "갭투자":
        cols_order = ["naver_url", "rank", "region", "apt_name",
                      "trade_median", "rent_median", "gap", "required_equity",
                      "jeonse_risk",
                      "jeonse_ratio", "jeonse_accel_%p",
                      "leverage_mult",
                      "tier_label",
                      "area_bucket", "build_year",
                      "trade_count", "rent_count", "score"]
    elif strategy == "임대수익":
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "area_bucket", "build_year",
                      "ltv_%", "loan_capacity",
                      "deposit_median", "monthly_median",
                      "annual_yield_%", "trade_count", "rent_count", "score"]
    else:  # 자가매입
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "area_bucket", "build_year",
                      "ltv_%", "loan_capacity",
                      "ppp_median", "region_median_ppp", "value_ratio",
                      "trade_count", "score"]

    # 추천 순위 부여: rec_disp는 이미 score 내림차순 정렬 → 1,2,3...
    rec_disp_ranked = rec_disp.copy()
    rec_disp_ranked["rank"] = range(1, len(rec_disp_ranked) + 1)
    # 네이버 부동산 검색 링크 (지역명 + 단지명)
    rec_disp_ranked["naver_url"] = [
        naver_land_url(r.get("region"), r.get("apt_name"))
        for r in rec_disp_ranked.to_dict("records")
    ]
    rec_top = rec_disp_ranked[cols_order].head(top_n).copy()
    # tier_label "2_상급지" → "2" (숫자 한 자리만)
    if "tier_label" in rec_top.columns:
        rec_top["tier_label"] = rec_top["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
    render_table(rec_top, height=600)

    csv = rec_disp_ranked[cols_order].to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 추천 결과 CSV 다운로드", csv,
                        file_name=f"추천_{strategy}_{seed_eok}억_{date.today():%Y%m%d}.csv",
                        mime="text/csv")

    # ─── 🧪 단지 선택 후 스트레스 테스트 ───
    if "trade_median" in rec.columns and "loan_capacity" in rec.columns:
        st.markdown("---")
        st.markdown("### 🎯 관심 단지 깊이 분석")
        st.caption("아래에서 한 단지를 선택하면 5년 시나리오 + 스트레스 테스트가 표시됩니다.")
        rec_top = rec_disp.head(top_n).reset_index(drop=True)
        labels = [
            f"{r['region']} · {r['apt_name']} · {r['area_bucket']:.0f}㎡  "
            f"({r['trade_median']/10000:.2f}억)"
            for _, r in rec_top.iterrows()
        ]
        if labels:
            picked_idx = st.selectbox(
                "단지 선택", range(len(labels)),
                format_func=lambda i: labels[i],
                key="stress_picker",
            )
            selected = rec_top.iloc[picked_idx].to_dict()
            _render_stress_test(inputs, selected)


if __name__ == "__main__":
    main()
