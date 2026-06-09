import sqlite3
import random
from pathlib import Path

DB_PATH = Path(__file__).parent / "questions.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                source_file TEXT
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_sessions INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                total_answered INTEGER DEFAULT 0
            );
        """)


def save_questions(questions: list[dict], source_file: str) -> int:
    with get_conn() as conn:
        conn.execute("DELETE FROM questions WHERE source_file = ?", (source_file,))
        conn.executemany(
            """INSERT INTO questions
               (question, option_a, option_b, option_c, option_d, correct_answer, source_file)
               VALUES (:question, :option_a, :option_b, :option_c, :option_d, :correct_answer, :source_file)""",
            [{**q, "source_file": source_file} for q in questions],
        )
        return conn.execute(
            "SELECT COUNT(*) FROM questions WHERE source_file = ?", (source_file,)
        ).fetchone()[0]


def get_random_questions(n: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM questions").fetchall()
    if not rows:
        return []
    sample = random.sample(rows, min(n, len(rows)))
    return [dict(r) for r in sample]


def count_questions() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]


def update_stats(user_id: int, correct: int, answered: int):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO user_stats (user_id, total_sessions, total_correct, total_answered)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   total_sessions = total_sessions + 1,
                   total_correct = total_correct + excluded.total_correct,
                   total_answered = total_answered + excluded.total_answered""",
            (user_id, correct, answered),
        )


def get_stats(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None
