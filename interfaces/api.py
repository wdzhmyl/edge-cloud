"""交互层：FastAPI 后端（前后端分离架构）。

- 本文件提供 REST API + MJPEG 视频流，供 Vue3 前端（frontend/）调用；
- 核心逻辑全部复用 pipeline/ 与 core/，本层只做 HTTP 协议适配。

启动：
    uvicorn interfaces.api:app --host 0.0.0.0 --port 8000
接口文档（自动生成）：
    http://localhost:8000/docs
"""
import base64
import os
import tempfile
from collections import Counter
from typing import Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from pipeline.collab import analyze_image
from core import album, auth, db, inspection, monitor_service as ms, zone
from core.edge_infer import check_danger_zone, infer

app = FastAPI(title="智慧工地安全巡检平台 API", version="2.0.0")

# 前端 Vite 开发服务器（localhost:5173）跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODE = "云端大模型研判（多模态）" if settings.LLM_API_KEY else "本地离线兜底（未配置 API Key）"


@app.get("/api/health")
def health():
    """健康检查：确认服务可用，并告知当前运行模式（云端/兜底）。"""
    return {"status": "ok", "mode": MODE, "model": settings.LLM_MODEL}


# 云端研判（LLM）较慢，放到后台线程执行，HTTP 接口立即返回检测结果，前端轮询拿报告。
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from core.cloud_reason import generate_report as _generate_report

_inspect_executor = ThreadPoolExecutor(max_workers=2)


def _report_job(photo_id, detections, intrusions, annotated):
    """后台任务：生成云端研判报告并落库（含标注图）。

    用墙钟超时（fut.result(timeout=...)）强制在 LLM_TIMEOUT 内结束：
    部分推理模型会用 SSE 心跳保活，导致 socket 级超时永不触发，必须用墙钟兜底，
    否则后台线程会一直挂起、巡检结果迟迟不落库。超时/异常均回退本地兜底报告。
    """
    report = None
    _ex = ThreadPoolExecutor(max_workers=1)
    try:
        fut = _ex.submit(_generate_report, detections, None, intrusions)
        report = fut.result(timeout=settings.LLM_TIMEOUT)
    except Exception as e:
        from core import fallback_report
        report = fallback_report.build_fallback_report(
            detections, intrusions=intrusions,
            note=f"\n\n（云端报告生成超时/失败，已回退本地兜底：{e}）"
        )
    finally:
        # 关键：wait=False，避免反过来等待仍在跑的慢 LLM 线程，确保报告及时落库
        _ex.shutdown(wait=False)
    counts = dict(Counter(d["label_zh"] for d in detections))
    try:
        inspection.save_inspection(photo_id, report, counts, intrusions,
                                  len(intrusions), settings.LLM_MODEL, annotated)
    except Exception:
        pass


def _detect_and_persist(in_path, zone_list, user, existing_photo_id=None):
    """快速检测（毫秒级）并落库；返回 (result, photo_id)。

    existing_photo_id 给定时（已有照片复查）不新建照片，直接复用；
    否则若已登录则把上传图片存入「AI巡检」相册。巡检报告由 _report_job 后台补全。
    """
    from pipeline.collab import analyze_detect
    out_path, detections, intrusions = analyze_detect(in_path, zones=zone_list)
    annotated = open(out_path, "rb").read() if out_path and os.path.exists(out_path) else None
    counts = dict(Counter(d["label_zh"] for d in detections))
    image_b64 = "data:image/jpeg;base64," + base64.b64encode(annotated).decode() if annotated else ""
    result = {
        "report": "",
        "summary": ms.build_summary(detections, intrusions),
        "counts": counts,
        "intrusion_count": len(intrusions),
        "intrusion_labels": [d["label_zh"] for d in intrusions],
        "image": image_b64,
        "processing": True,
        "saved": False,
        "photo_id": existing_photo_id,
    }
    photo_id = existing_photo_id
    if photo_id is None and user:
        try:
            album_id = album.get_or_create_album(user["id"], "AI巡检")["id"]
            with open(in_path, "rb") as f:
                raw = f.read()
            photo = album.add_photo_bytes(album_id, raw, note="AI巡检", source="inspect",
                                         uploader_id=user["id"])
            photo_id = photo["id"]
            result["album"] = "AI巡检"
        except Exception as e:
            result["save_error"] = str(e)
    if photo_id is not None:
        result["saved"] = True
        result["photo_id"] = photo_id
        _inspect_executor.submit(_report_job, photo_id, detections, intrusions, annotated)
    else:
        # 匿名且非已有照片：无法持久化，给出本地即时兜底报告（不调云端，避免卡死）
        try:
            from core import fallback_report
            result["report"] = fallback_report.build_fallback_report(detections, intrusions=intrusions)
        except Exception:
            result["report"] = ""
        result["processing"] = False
    return result, photo_id


