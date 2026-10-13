"""危险作业区管理：支持每个用户划定多个区域（增 / 单独删 / 清空）。

坐标为归一化 [x1, y1, x2, y2]（相对画面宽高，0~1）。
"""
from core import db


def list_zones(user_id: int):
    """用户的全部危险区（按创建时间）。"""
    return db.query(
        "SELECT id, name, x1, y1, x2, y2, created_at FROM zones WHERE user_id=? ORDER BY id",
        (user_id,))


def add_zone(user_id: int, zone, name: str = ""):
    """新增一个危险区；返回新记录。"""
    x1, y1, x2, y2 = zone
    zid = db.execute(
        "INSERT INTO zones (user_id, name, x1, y1, x2, y2, created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, name or f"危险作业区", x1, y1, x2, y2, db.now()))
    return db.query("SELECT * FROM zones WHERE id=?", (zid,), one=True)


def delete_zone(zone_id: int, user_id: int):
    """删除单个危险区（校验归属）。"""
    row = db.query("SELECT id FROM zones WHERE id=? AND user_id=?", (zone_id, user_id), one=True)
    if not row:
        return False
    db.execute("DELETE FROM zones WHERE id=?", (zone_id,))
    return True


def clear_zones(user_id: int):
    """清空该用户全部危险区。"""
    db.execute("DELETE FROM zones WHERE user_id=?", (user_id,))


def zone_rects(user_id: int):
    """取该用户全部区域的归一化矩形列表（检测/绘制用）。"""
    return [(z["x1"], z["y1"], z["x2"], z["y2"]) for z in list_zones(user_id)]
