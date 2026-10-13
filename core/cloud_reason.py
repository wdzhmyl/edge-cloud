"""云端理解层：调用云端多模态大模型生成《施工安全巡检报告》，体现云侧深度语义理解。

无 API Key 或调用失败时，回退到本地模板报告（core.fallback_report），保证服务始终可运行。
"""
import base64
import re

from openai import OpenAI

from config import settings
from core import fallback_report


def _strip_think(text):
    """去除推理模型（如 deepseek-r1）返回的 <think>...</think> 思考过程，保持报告清爽。"""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

SYSTEM_PROMPT = """你是一名智慧工地安全巡检 AI 助手。基于边缘端目标检测结果（类别、数量、是否闯入危险作业区），
输出一份简洁的《施工安全巡检报告》。要求：纯文本、不要使用任何 Markdown 符号（不要出现 # * 等标记），
用中文数字序号分段，语言专业、可读、中文：

一、图中人物及数量
列出图中检测到的主要目标（如作业人员、工程车辆等）及各自数量。

二、安全危险情况
说明是否存在人员闯入危险作业区、车辆违规停靠、防护不到位等安全隐患，并给出风险等级（低/中/高）。

三、总结
用一句话精简总结当前工地安全状态与需重点关注的事项。

要求：内容简洁，整份报告总字数控制在 200 字以内；不要输出多余解释、示例或符号。"""


def _encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _strip_markdown(text):
    """清洗可能残留的 Markdown 标记（#、*、_、~~、代码块、链接），保证输出为干净纯文本文档。"""
    if not text:
        return text
    text = re.sub(r"```+", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"_{1,3}", "", text)
    text = re.sub(r"~~", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return text.strip()


def _truncate(text, max_chars):
    """清洗 Markdown 后按字数截断，避免输出过长且保证收尾完整。"""
    text = _strip_markdown(text)
    if not text or len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if "\n" in cut:
        cut = cut[: cut.rfind("\n")]
    return cut.rstrip() + "\n…（已按字数上限截断）"


def generate_report(detections, image_path, intrusions=None):
    """生成施工安全巡检报告。

    优先调用云端多模态大模型；无 Key 或调用异常/超时自动降级为本地兜底报告，保证不卡死。

    Args:
        detections: 推理结果列表。
        image_path: 原图路径（用于多模态输入）。
        intrusions: 危险作业区闯入目标列表（可选）。
    Returns:
        Markdown 报告文本（已规范格式并限制字数）。
    """
    if not settings.LLM_API_KEY:
        return _truncate(
            fallback_report.build_fallback_report(detections, intrusions=intrusions),
            settings.REPORT_MAX_CHARS)

    # 设置超时 + 关闭自动重试，避免慢端点被多次叠加等待导致请求长时间挂起（页面卡死）。
    # 真正耗时的云端推理由调用方放到后台线程执行，HTTP 接口立即返回。
    client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY,
                    timeout=settings.LLM_TIMEOUT, max_retries=0)
    summary = "; ".join(f'{d["label_zh"]}({d["conf"]:.2f})' for d in detections) or "未检测到目标"
    if intrusions:
        names = "、".join(d["label_zh"] for d in intrusions)
        summary += f"；【危险作业区闯入 {len(intrusions)} 起：{names}】"
    try:
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"以下是边缘端 YOLOv8 目标检测结果，请基于此生成施工安全巡检报告：\n{summary}"},
            ],
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        return _truncate(_strip_think(resp.choices[0].message.content), settings.REPORT_MAX_CHARS)
    except Exception as e:
        note = f"\n\n（云端模型调用失败或超时，已回退本地兜底：{e}）"
        return _truncate(
            fallback_report.build_fallback_report(detections, intrusions=intrusions, note=note),
            settings.REPORT_MAX_CHARS)