@app.post("/api/inspect")
async def inspect(file: UploadFile = File(...), authorization: str = Header(None)):
    """图片巡检：上传图片 → 快速 YOLO 检测 + 危险区判定（立即返回标注图与计数），
    云端研判报告在后台生成，前端轮询 /api/photos/{id}/inspection 获取。

    已登录时自动把图片存入「AI巡检」相册，巡检结果持久化，刷新/重登后仍可见。
    """
    suffix = os.path.splitext(file.filename or "upload.jpg")[1] or ".jpg"
    in_path = tempfile.mktemp(suffix=suffix)
    with open(in_path, "wb") as f:
        f.write(await file.read())

    zone_list = None
    user = auth.user_by_token(authorization)
    if user:
        rects = zone.zone_rects(user["id"])
        if rects:
            zone_list = rects
    result, _ = _detect_and_persist(in_path, zone_list, user)
    return result


@app.post("/api/photos/{photo_id}/inspect")
def inspect_existing_photo(photo_id: int, user=Depends(auth.require_user)):
    """对相册中已有照片重新巡检：复用其原图，快速检测后立即返回，报告后台生成并落库。

    个人照片仅属主可巡检；共享照片任何登录用户可巡检（结果按最新一次覆盖）。
    """
    a = album.album_of_photo(photo_id)
    if not a:
        return JSONResponse(status_code=404, content={"detail": "照片不存在"})
    if not a["shared"] and a["user_id"] != user["id"]:
        return JSONResponse(status_code=403, content={"detail": "无权访问该照片"})
    data = album.photo_data(photo_id)
    if not data:
        return JSONResponse(status_code=404, content={"detail": "照片数据缺失"})

    in_path = tempfile.mktemp(suffix=".jpg")
    with open(in_path, "wb") as f:
        f.write(data)

    zone_list = None
    if not a["shared"]:
        rects = zone.zone_rects(user["id"])
        if rects:
            zone_list = rects
    result, _ = _detect_and_persist(in_path, zone_list, user, existing_photo_id=photo_id)
    return result


@app.get("/api/photos/{photo_id}/inspection")
def photo_inspection(photo_id: int, authorization: str = Header(None), token: str = None):
    """获取某照片的巡检结果（悬浮展示用）。无结果返回 404；含标注图 base64。"""
    user = auth.user_by_token_or_query(authorization, token)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "请先登录"})
    a = album.album_of_photo(photo_id)
    if not a:
        return JSONResponse(status_code=404, content={"detail": "照片不存在"})
    if not a["shared"] and a["user_id"] != user["id"]:
        return JSONResponse(status_code=403, content={"detail": "无权访问该照片"})
    rec = inspection.get_inspection(photo_id)
    if not rec:
        return JSONResponse(status_code=404, content={"detail": "该照片尚未巡检"})
    img = inspection.get_inspection_image(photo_id)
    rec["image"] = ("data:image/jpeg;base64," + base64.b64encode(img).decode()) if img else ""
    return rec


# ===== 实时监控 =====

@app.get("/api/cameras")
def cameras():
    """搜索摄像头：本地设备 + 已添加的网络源，返回下拉选项与默认值。"""
    choices, value = ms.discover()
    if not choices:
        return {"choices": [], "value": None, "message": "未找到可用摄像头"}
    return {"choices": choices, "value": value, "message": f"发现 {len(choices)} 个摄像头"}


class NetCamIn(BaseModel):
    url: str


@app.post("/api/cameras/net")
def add_net_cam(body: NetCamIn):
    """添加网络/手机摄像头（RTSP 或 http 视频流）。"""
    choices, value, message = ms.add_network(body.url)
    return {"choices": choices or [], "value": value, "message": message}


