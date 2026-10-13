"""数据层：SQLite（标准库，零依赖）。

全部用户数据都在这里：用户 / 会话 / 相册文件夹 / 照片（图片以 BLOB 存库）/ 头像。
每次操作独立连接 + 行锁，规模足够（单机 demo）。
"""
import os
import sqlite3
import threading
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")
os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    salt TEXT NOT NULL,
    nickname TEXT DEFAULT '',
    avatar TEXT DEFAULT '',
    avatar_data BLOB,
    bio TEXT DEFAULT '',
    accent TEXT DEFAULT '#2563eb',
    role INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    shared INTEGER DEFAULT 0,
    parent_id INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id INTEGER NOT NULL,
    uploader_id INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    source TEXT DEFAULT 'upload',
    size INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT DEFAULT '危险作业区',
    x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER UNIQUE NOT NULL,
    report TEXT,
    counts TEXT,
    intrusions TEXT,
    intrusion_count INTEGER DEFAULT 0,
    model TEXT,
    annotated BLOB,
    created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA)
        # 旧库迁移（已存在则忽略）
        ucols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        if "role" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN role INTEGER DEFAULT 0")
        acols = {r[1] for r in conn.execute("PRAGMA table_info(albums)")}
        if "shared" not in acols:
            conn.execute("ALTER TABLE albums ADD COLUMN shared INTEGER DEFAULT 0")
        if "parent_id" not in acols:
            conn.execute("ALTER TABLE albums ADD COLUMN parent_id INTEGER DEFAULT 0")
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
        if "uploader_id" not in pcols:
            conn.execute("ALTER TABLE photos ADD COLUMN uploader_id INTEGER DEFAULT 0")


def query(sql, params=(), one=False):
    """查询，返回 dict 列表（或单条 dict）。"""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    data = [dict(r) for r in rows]
    return data[0] if one and data else (None if one else data)


def execute(sql, params=()):
    """写入，返回 lastrowid。"""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


init_db()
