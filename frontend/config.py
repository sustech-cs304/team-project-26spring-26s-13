"""
Frontend Relevant/config.py
前端配置：后端 API 地址，通过环境变量覆盖。
"""

import os

# 后端 FastAPI 服务地址，与 backend/config.py 的 HOST:PORT 对应
API_BASE_URL: str = os.environ.get("SPA_API_BASE_URL", "http://127.0.0.1:8000")