class StartIn(BaseModel):
    source: str


@app.post("/api/monitor/start")
def monitor_start(body: StartIn):
    """开启监控（source 形如 local:0 或 net:http://...）。"""
    return {"message": ms.start(body.source), "monitoring": True}


@app.post("/api/monitor/stop")
def monitor_stop():
    """停止监控。"""
    return {"message": ms.stop(), "monitoring": False}


@app.get("/api/monitor/stream")
def monitor_stream():
    """MJPEG 实时视频流（前端 <img src> 直接播放）。"""
    return StreamingResponse(
        ms.stream_gen(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/monitor/state")
def monitor_state():
    """轮询实时状态：告警文本、检测计数、闯入数、截图数。"""
    return ms.get_state()


@app.post("/api/monitor/screenshot")
def monitor_screenshot(user=Depends(auth.require_user)):
    """主动截屏存证（标注检测框 + 危险区）；已登录时同步收入相册。"""
    message, items, path = ms.manual_shot()
    jpg = ms.latest_frame_jpg()
    if jpg is None and path and os.path.isfile(path):
        with open(path, "rb") as f:
            jpg = f.read()
    if jpg is not None:
        album.add_photo_bytes(
            album.default_album(user["id"])["id"], jpg,
            note="巡检截图", source="shot", uploader_id=user["id"])
        message += "（已收入相册 · 巡检截图）"
    return {"message": message, "gallery": items}


# ===== 认证与个人中心 =====

class RegisterIn(BaseModel):
    username: str
    password: str
    nickname: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class ProfileIn(BaseModel):
    nickname: str = None
    bio: str = None
    accent: str = None


class ZoneIn(BaseModel):
    zone: list                    # [x1,y1,x2,y2] 归一化
    name: str = "危险作业区"


@app.get("/api/me/zones")
def get_my_zones(user=Depends(auth.require_user)):
    """当前用户的全部危险作业区（支持多个）。"""
    return {"items": zone.list_zones(user["id"])}


@app.post("/api/me/zones")
def add_my_zone(body: ZoneIn, user=Depends(auth.require_user)):
    """新增一个危险作业区（手动划定，保留已有区域）。"""
    z = body.zone
    if len(z) != 4 or z[2] <= z[0] or z[3] <= z[1]:
        return JSONResponse(status_code=400, content={"detail": "区域坐标不合法"})
    return zone.add_zone(user["id"], z, body.name)


@app.delete("/api/me/zones/{zone_id}")
def delete_my_zone(zone_id: int, user=Depends(auth.require_user)):
    """删除单个危险作业区。"""
    if not zone.delete_zone(zone_id, user["id"]):
        return JSONResponse(status_code=404, content={"detail": "区域不存在"})
    return {"ok": True}


@app.delete("/api/me/zones")
def clear_my_zones(user=Depends(auth.require_user)):
    """清空全部危险作业区。"""
    zone.clear_zones(user["id"])
    return {"ok": True}


@app.post("/api/auth/register")
def register(body: RegisterIn):
    """注册（用户名 + 密码），成功直接返回 token。"""
    user = auth.register(body.username, body.password, body.nickname)
    if not user:
        return JSONResponse(status_code=400, content={"detail": "用户名已存在或不能为空"})
    token, _ = auth.login(body.username, body.password)
    return {"token": token, "user": user}


@app.post("/api/auth/login")
def api_login(body: LoginIn):
    """登录，返回 token 与用户信息。"""
    token, user = auth.login(body.username, body.password)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})
    return {"token": token, "user": user}


@app.post("/api/auth/logout")
def api_logout(authorization: str = Header(None)):
    """退出登录（使当前 token 失效）。"""
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    auth.logout(token)
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(auth.require_user)):
    """当前登录用户信息。"""
    return user


@app.put("/api/me")
def update_me(body: ProfileIn, user=Depends(auth.require_user)):
    """修改个人设置（昵称 / 个性签名 / 主题色）。"""
    return auth.update_profile(user["id"], nickname=body.nickname, bio=body.bio, accent=body.accent)


