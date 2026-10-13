"""相册：个人文件夹（支持多级嵌套）+ 共享文件夹（也支持嵌套）+ 照片管理。

图片全部以 BLOB 存在 SQLite（data/app.db），不落文件系统。
- 个人文件夹：归属 user_id，仅本人可见可管；可任意层级嵌套（parent_id）。
- 共享文件夹：shared=1，所有账号可上传到任意层级；只有上传者本人和管理员(role=1)
  可删除/移出其中的照片；共享文件夹的删除仅管理员。
- source 标记来源：upload=手动上传，shot=监控截图。
"""
import sqlite3

from core import db

DEFAULT_ALBUM_NAME = "巡检截图"
SHARED_ALBUM_NAME = "共享文件夹"


def _row(photo_id):
    return db.query(
        "SELECT id, album_id, uploader_id, note, source, size, created_at FROM photos WHERE id=?",
        (photo_id,), one=True)


def is_admin(user: dict) -> bool:
    return bool(user and user.get("role") == 1)


def can_manage_photo(photo: dict, user: dict) -> bool:
    """共享文件夹里的照片：上传者本人或管理员可删除/移出。"""
    if not photo or not user:
        return False
    return photo["uploader_id"] == user["id"] or is_admin(user)


def _album_info(a):
    a["count"] = db.query("SELECT COUNT(*) AS c FROM photos WHERE album_id=?",
                          (a["id"],), one=True)["c"]
    a["sub_count"] = db.query("SELECT COUNT(*) AS c FROM albums WHERE parent_id=?",
                              (a["id"],), one=True)["c"]
    first = db.query("SELECT id FROM photos WHERE album_id=? ORDER BY id DESC LIMIT 1",
                     (a["id"],), one=True)
    a["cover_id"] = first["id"] if first else None
    return a


# ============ 文件夹树 ============

def list_children(user_id: int, parent_id: int = 0, shared: bool = False):
    """列出某父目录下的子文件夹（不含照片）。"""
    if shared:
        rows = db.query(
            "SELECT * FROM albums WHERE shared=1 AND parent_id=? ORDER BY id DESC", (parent_id,))
    else:
        rows = db.query(
            "SELECT * FROM albums WHERE user_id=? AND shared=0 AND parent_id=? ORDER BY id DESC",
            (user_id, parent_id))
    return [_album_info(a) for a in rows]


def create_album(user_id: int, name: str, parent_id: int = 0, shared: bool = False):
    """新建文件夹（可指定父目录，实现多级嵌套）。"""
    name = (name or "").strip() or "未命名文件夹"
    aid = db.execute(
        "INSERT INTO albums (user_id, name, shared, parent_id, created_at) VALUES (?,?,?,?,?)",
        (user_id, name, 1 if shared else 0, parent_id, db.now()))
    return db.query("SELECT * FROM albums WHERE id=?", (aid,), one=True)


def get_album(album_id: int):
    return db.query("SELECT * FROM albums WHERE id=?", (album_id,), one=True)


def can_manage_album(album: dict, user: dict) -> bool:
    """删除文件夹的权限：共享文件夹仅管理员；个人文件夹仅属主。"""
    if not album:
        return False
    if album["shared"]:
        return is_admin(user)
    return album["user_id"] == user["id"]


def delete_album_recursive(album_id: int, user: dict):
    """递归删除文件夹（含所有子文件夹与照片）。"""
    album = get_album(album_id)
    if not can_manage_album(album, user):
        return False
    for child in db.query("SELECT id FROM albums WHERE parent_id=?", (album_id,)):
        delete_album_recursive(child["id"], user)
    db.execute("DELETE FROM photos WHERE album_id=?", (album_id,))
    db.execute("DELETE FROM albums WHERE id=?", (album_id,))
    return True


def album_path(album_id: int):
    """返回从根到该文件夹的路径（面包屑）。"""
    path = []
    cur = get_album(album_id)
    while cur:
        path.insert(0, {"id": cur["id"], "name": cur["name"], "shared": bool(cur["shared"])})
        if not cur["parent_id"]:
            break
        cur = get_album(cur["parent_id"])
    return path


