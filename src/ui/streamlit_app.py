"""Streamlit 부동산 분석 대시보드

실행: streamlit run src/ui/streamlit_app.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import ROOT as APP_ROOT
ROOT = APP_ROOT

from src.ui.shared import _sidebar_nav
from src.ui.pages.map_signals import page_market_signals
from src.ui.pages.capacity import page_my_capacity
from src.ui.pages.undervalued import page_undervalued
from src.ui.pages.region import page_region
from src.ui.pages.backtest import page_strategy_backtest
from src.ui.pages.portfolio import page_portfolio_strategy
from src.ui.pages.invest import page_invest
from src.ui.pages.lab import page_lab


def main():
    page = _sidebar_nav()

    if page.startswith("💰"):
        page_my_capacity()
    elif page.startswith("🚀"):
        page_invest()
    elif page.startswith("💎"):
        page_undervalued()
    elif page.startswith("📊"):
        page_region()
    elif page.startswith("🚦"):
        page_market_signals()
    elif page.startswith("🔬"):
        page_strategy_backtest()
    elif page.startswith("🏘️"):
        page_portfolio_strategy()
    elif page.startswith("🧪"):
        page_lab()
    else:
        page_my_capacity()


if __name__ == "__main__":
    main()