@app.post("/api/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user=Depends(auth.require_user)):
    """上传头像（字节入库）。"""
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        return JSONResponse(status_code=400, content={"detail": "头像不能超过 5MB"})
    url = auth.save_avatar(user["id"], content)
    return {"avatar": url}


@app.get("/api/me/avatar")
def avatar_file(token: str = None, authorization: str = Header(None)):
    """读取当前用户头像（数据库 BLOB）。支持 ?token=（浏览器 img 标签用）。"""
    user = auth.user_by_token_or_query(authorization, token)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "请先登录"})
    data = auth.avatar_data(user["id"])
    if not data:
        return JSONResponse(status_code=404, content={"detail": "头像不存在"})
    return Response(content=bytes(data), media_type="image/jpeg")


# ===== 相册（支持多级嵌套文件夹）=====

class AlbumIn(BaseModel):
    name: str
    parent_id: int = 0


class PhotoIn(BaseModel):
    note: str = ""


@app.get("/api/albums")
def albums(parent_id: int = 0, user=Depends(auth.require_user)):
    """我的个人文件夹：返回 parent_id 下的子文件夹列表（多级嵌套）。"""
    return {"items": album.list_children(user["id"], parent_id, shared=False)}


@app.get("/api/albums/tree")
def albums_tree(user=Depends(auth.require_user)):
    """我的全部个人文件夹（扁平带路径，用于移动目标选择）。"""
    return {"items": album.list_albums_flat(user["id"])}


@app.get("/api/albums/move-targets")
def move_targets(user=Depends(auth.require_user)):
    """移动目标：个人文件夹树 + 共享文件夹树（含子目录），供多选移动到共享。"""
    return {"items": album.move_targets(user["id"])}


@app.post("/api/albums")
def create_album_api(body: AlbumIn, user=Depends(auth.require_user)):
    """新建个人文件夹（可指定父目录，实现多级嵌套）。"""
    return album.create_album(user["id"], body.name, parent_id=body.parent_id)


@app.delete("/api/albums/{album_id}")
def delete_album_api(album_id: int, user=Depends(auth.require_user)):
    """递归删除文件夹（含子文件夹与所有照片）。共享文件夹仅管理员可删。"""
    ok = album.delete_album_recursive(album_id, user)
    if not ok:
        return JSONResponse(status_code=403, content={"detail": "无权删除或文件夹不存在"})
    return {"ok": True}


@app.get("/api/albums/{album_id}/photos")
def album_photos(album_id: int, user=Depends(auth.require_user)):
    """个人文件夹内的照片列表（仅本人）。"""
    a = album.get_album(album_id)
    if not a or a["shared"] or a["user_id"] != user["id"]:
        return JSONResponse(status_code=404, content={"detail": "文件夹不存在"})
    return {"items": album.list_photos(album_id, user)}


@app.post("/api/albums/{album_id}/photos")
async def upload_photo(album_id: int, file: UploadFile = File(...),
                       note: str = Form(""), user=Depends(auth.require_user)):
    """上传照片到个人文件夹（含子文件夹）。"""
    a = album.get_album(album_id)
    if not a or a["shared"] or a["user_id"] != user["id"]:
        return JSONResponse(status_code=404, content={"detail": "文件夹不存在"})
    return album.add_photo_bytes(album_id, await file.read(), note,
                                 uploader_id=user["id"])


# ===== 共享文件夹（所有账号可上传；支持多级嵌套；仅上传者/管理员删内容）=====

class SharedFolderIn(BaseModel):
    name: str
    parent_id: int = 0


@app.get("/api/shared")
def shared_folder(parent_id: int = 0, user=Depends(auth.require_user)):
    """共享目录内容：parent_id 下的子文件夹 + 照片（含 can_delete 标记）。"""
    info = album.shared_info(user, parent_id)
    if not info:
        return JSONResponse(status_code=404, content={"detail": "共享文件夹不存在"})
    return info


@app.post("/api/shared/folders")
def create_shared_folder_api(body: SharedFolderIn, user=Depends(auth.require_user)):
    """在共享目录下新建子文件夹（任何登录账号均可）。"""
    created = album.create_shared_folder(body.name, parent_id=body.parent_id,
                                         creator_id=user["id"])
    if not created:
        return JSONResponse(status_code=400, content={"detail": "父目录不是共享文件夹"})
    return created


