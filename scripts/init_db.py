"""DB 초기화 (테이블 생성)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database.models import init_db

if __name__ == "__main__":
    init_db()
    print("OK: DB 초기화 완료")
