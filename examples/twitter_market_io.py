"""
MarketIO implementation that reads timeline (posts + comments) from the same
SQLite database used by twitter_complex_demo.py. Use this when the Creator Agent
should observe feedback from a running or completed Twitter simulation.
"""
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

# Default db path: same as twitter_complex_demo.py (examples/data/twitter_50rounds.db)
_EXAMPLES_DIR = Path(__file__).resolve().parent
DEFAULT_TWITTER_DB_PATH = str(_EXAMPLES_DIR / "data" / "twitter_50rounds.db")


def get_twitter_db_path(db_path: str | None = None) -> str:
    """Resolve db path: argument > OASIS_DB_PATH env > default."""
    if db_path:
        return os.path.abspath(db_path)
    env_path = os.environ.get("OASIS_DB_PATH")
    if env_path:
        return os.path.abspath(env_path)
    return DEFAULT_TWITTER_DB_PATH


def ensure_twitter_db_seeded(db_path: str) -> bool:
    """
    若 DB 不存在或无 post/comment，则创建最小 schema 并插入种子数据，保证 fetch_timelines 可返回数据。
    返回 True 表示写入过种子数据，False 表示已有数据无需写入。
    """
    if not os.path.exists(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='post'")
    if cur.fetchone():
        cur.execute("SELECT COUNT(*) FROM post")
        if cur.fetchone()[0] > 0:
            conn.close()
            return False
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS user (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER, user_name TEXT, name TEXT, bio TEXT, created_at DATETIME,
            num_followings INTEGER DEFAULT 0, num_followers INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS post (
            post_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, original_post_id INTEGER,
            content TEXT DEFAULT '', quote_content TEXT, created_at DATETIME,
            num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0,
            num_shares INTEGER DEFAULT 0, num_reports INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES user(user_id)
        );
        CREATE TABLE IF NOT EXISTS comment (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, user_id INTEGER,
            content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0,
            FOREIGN KEY(post_id) REFERENCES post(post_id), FOREIGN KEY(user_id) REFERENCES user(user_id)
        );
    """)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM user")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO user (user_id, name, user_name) VALUES (1, 'TestUser', 'test_user')")
        cur.execute("INSERT INTO post (post_id, user_id, content) VALUES (1, 1, 'I want a tiny terminal game I can play during breaks.')")
        cur.execute("INSERT INTO comment (comment_id, post_id, user_id, content) VALUES (1, 1, 1, 'A simple puzzle or number game would be great.')")
        conn.commit()
    conn.close()
    return True


class TwitterDbMarket:
    """
    MarketIO that fetches timelines from the Twitter simulation SQLite db
    (posts + comments from twitter_complex_demo). post_update() appends to
    an in-memory list so the creator's own updates appear in fetch_timelines.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = get_twitter_db_path(db_path)
        self._my_updates: List[Dict[str, Any]] = []

    def fetch_timelines(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read posts and comments from the Twitter simulation db, newest first."""
        result: List[Dict[str, Any]] = []

        # Prepend creator's own updates (newest first)
        for item in reversed(self._my_updates):
            result.append(item)
            if len(result) >= limit:
                return result[:limit]

        if not os.path.exists(self._db_path):
            return result[:limit]

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Posts: post_id, user_id, name, content, created_at
            cur.execute("""
                SELECT p.post_id, p.user_id, u.name, p.content, p.created_at
                FROM post p JOIN user u ON p.user_id = u.user_id
                ORDER BY p.post_id DESC
            """)
            for row in cur.fetchall():
                result.append({
                    "user_id": row["user_id"],
                    "content": row["content"] or "",
                    "name": row["name"] or "",
                    "metadata": {"source": "post", "post_id": row["post_id"]},
                })
                if len(result) >= limit:
                    conn.close()
                    return result[:limit]

            # Comments: comment_id, user_id, name, content, post_id, created_at
            cur.execute("""
                SELECT c.comment_id, c.user_id, u.name, c.content, c.post_id, c.created_at
                FROM comment c JOIN user u ON c.user_id = u.user_id
                ORDER BY c.comment_id DESC
            """)
            for row in cur.fetchall():
                result.append({
                    "user_id": row["user_id"],
                    "content": row["content"] or "",
                    "name": row["name"] or "",
                    "metadata": {"source": "comment", "comment_id": row["comment_id"]},
                })
                if len(result) >= limit:
                    break

            conn.close()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass

        return result[:limit]

    def post_update(
        self,
        content: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Any:
        """Append a creator update (in-memory); does not write to the simulation db."""
        item = {
            "user_id": 0,
            "content": content,
            "metadata": metadata or {},
        }
        self._my_updates.append(item)
        print(f"[Market] posted update: {content}")
        return item
