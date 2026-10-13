"""认证与用户资料：注册 / 登录 / Token 会话 / 个人设置。

零第三方依赖：PBKDF2 哈希密码 + 随机 Token 会话；头像以 BLOB 存 SQLite。
"""
import hashlib
import secrets
import sqlite3

from fastapi import Header

from core import db

_ITERATIONS = 60000


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS).hex()


def register(username: str, password: str, nickname: str = ""):
    """注册；成功返回用户 dict，用户名已存在返回 None。"""
    username = (username or "").strip()
    if not username or not password:
        return None
    if db.query("SELECT id FROM users WHERE username=?", (username,), one=True):
        return None
    salt = secrets.token_hex(16)
    uid = db.execute(
        "INSERT INTO users (username, password, salt, nickname, created_at) VALUES (?,?,?,?,?)",
        (username, _hash(password, salt), salt, nickname or username, db.now()))
    return get_user(uid)


def login(username: str, password: str):
    """登录；成功返回 (token, user)，失败返回 (None, None)。"""
    user = db.query("SELECT * FROM users WHERE username=?", ((username or "").strip(),), one=True)
    if not user or user["password"] != _hash(password or "", user["salt"]):
        return None, None
    token = secrets.token_hex(32)
    db.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
               (token, user["id"], db.now()))
    return token, public(user)


def logout(token: str):
    if token:
        db.execute("DELETE FROM sessions WHERE token=?", (token,))


def get_user(user_id: int):
    user = db.query("SELECT * FROM users WHERE id=?", (user_id,), one=True)
    return public(user) if user else None


def public(user: dict):
    """去掉敏感字段（密码 / 盐 / 头像二进制）。"""
    return {k: user.get(k) for k in
            ("id", "username", "nickname", "avatar", "bio", "accent", "role", "created_at")}


def user_by_token(authorization: str):
    """从 Authorization: Bearer <token> 解析当前用户；无效返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    row = db.query("SELECT user_id FROM sessions WHERE token=?", (token,), one=True)
    return get_user(row["user_id"]) if row else None


def user_by_token_or_query(authorization: str = None, token_query: str = None):
    """图片接口专用：浏览器 <img> 标签带不了 Header，允许 ?token=xxx 查询参数。"""
    user = user_by_token(authorization)
    if user:
        return user
    if token_query:
        row = db.query("SELECT user_id FROM sessions WHERE token=?", (token_query,), one=True)
        return get_user(row["user_id"]) if row else None
    return None


def current_user(authorization: str = Header(None)):
    """FastAPI 依赖：可选登录（接口在此基础上自行校验）。"""
    return user_by_token(authorization)


def require_user(authorization: str = Header(None)):
    """FastAPI 依赖：必须登录。"""
    user = user_by_token(authorization)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


def require_admin(authorization: str = Header(None)):
    """FastAPI 依赖：必须管理员。"""
    user = require_user(authorization)
    if user.get("role") != 1:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def list_users():
    """全部用户（管理员用，不含密码等敏感字段）。"""
    return [public(u) for u in db.query("SELECT * FROM users ORDER BY id")]


def delete_user(user_id: int):
    """删除用户及其全部数据（相册/照片/区域/会话）。管理员用。

    保护：不能删 root；不能删最后一个管理员（否则系统无管理员）。返回是否成功。
    """
    target = db.query("SELECT * FROM users WHERE id=?", (user_id,), one=True)
    if not target or target["username"] == "root":
        return False
    if target.get("role") == 1:
        admins = db.query("SELECT COUNT(*) AS c FROM users WHERE role=1", one=True)["c"]
        if admins <= 1:
            return False
    db.execute("DELETE FROM photos WHERE album_id IN (SELECT id FROM albums WHERE user_id=?)",
               (user_id,))
    db.execute("DELETE FROM albums WHERE user_id=? AND shared=0", (user_id,))
    db.execute("DELETE FROM zones WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    return True


def set_role(user_id: int, role: int):
    """设置用户角色（1=管理员，0=普通用户）。

    保护：root 不可降级；不能把最后一个管理员降为普通用户（否则系统无管理员）。
    成功返回用户 dict，被保护则返回 None。
    """
    target = db.query("SELECT * FROM users WHERE id=?", (user_id,), one=True)
    if not target:
        return None
    if target["username"] == "root":
        return None
    if target.get("role") == 1 and not role:
        admins = db.query("SELECT COUNT(*) AS c FROM users WHERE role=1", one=True)["c"]
        if admins <= 1:
            return None
    db.execute("UPDATE users SET role=? WHERE id=?", (1 if role else 0, user_id))
    return get_user(user_id)


def update_profile(user_id: int, nickname=None, bio=None, accent=None):
    """更新个人设置（只更新传入的字段）。"""
    fields, params = [], []
    for key, val in (("nickname", nickname), ("bio", bio), ("accent", accent)):
        if val is not None:
            fields.append(f"{key}=?")
            params.append(val)
    if fields:
        params.append(user_id)
        db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", params)
    return get_user(user_id)


def save_avatar(user_id: int, content: bytes) -> str:
    """头像字节入库，返回可访问 URL（带版本号防缓存）。"""
    url = f"/api/me/avatar?v={user_id}_{len(content)}"
    db.execute("UPDATE users SET avatar=?, avatar_data=? WHERE id=?",
               (url, sqlite3.Binary(content), user_id))
    return url


def avatar_data(user_id: int):
    """取头像字节。"""
    row = db.query("SELECT avatar_data FROM users WHERE id=?", (user_id,), one=True)
    return row["avatar_data"] if row else None
