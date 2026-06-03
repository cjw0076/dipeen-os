"""
reset_db.py — 개발용 DB 초기화 스크립트

새 컬럼(required_role, required_skills, AgentMessage 테이블 등) 추가 후
기존 dipeen.db를 삭제하고 새로 생성할 때 사용.

실행: cd api && python scripts/reset_db.py
"""

import asyncio
import os
import sys

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine, create_tables
from app.db.models import Base
from app.config import settings


async def reset():
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"삭제: {db_path}")

    await create_tables()
    print("DB 재생성 완료")
    print(f"테이블: {list(Base.metadata.tables.keys())}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset())
