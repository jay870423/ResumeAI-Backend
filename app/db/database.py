import aiosqlite
import os
from typing import Optional
from app.core.config import settings

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "resume.db")


async def init_db():
    """初始化数据库"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                resume_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                page_count INTEGER,
                raw_text TEXT,
                optimized_text TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analyzed_at TIMESTAMP,
                persona_json TEXT,
                analysis_json TEXT
            )
        """)
        await db.commit()


async def save_resume(
    resume_id: str,
    file_name: str,
    file_type: str,
    file_path: str,
    file_size: int,
    page_count: Optional[int] = None,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO resumes
               (resume_id, file_name, file_type, file_path, file_size, page_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (resume_id, file_name, file_type, file_path, file_size, page_count),
        )
        await db.commit()


async def get_resume(resume_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM resumes WHERE resume_id = ?", (resume_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def update_resume_text(resume_id: str, raw_text: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE resumes SET raw_text = ?, status = 'parsed' WHERE resume_id = ?",
            (raw_text, resume_id),
        )
        await db.commit()


async def update_resume_analysis(
    resume_id: str, analysis_json: str, persona_json: str
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """UPDATE resumes
               SET analysis_json = ?, persona_json = ?, status = 'analyzed',
                   analyzed_at = CURRENT_TIMESTAMP
               WHERE resume_id = ?""",
            (analysis_json, persona_json, resume_id),
        )
        await db.commit()


async def update_resume_optimized(resume_id: str, optimized_text: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """UPDATE resumes
               SET optimized_text = ?, status = 'optimized'
               WHERE resume_id = ?""",
            (optimized_text, resume_id),
        )
        await db.commit()
