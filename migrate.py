import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "src"))

from sqlalchemy import text
from briefing.database import get_engine

def migrate_v03():
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE raw_news_items ADD COLUMN ai_tags TEXT DEFAULT '[]'"))
        print("V0.3 迁移完成：ai_tags 列已添加")
    except Exception as e:
        if "duplicate column name" in str(e).lower():
            print("列 ai_tags 已存在，跳过迁移")
        else:
            print("迁移失败:", e)

if __name__ == "__main__":
    migrate_v03()
