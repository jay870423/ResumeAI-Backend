import os
import uuid
import json
import fitz
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.parser import ParserFactory
from app.core.ocr import OCRFactory
from app.services.minimax import MiniMaxService
from app.db import database
from app.models.common import (
    ApiResponse,
    ResumeUploadResponse,
    ResumeParseResponse,
    AnalyzeResponse,
    BasicInfo,
    Score,
    Strength,
    Weakness,
    Suggestion,
    PersonaResponse,
    PersonaDimension,
    PersonaDimensions,
    KeywordsResponse,
    OptimizeResponse,
    ResumeStatusResponse,
)

router = APIRouter(prefix="/resume", tags=["简历"])

# 全局服务实例
_minimax_service: MiniMaxService = None
_parser_factory: ParserFactory = None
_ocr_factory: OCRFactory = None


def get_minimax() -> MiniMaxService:
    global _minimax_service
    if _minimax_service is None:
        _minimax_service = MiniMaxService(
            api_key=settings.minimax_api_key,
            model=settings.minimax_model,
        )
    return _minimax_service


def get_parser() -> ParserFactory:
    global _parser_factory
    if _parser_factory is None:
        _parser_factory = ParserFactory()
    return _parser_factory


def get_ocr() -> OCRFactory:
    global _ocr_factory
    if _ocr_factory is None:
        _ocr_factory = OCRFactory()
    return _ocr_factory


# ─── 辅助函数 ───────────────────────────────────────────────