@app.post("/api/shared/photos")
async def upload_shared_photo(album_id: int = 0, file: UploadFile = File(...),
                              note: str = Form(""), user=Depends(auth.require_user)):
    """上传照片到共享文件夹（默认共享根，可指定共享子文件夹）。任何登录账号均可。"""
    aid = album_id or album.shared_root()["id"]
    target = album.get_album(aid)
    if not target or not target["shared"]:
        return JSONResponse(status_code=400, content={"detail": "目标不是共享文件夹"})
    return album.add_photo_bytes(aid, await file.read(), note, uploader_id=user["id"])


@app.delete("/api/photos/{photo_id}")
def delete_photo_api(photo_id: int, user=Depends(auth.require_user)):
    """删除单张照片（共享文件夹内仅上传者/管理员）。"""
    ok = album.delete_photo(photo_id, user)
    if not ok:
        return JSONResponse(status_code=403, content={"detail": "无权删除或照片不存在"})
    return {"ok": True}


@app.get("/api/photos/{photo_id}/file")
def photo_file(photo_id: int, token: str = None, authorization: str = Header(None)):
    """读取照片（数据库 BLOB）。支持 ?token=（浏览器 img 标签用）。

    共享文件夹照片任何登录用户可读；个人照片仅本人。
    """
    user = auth.user_by_token_or_query(authorization, token)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "请先登录"})
    p = album._row(photo_id)
    if not p:
        return JSONResponse(status_code=404, content={"detail": "照片不存在"})
    owner = db.query("SELECT shared, user_id FROM albums WHERE id=?", (p["album_id"],), one=True)
    if not owner:
        return JSONResponse(status_code=404, content={"detail": "照片不存在"})
    if not owner["shared"] and owner["user_id"] != user["id"]:
        return JSONResponse(status_code=403, content={"detail": "无权查看"})
    data = album.photo_data(photo_id)
    if not data:
        return JSONResponse(status_code=404, content={"detail": "照片数据缺失"})
    return Response(content=bytes(data), media_type="image/jpeg")


class MoveIn(BaseModel):
    album_id: int


class BatchMoveIn(BaseModel):
    ids: list
    album_id: int


class BatchDeleteIn(BaseModel):
    ids: list


@app.put("/api/photos/{photo_id}/move")
def move_photo_api(photo_id: int, body: MoveIn, user=Depends(auth.require_user)):
    """把照片移动到其他文件夹（共享夹移出需上传者/管理员权限）。"""
    ok = album.move_photo(photo_id, body.album_id, user)
    if not ok:
        return JSONResponse(status_code=403, content={"detail": "无权移动或目标不存在"})
    return {"ok": True}


@app.post("/api/photos/batch-move")
def batch_move_api(body: BatchMoveIn, user=Depends(auth.require_user)):
    """批量移动照片到目标文件夹。"""
    moved = album.batch_move(body.ids, body.album_id, user)
    return {"moved": moved}


@app.post("/api/photos/batch-delete")
def batch_delete_api(body: BatchDeleteIn, user=Depends(auth.require_user)):
    """批量删除照片。"""
    deleted = album.batch_delete(body.ids, user)
    return {"deleted": deleted}


# ===== 管理员：用户账号管理 =====

@app.get("/api/admin/users")
def admin_users(admin=Depends(auth.require_admin)):
    """全部用户列表（仅管理员）。"""
    return {"items": auth.list_users()}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin=Depends(auth.require_admin)):
    """删除用户及其全部数据（仅管理员，不能删自己 / root / 最后一个管理员）。"""
    if user_id == admin["id"]:
        return JSONResponse(status_code=400, content={"detail": "不能删除当前登录的管理员账号"})
    ok = auth.delete_user(user_id)
    if not ok:
        return JSONResponse(status_code=400, content={"detail": "不能删除 root 或最后一个管理员"})
    return {"ok": True}


class RoleIn(BaseModel):
    role: int


@app.put("/api/admin/users/{user_id}/role")
def admin_set_role(user_id: int, body: RoleIn, admin=Depends(auth.require_admin)):
    """设置用户角色（1=管理员 / 0=普通用户，仅管理员）。"""
    if user_id == admin["id"]:
        return JSONResponse(status_code=400, content={"detail": "不能修改自己的角色"})
    new_user = auth.set_role(user_id, body.role)
    if not new_user:
        return JSONResponse(status_code=400, content={"detail": "不能降级 root 或最后一个管理员"})
    return new_user