def list_albums_flat(user_id: int):
    """扁平列出用户全部个人文件夹（用于移动目标），带路径标签。"""
    out = []
    def walk(parent_id, prefix):
        for a in db.query(
            "SELECT * FROM albums WHERE user_id=? AND shared=0 AND parent_id=? ORDER BY id",
            (user_id, parent_id)):
            label = f"{prefix}/{a['name']}" if prefix else a["name"]
            out.append({"id": a["id"], "name": a["name"], "label": label})
            walk(a["id"], label)
    walk(0, "")
    return out


def move_targets(user_id: int):
    """移动目标：个人全部文件夹（带路径）+ 共享根及全部子目录（带'共享/'前缀）。

    这样任何个人照片都可通过多选移动到共享文件夹（含子目录），移入后
    uploader_id 记为操作者，仅其本人与管理员可删。
    """
    personal = list_albums_flat(user_id)
    root = shared_root()
    shared = [{"id": root["id"], "label": f"共享/{root['name']}", "shared": True}]
    def walk(parent_id, prefix):
        for a in db.query(
            "SELECT * FROM albums WHERE shared=1 AND parent_id=? ORDER BY id", (parent_id,)):
            label = f"{prefix}/{a['name']}"
            shared.append({"id": a["id"], "label": label, "shared": True})
            walk(a["id"], label)
    walk(root["id"], f"共享/{root['name']}")
    return personal + shared


# ============ 共享文件夹 ============

def shared_root():
    """全局唯一共享根文件夹（不存在则创建，user_id=0 表示系统级）。"""
    album = db.query("SELECT * FROM albums WHERE shared=1 AND parent_id=0 ORDER BY id LIMIT 1",
                     one=True)
    if album:
        return album
    aid = db.execute(
        "INSERT INTO albums (user_id, name, shared, parent_id, created_at) VALUES (0,?,1,0,?)",
        (SHARED_ALBUM_NAME, db.now()))
    return db.query("SELECT * FROM albums WHERE id=?", (aid,), one=True)


def create_shared_folder(name: str, parent_id: int = 0, creator_id: int = 0):
    """在共享目录下新建子文件夹（任何登录用户均可）。"""
    if parent_id:
        parent = get_album(parent_id)
        if not parent or not parent["shared"]:
            return None
    else:
        parent_id = shared_root()["id"]
    return create_album(creator_id, name, parent_id=parent_id, shared=True)


def shared_info(user: dict, parent_id: int = 0):
    """共享目录（parent_id 下）的子文件夹 + 照片（带 can_delete 等）。

    parent_id=0 表示共享根视图：用共享根的真实 id 作为父级来查子目录与照片。
    """
    root = shared_root()
    if parent_id:
        a = get_album(parent_id)
        if not a or not a["shared"]:
            return None
        actual = parent_id
    else:
        actual = root["id"]
    children = list_children(user["id"], actual, shared=True)
    photos = list_photos(actual, user)
    return {"album": get_album(actual), "children": children, "photos": photos}


def is_shared_album(album_id: int) -> bool:
    a = get_album(album_id)
    return bool(a and a["shared"])


# ============ 照片 ============

def get_or_create_album(user_id: int, name: str, parent_id: int = 0, shared: bool = False):
    """按 (user_id, name, shared, parent_id) 取已有相册，没有则创建。"""
    a = db.query(
        "SELECT * FROM albums WHERE user_id=? AND name=? AND shared=? AND parent_id=? "
        "ORDER BY id LIMIT 1",
        (user_id, name, 1 if shared else 0, parent_id), one=True)
    return a or create_album(user_id, name, parent_id=parent_id, shared=shared)


def album_of_photo(photo_id: int):
    """返回某照片所属相册记录（用于权限判定）。"""
    return db.query(
        "SELECT a.* FROM albums a JOIN photos p ON p.album_id=a.id WHERE p.id=?",
        (photo_id,), one=True)


