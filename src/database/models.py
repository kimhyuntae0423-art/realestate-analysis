from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime,
    UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker

from config.settings import DATABASE_URL

Base = declarative_base()


class AptTrade(Base):
    """아파트 매매 실거래"""
    __tablename__ = "apt_trade"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_code = Column(String(5), index=True, nullable=False)
    deal_year = Column(Integer, nullable=False)
    deal_month = Column(Integer, nullable=False)
    deal_day = Column(Integer, nullable=False)
    deal_date = Column(Date, index=True, nullable=False)

    apt_name = Column(String(200), index=True, nullable=False)
    dong = Column(String(100))
    jibun = Column(String(50))
    road_name = Column(String(200))

    area_m2 = Column(Float, nullable=False)           # 전용면적
    floor = Column(Integer)
    build_year = Column(Integer)

    deal_amount = Column(Integer, nullable=False)     # 만원 단위
    price_per_pyeong = Column(Integer)                # 만원/평

    cancel_deal_type = Column(String(10))             # 해제여부 O/공란
    cancel_deal_day = Column(String(20))

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "region_code", "deal_date", "apt_name", "area_m2", "floor", "deal_amount",
            name="uq_trade"
        ),
        Index("ix_trade_region_date", "region_code", "deal_date"),
        Index("ix_trade_apt", "apt_name"),
    )


class AptRent(Base):
    """아파트 전월세 실거래"""
    __tablename__ = "apt_rent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_code = Column(String(5), index=True, nullable=False)
    deal_year = Column(Integer, nullable=False)
    deal_month = Column(Integer, nullable=False)
    deal_day = Column(Integer, nullable=False)
    deal_date = Column(Date, index=True, nullable=False)

    apt_name = Column(String(200), index=True, nullable=False)
    dong = Column(String(100))
    jibun = Column(String(50))

    area_m2 = Column(Float, nullable=False)
    floor = Column(Integer)
    build_year = Column(Integer)

    deposit = Column(Integer, nullable=False)         # 보증금 만원
    monthly_rent = Column(Integer, default=0)         # 월세 만원
    contract_type = Column(String(20))                # 신규/갱신

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "region_code", "deal_date", "apt_name", "area_m2", "floor", "deposit", "monthly_rent",
            name="uq_rent"
        ),
        Index("ix_rent_region_date", "region_code", "deal_date"),
    )


class SupplySchedule(Base):
    """시군구별 입주 예정 물량 (KOSIS/HUG 수집)."""
    __tablename__ = "supply_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_code = Column(String(5), index=True, nullable=False)
    move_in_date = Column(Date, index=True, nullable=False)  # 입주월 1일
    units = Column(Integer, nullable=False)                  # 입주 호수
    source = Column(String(50))                              # kosis / hug / manual
    note = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("region_code", "move_in_date", "source",
                         name="uq_supply"),
    )


class PopulationFlow(Base):
    """시군구별 월별 인구 순유입 (KOSIS 주민등록 인구이동)."""
    __tablename__ = "population_flow"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_code = Column(String(5), index=True, nullable=False)
    flow_date = Column(Date, index=True, nullable=False)     # 해당월 1일
    inflow = Column(Integer, default=0)                       # 전입
    outflow = Column(Integer, default=0)                      # 전출
    net_inflow = Column(Integer, nullable=False)              # 전입 - 전출
    source = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("region_code", "flow_date", name="uq_popflow"),
    )


class CollectionLog(Base):
    """수집 이력"""
    __tablename__ = "collection_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)        # molit_trade / molit_rent
    region_code = Column(String(5), nullable=False)
    year_month = Column(String(6), nullable=False)     # YYYYMM
    rows_fetched = Column(Integer, default=0)
    rows_inserted = Column(Integer, default=0)
    status = Column(String(20))                        # ok / fail
    error = Column(String(500))
    finished_at = Column(DateTime, default=datetime.utcnow)


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db():
    Base.metadata.create_all(engine)


init_db()
