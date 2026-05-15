# ResumeAI Backend

简历AI分析优化平台后端API，基于FastAPI构建，提供简历解析、分析、人格画像、优化、导出等能力。

## 技术栈

- FastAPI + uvicorn
- SQLAlchemy + SQLite
- MiniMax API（AI能力）
- JWT认证
- python-docx, PyPDF2（文档解析）

## 项目结构

```
backend/
├── app/
│   ├── api/v1/     # API路由
│   ├── core/      # 核心模块（parser/ocr/config）
│   ├── db/        # 数据库
│   ├── models/    # 数据模型
│   ├── schemas/   # Pydantic模型
│   └── services/  # 业务服务
├── uploads/       # 上传文件
├── requirements.txt
├── Dockerfile
└── run.sh
```

## 快速部署

```bash
pip install -r requirements.txt
bash run.sh
```

## API文档

启动后访问：http://localhost:8877/docs

## 服务地址

- 后端：http://81.70.144.73:8877
- 前端：http://81.70.144.73:5173

## 许可证

MIT License

