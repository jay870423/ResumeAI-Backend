import json
import io
import urllib.parse
from fastapi import APIRouter, HTTPException
from datetime import datetime
from app.db import database
from app.services.minimax import MiniMaxService
from app.core.config import settings
from app.models.common import ApiResponse

router = APIRouter(prefix="/resume", tags=["简历优化"])


def _error_response(code: int, message: str):
    return ApiResponse(code=code, message=message, data=None)


def _get_minimax():
    return MiniMaxService(api_key=settings.minimax_api_key, model=settings.minimax_model)


def _safe_filename(name: str) -> str:
    """RFC 5987 编码，防止 Content-Disposition 头编码错误"""
    encoded = urllib.parse.quote(name, safe='')
    return f"'{encoded}'"


@router.post("/optimize", response_model=ApiResponse)
async def optimize_resume(
    resume_id: str,
    optimize_type: str = "full",
):
    """AI优化简历（全部参数通过 query 传递）"""
    resume = await database.get_resume(resume_id)
    if not resume:
        return _error_response(2001, "简历不存在")

    if not resume.get("raw_text"):
        return _error_response(2002, "简历未解析，请先调用parse接口")

    try:
        minimax = _get_minimax()
        try:
            result = minimax.optimize_resume(
                resume_text=resume["raw_text"],
                target_industry=None,
                optimize_type=optimize_type,
                target_keywords=[],
            )
        except (json.JSONDecodeError, ValueError) as e:
            # JSON解析失败时，用原始简历文本+错误信息作为降级响应
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "resume_id": resume_id,
                    "optimized_text": resume["raw_text"],
                    "changes": [],
                    "summary": f"AI优化暂时不可用，请稍后再试（解析错误: {str(e)[:80]}）",
                },
            )

        optimized_text = result.get("optimized_text", "")
        await database.update_resume_optimized(resume_id, optimized_text)

        return ApiResponse(
            code=0,
            message="success",
            data={
                "resume_id": resume_id,
                "optimized_text": optimized_text,
                "changes": result.get("changes", []),
                "summary": result.get("summary", ""),
            },
        )
    except Exception as e:
        return _error_response(2004, f"MiniMax API错误: {str(e)}")


@router.post("/export", response_model=ApiResponse)
async def export_resume(
    resume_id: str,
    format: str = "pdf",
    use_optimized: bool = True,
):
    """导出简历为PDF或Word"""
    if format not in ("pdf", "docx"):
        return _error_response(3001, "导出格式不支持，仅支持PDF和Word")

    resume = await database.get_resume(resume_id)
    if not resume:
        return _error_response(2001, "简历不存在")

    try:
        if use_optimized and resume.get("optimized_text"):
            text = resume["optimized_text"]
        elif resume.get("raw_text"):
            text = resume["raw_text"]
        else:
            return _error_response(3002, "没有可导出的简历内容")

        base_name = resume["file_name"].rsplit(".", 1)[0] if resume.get("file_name") else "resume"

        if format == "pdf":
            return await _export_pdf(text, base_name)
        else:
            return await _export_docx(text, base_name)

    except Exception as e:
        return _error_response(3002, f"导出生成失败: {str(e)}")


async def _export_pdf(text: str, base_name: str):
    """导出为PDF（使用 reportlab + Noto CJK 中文字体）"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from fastapi.responses import StreamingResponse

    # 注册中文字体（wqy-microhei 为单体 TTC，兼容 ReportLab）
    try:
        pdfmetrics.registerFont(TTFont("NotoCJK", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"))
    except Exception:
        raise RuntimeError("未找到可用的中文字体")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    style = ParagraphStyle(
        "ResumeStyle",
        fontName="NotoCJK",
        fontSize=11,
        leading=20,
        spaceAfter=4,
    )

    title_style = ParagraphStyle(
        "TitleStyle",
        fontName="NotoCJK",
        fontSize=16,
        leading=24,
        spaceAfter=12,
        textColor=colors.HexColor("#1A365D"),
    )

    story = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 6))
        elif i == 0 and len(lines) < 10:
            story.append(Paragraph(line, title_style))
        else:
            story.append(Paragraph(line, style))

    doc.build(story)
    buffer.seek(0)

    output_name = f"{base_name}_optimized.pdf"
    encoded_name = urllib.parse.quote(output_name)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


async def _export_docx(text: str, base_name: str):
    """导出为Word（python-docx 原生支持中文）"""
    from docx import Document
    from docx.shared import Pt
    from docx.oxml.ns import qn
    from fastapi.responses import StreamingResponse

    doc = Document()
    lines = text.split("\n")

    for line in lines:
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.font.size = Pt(11)
        run.font.name = "宋体"
        try:
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        except Exception:
            pass
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.space_before = Pt(0)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    output_name = f"{base_name}_optimized.docx"
    encoded_name = urllib.parse.quote(output_name)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )
