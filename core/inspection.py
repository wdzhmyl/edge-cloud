"""巡检结果持久化：把一次图片巡检的报告/统计/标注图与照片绑定存储。

- 一张照片只保留最新一次巡检结果（upsert）。
- 标注图（带检测框/危险区）以 BLOB 存储，悬浮查看时按需返回。
- 列表查询只需"是否已巡检"，详情（含标注图）按 id 懒加载。
"""
import json
import sqlite3

from core import db


def save_inspection(photo_id: int, report: str, counts: dict, intrusions: list,
                   intrusion_count: int, model: str, annotated: bytes = None):
    """保存/覆盖一张照片的巡检结果（photo_id 唯一）。"""
    existing = db.query("SELECT id FROM inspections WHERE photo_id=?", (photo_id,), one=True)
    blob = sqlite3.Binary(annotated) if annotated else None
    counts_json = json.dumps(counts or {}, ensure_ascii=False)
    intrusions_json = json.dumps(intrusions or [], ensure_ascii=False)
    if existing:
        db.execute(
            "UPDATE inspections SET report=?, counts=?, intrusions=?, intrusion_count=?, "
            "model=?, annotated=?, created_at=? WHERE photo_id=?",
            (report, counts_json, intrusions_json, intrusion_count, model, blob,
             db.now(), photo_id))
    else:
        db.execute(
            "INSERT INTO inspections (photo_id, report, counts, intrusions, intrusion_count, "
            "model, annotated, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (photo_id, report, counts_json, intrusions_json, intrusion_count, model, blob, db.now()))
    return True


def get_inspection(photo_id: int):
    """返回照片的巡检结果（counts/intrusions 反序列化为对象）。无则返回 None。"""
    row = db.query(
        "SELECT report, counts, intrusions, intrusion_count, model, created_at "
        "FROM inspections WHERE photo_id=?", (photo_id,), one=True)
    if not row:
        return None
    row["counts"] = json.loads(row["counts"]) if row["counts"] else {}
    row["intrusions"] = json.loads(row["intrusions"]) if row["intrusions"] else []
    return row


def get_inspection_image(photo_id: int):
    """返回标注图字节（无则 None）。"""
    row = db.query("SELECT annotated FROM inspections WHERE photo_id=?", (photo_id,), one=True)
    return row["annotated"] if row else None


def has_inspection(photo_id: int) -> bool:
    return bool(db.query("SELECT 1 FROM inspections WHERE photo_id=?", (photo_id,), one=True))
