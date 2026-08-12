"""컬럼 스펙, 테이블 렌더링, 단지명 정리·네이버 링크 헬퍼.

src/ui/shared.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from src.ui.shared.columns_spec import COL_SPEC


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