def _get_page_count(file_path: str) -> int:
    """获取PDF页数"""
    try:
        doc = fitz.open(file_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 1


def _generate_resume_id() -> str:
    """生成简历ID"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"rs_{ts}_{uid}"


def _error_response(code: int, message: str):
    return ApiResponse(code=code, message=message, data=None)


# ─── API 接口 ───────────────────────────────────────────────


@router.post("/upload", response_model=ApiResponse)
async def upload_resume(file: UploadFile = File(...)):
    """上传简历文件"""
    # 校验文件大小
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        return _error_response(1002, f"文件超过大小限制({settings.max_file_size_mb}MB)")

    # 校验文件格式
    allowed = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return _error_response(1001, f"不支持的文件格式: {ext}，仅支持PDF/Word/图片")

    # 生成ID并保存文件
    resume_id = _generate_resume_id()
    file_type = ext.lstrip(".")
    save_dir = os.path.join(settings.upload_dir, "default")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, f"{resume_id}{ext}")

    try:
        with open(save_path, "wb") as f:
            f.write(content)

        # 获取页数
        page_count = _get_page_count(save_path) if ext == ".pdf" else 1

        # 保存到数据库
        await database.save_resume(
            resume_id=resume_id,
            file_name=file.filename,
            file_type=file_type,
            file_path=save_path,
            file_size=len(content),
            page_count=page_count,
        )

        return ApiResponse(
            code=0,
            message="success",
            data=ResumeUploadResponse(
                resume_id=resume_id,
                file_name=file.filename,
                file_type=file_type,
                file_size=len(content),
                page_count=page_count,
            ).model_dump(),
        )
    except Exception as e:
        return _error_response(1003, f"文件读取失败: {str(e)}")


@router.post("/parse", response_model=ApiResponse)
async def parse_resume(resume_id: str):
    """解析简历，提取文本"""
    resume = await database.get_resume(resume_id)
    if not resume:
        return _error_response(2001, "简历不存在")

    try:
        file_path = resume["file_path"]
        ext = os.path.splitext(file_path)[1].lower()

        if ext in {".png", ".jpg", ".jpeg"}:
            # 图片走OCR
            ocr = get_ocr()
            raw_text = ocr.extract_text(file_path)
        else:
            # 文档走解析器
            parser = get_parser()
            raw_text = parser.extract_text(file_path)

        if not raw_text or len(raw_text.strip()) < 10:
            return _error_response(2002, "简历内容过少或无法解析")

        word_count = len(raw_text)
        page_count = resume["page_count"] or 1

        # 更新数据库
        await database.update_resume_text(resume_id, raw_text)

        return ApiResponse(
            code=0,
            message="success",
            data=ResumeParseResponse(
                resume_id=resume_id,
                raw_text=raw_text,
                word_count=word_count,
                page_count=page_count,
            ).model_dump(),
        )
    except Exception as e:
        return _error_response(2002, f"简历解析失败: {str(e)}")


@router.post("/analyze", response_model=ApiResponse)
async def analyze_resume(resume_id: str, target_industry: str = None, keywords: list[str] = None):
    """AI分析简历"""
    resume = await database.get_resume(resume_id)
    if not resume:
        return _error_response(2001, "简历不存在")

    if not resume.get("raw_text"):
        return _error_response(2002, "简历未解析，请先调用parse接口")

    try:
        minimax = get_minimax()
        result = minimax.analyze_resume(resume["raw_text"], target_industry)

        # 保存分析结果
        await database.update_resume_analysis(
            resume_id,
            json.dumps(result, ensure_ascii=False),
            "",  # persona后续单独更新
        )

        # 构造响应
        basic = result.get("basic_info", {})
        score = result.get("score", {})
        analyzed_at = datetime.now()

        return ApiResponse(
            code=0,
            message="success",
            data={
                "resume_id": resume_id,
                "basic_info": basic,
                "score": score,
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", []),
                "optimization_suggestions": result.get("optimization_suggestions", []),
                "analyzed_at": analyzed_at.isoformat(),
            },
        )
    except Exception as e:
        return _error_response(2004, f"MiniMax API错误: {str(e)}")


@router.post("/persona", response_model=ApiResponse)
async def generate_persona(resume_id: str, target_industry: str = None):
    """生成职场人格画像"""
    resume = await database.get_resume(resume_id)
    if not resume:
        return _error_response(2001, "简历不存在")

    if not resume.get("raw_text"):
        return _error_response(2002, "简历未解析，请先调用parse接口")

    try:
        minimax = get_minimax()
        result = minimax.generate_persona(resume["raw_text"], target_industry)

        # 更新persona到数据库
        existing = await database.get_resume(resume_id)
        current_persona = json.loads(existing.get("persona_json") or "{}")
        current_persona.update(result)
        await database.update_resume_analysis(
            resume_id,
            existing.get("analysis_json", ""),
            json.dumps(current_persona, ensure_ascii=False),
        )

        dims = result.get("dimensions", {})
        generated_at = datetime.now()

        return ApiResponse(
            code=0,
            message="success",
            data={
                "resume_id": resume_id,
                "mbti_type": result.get("mbti_type", ""),
                "type_label": result.get("type_label", ""),
                "type_description": result.get("type_description", ""),
                "dimensions": {
                    "communication_style": dims.get("communication_style", {}),
                    "decision_mode": dims.get("decision_mode", {}),
                    "collaboration": dims.get("collaboration", {}),
                    "motivation": dims.get("motivation", {}),
                },
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", []),
                "ideal_environment": result.get("ideal_environment", ""),
                "career_suggestions": result.get("career_suggestions", []),
                "summary": result.get("summary", ""),
                "confidence": result.get("confidence", 0.0),
                "generated_at": generated_at.isoformat(),
            },
        )
    except Exception as e:
        return _error_response(2004, f"MiniMax API错误: {str(e)}")


@router.get("/{resume_id}", response_model=ApiResponse)
async def get_resume_status(resume_id: str):
    """获取简历状态"""
    resume = await database.get_resume(resume_id)
    if not resume:
        return _error_response(2001, "简历不存在")

    return ApiResponse(
        code=0,
        message="success",
        data=ResumeStatusResponse(
            resume_id=resume_id,
            file_name=resume["file_name"],
            status=resume["status"],
            has_optimized=bool(resume.get("optimized_text")),
            created_at=datetime.fromisoformat(resume["created_at"]),
            analyzed_at=datetime.fromisoformat(resume["analyzed_at"]) if resume.get("analyzed_at") else None,
        ).model_dump(),
    )