@app.get("/api/monitor/report")
def monitor_report():
    """对当前监控帧生成云端研判报告。"""
    return {"report": ms.make_report()}


class FrameIn(BaseModel):
    image: str  # base64(JPEG)，可带 data: 前缀


@app.post("/api/monitor/frame")
def monitor_frame(body: FrameIn, authorization: str = Header(None)):
    """浏览器摄像头模式：接收前端 base64 帧 → YOLO + 危险区判定 → 返回归一化检测框。

    画框由前端覆盖层 canvas 完成（不回传整图，带宽最省），与旧版 Gradio 实现同构。
    已登录用户使用其手动划定的危险作业区。
    """
    try:
        raw = base64.b64decode(body.image.split(",", 1)[-1])
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "帧数据解码失败"})
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return JSONResponse(status_code=400, content={"detail": "帧解码失败"})

    # 用户手动划定的危险区（可多个）优先
    zone_rects = None
    user = auth.user_by_token(authorization)
    if user:
        rects = zone.zone_rects(user["id"])
        if rects:
            zone_rects = rects

    detections, _ = infer(frame)
    h, w = frame.shape[:2]
    intrusions, zone_px_list = check_danger_zone(detections, (w, h), zones=zone_rects)
    ms.ingest_browser_frame(frame, detections, intrusions)

    dets = [{
        "label_zh": d["label_zh"], "conf": d["conf"],
        "box": [d["box"][0] / w, d["box"][1] / h, d["box"][2] / w, d["box"][3] / h],
        "in_zone": bool(d.get("in_zone", False)),
    } for d in detections]
    zones_out = [[zx1 / w, zy1 / h, zx2 / w, zy2 / h] for (zx1, zy1, zx2, zy2) in zone_px_list]
    return {
        "detections": dets,
        "zones": zones_out,
        "zone_label": settings.DANGER_ZONE_LABEL,
        "intrusion_count": len(intrusions),
        "counts": dict(Counter(d["label_zh"] for d in detections)),
    }


@app.post("/api/monitor/shot")
async def monitor_shot(file: UploadFile = File(...), user=Depends(auth.require_user)):
    """浏览器摄像头截屏（手动/自动）：前端合成标注图 → 直接入库相册。"""
    content = await file.read()
    intrusion = ms.get_state()["intrusion_count"] > 0
    note = "自动·危险区闯入" if intrusion else "巡检截图"
    album.add_photo_bytes(
        album.default_album(user["id"])["id"], content, note=note,
        source="shot", uploader_id=user["id"])
    return {"message": "已截屏并收入相册 · 巡检截图"}


@app.post("/api/monitor/screenshot")
def monitor_screenshot(user=Depends(auth.require_user)):
    """网络摄像头模式主动截屏：取服务端最新标注帧 → 入库相册。"""
    message, _items, path = ms.manual_shot()
    jpg = ms.latest_frame_jpg()
    if jpg is None and path and os.path.isfile(path):
        with open(path, "rb") as f:
            jpg = f.read()
    if jpg is None:
        return JSONResponse(status_code=400, content={"detail": "当前没有可用的监控帧"})
    intrusion = ms.get_state()["intrusion_count"] > 0
    album.add_photo_bytes(
        album.default_album(user["id"])["id"], jpg,
        note="危险区闯入" if intrusion else "巡检截图",
        source="shot", uploader_id=user["id"])
    return {"message": "已主动截屏并收入相册 · 巡检截图"}


@app.get("/api/monitor/gallery")
def monitor_gallery(user=Depends(auth.require_user)):
    """监控页画廊：全部监控截图（来自相册，数据库，仅元数据不返回 BLOB）。

    返回所有截图以便前端统计总数；监控预览区只展示其中最新 4 张，绝不自动删除。
    """
    return {"items": album.recent_shots(user["id"], limit=2000)}


# ===== 前端构建产物托管（可选）=====
# `cd frontend && npm run build` 生成 dist 后，FastAPI 可直接伺服整个前端，
# 生产环境只需运行 uvicorn 一个进程。未构建时这些路由不存在，不影响 /api。
_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """SPA  history 模式回退：非 API 路径一律返回 index.html。"""
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        index = os.path.join(_DIST, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "前端未构建"})