def list_photos(album_id: int, user: dict = None):
    """文件夹内照片（不含 BLOB 本体）。user 传入时附带 can_delete、上传者昵称、
    inspected（是否已巡检）、intrusion_count（危险区闯入数，悬浮展示用）。"""
    rows = db.query(
        "SELECT p.id, p.album_id, p.uploader_id, p.note, p.source, p.size, p.created_at, "
        "u.nickname AS uploader_name, "
        "(i.id IS NOT NULL) AS inspected, "
        "COALESCE(i.intrusion_count, 0) AS intrusion_count "
        "FROM photos p LEFT JOIN users u ON p.uploader_id = u.id "
        "LEFT JOIN inspections i ON i.photo_id = p.id "
        "WHERE p.album_id=? ORDER BY p.id DESC", (album_id,))
    album = get_album(album_id)
    is_shared = bool(album and album["shared"])
    for r in rows:
        r["can_delete"] = (not is_shared) or can_manage_photo(r, user) if user else (not is_shared)
        r["uploader_name"] = r["uploader_name"] or "未知用户"
        r["inspected"] = bool(r["inspected"])
        r["intrusion_count"] = int(r["intrusion_count"])
    return rows


def add_photo_bytes(album_id: int, content: bytes, note: str = "",
                    source: str = "upload", uploader_id: int = 0):
    """图片字节直接入库（记录上传者，共享文件夹据此判定删除权限）。"""
    pid = db.execute(
        "INSERT INTO photos (album_id, uploader_id, note, source, size, created_at, data) "
        "VALUES (?,?,?,?,?,?,?)",
        (album_id, uploader_id, note, source, len(content), db.now(),
         sqlite3.Binary(content)))
    return _row(pid)


def photo_data(photo_id: int):
    row = db.query("SELECT data FROM photos WHERE id=?", (photo_id,), one=True)
    return row["data"] if row else None


def _photo_album(photo_id: int):
    return db.query(
        "SELECT a.shared AS shared, a.user_id AS owner, a.parent_id AS parent "
        "FROM photos p JOIN albums a ON p.album_id = a.id WHERE p.id=?", (photo_id,), one=True)


def move_photo(photo_id: int, target_album_id: int, user: dict):
    """移动照片到目标文件夹。

    个人→个人：目标须属主；共享→个人：仅上传者/管理员可移出；
    个人→共享 / 共享内移动：允许，移入共享时上传者变为操作者。
    """
    p = _row(photo_id)
    if not p:
        return False
    src = _photo_album(photo_id)
    if src and src["shared"] and not can_manage_photo(p, user):
        return False
    target = get_album(target_album_id)
    if not target:
        return False
    if target["shared"]:
        db.execute("UPDATE photos SET album_id=?, uploader_id=? WHERE id=?",
                   (target_album_id, user["id"], photo_id))
        return True
    if target["user_id"] != user["id"]:
        return False
    db.execute("UPDATE photos SET album_id=? WHERE id=?", (target_album_id, photo_id))
    return True


def delete_photo(photo_id: int, user: dict):
    """删照片。个人文件夹校验归属；共享文件夹仅上传者或管理员。"""
    p = _row(photo_id)
    if not p:
        return False
    src = _photo_album(photo_id)
    if src and src["shared"]:
        if not can_manage_photo(p, user):
            return False
    elif not src or src["owner"] != user["id"]:
        return False
    db.execute("DELETE FROM photos WHERE id=?", (photo_id,))
    return True


def batch_move(photo_ids, target_album_id: int, user: dict):
    moved = 0
    for pid in photo_ids:
        if move_photo(pid, target_album_id, user):
            moved += 1
    return moved


def batch_delete(photo_ids, user: dict):
    deleted = 0
    for pid in photo_ids:
        if delete_photo(pid, user):
            deleted += 1
    return deleted


def default_album(user_id: int) -> dict:
    """用户的默认相册（根级，监控截图入库用它）。"""
    album = db.query(
        "SELECT * FROM albums WHERE user_id=? AND name=? AND shared=0 AND parent_id=0 "
        "ORDER BY id LIMIT 1", (user_id, DEFAULT_ALBUM_NAME), one=True)
    return album or create_album(user_id, DEFAULT_ALBUM_NAME, parent_id=0)


def recent_shots(user_id: int, limit: int = 50):
    """最近 N 张监控截图（跨该用户所有文件夹，供监控页画廊预览，只展示不删除）。"""
    return db.query(
        "SELECT p.id, p.album_id, p.note, p.source, p.size, p.created_at "
        "FROM photos p JOIN albums a ON p.album_id = a.id "
        "WHERE a.user_id=? AND p.source='shot' ORDER BY p.id DESC LIMIT ?",
        (user_id, limit))
