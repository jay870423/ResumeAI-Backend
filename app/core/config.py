from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # MiniMax API
    minimax_api_key: str = "sk-cp-xxxxxxxxxxxxxxxx"
    minimax_model: str = "abab7"
    minimax_endpoint: str = "https://api.minimaxi.com/v1/text/chatcompletion_v2"

    # OCR配置
    aliyun_ocr_api_key: str = ""
    aliyun_ocr_api_secret: str = ""

    # 文件存储
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 10

    # 服务器
    host: str = "0.0.0.0"
    port: int = 8877

    # JWT 认证
    jwt_secret: str = "resume-ai-super-secret-key-change-in-production"

    # CORS
    backend_cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # 项目名
    project_name: str = "ResumeAI"
    api_v1_prefix: str = "/api/v1"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 确保上传目录存在
os.makedirs(settings.upload_dir, exist_ok=True)
