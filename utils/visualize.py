"""工具层：在图像上绘制推理框、危险作业区与中文标签（可视化推理结果）。"""
from PIL import Image, ImageDraw

from config import settings


def _zone_px_list(image_size, zones=None):
    """把归一化危险区列表换算成像素坐标列表；未配置返回 []。"""
    w, h = image_size
    rects = list(zones) if zones else None
    if not rects:
        if not settings.ENABLE_DANGER_ZONE:
            return []
        rects = [settings.DANGER_ZONE]
    return [(int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)) for (x1, y1, x2, y2) in rects]


def draw_detections(image_path, detections, out_path, zones=None):
    """在图片上绘制推理框、危险作业区（支持多个）与标签，输出到 out_path。

    - 危险作业区以橙色虚线框标出；
    - 闯入危险区的目标以红色框 + "⚠闯入" 标记，其余目标以绿色框标出。

    Args:
        image_path: 原图路径。
        detections: 推理结果列表（需含 "box" 与 "label_zh"、"conf"，可选 "in_zone"）。
        out_path: 标注图输出路径。
        zones: 归一化危险区列表 [(x1,y1,x2,y2), ...]，传入则优先于 settings 配置。
    Returns:
        out_path
    """
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    for zone in _zone_px_list((w, h), zones):
        draw.rectangle(zone, outline="#f59e0b", width=3)
        draw.text((zone[0], max(0, zone[1] - 14)), settings.DANGER_ZONE_LABEL, fill="#f59e0b")

    for d in detections:
        x1, y1, x2, y2 = d["box"]
        if d.get("in_zone"):
            color, tag = "red", "⚠闯入 "
        else:
            color, tag = "#16a34a", ""
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = f"{tag}{d['label_zh']} {d['conf']:.2f}"
        draw.text((x1, max(0, y1 - 12)), label, fill=color)
    img.save(out_path)
    return out_path
