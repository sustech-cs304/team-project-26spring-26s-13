"""
backend/main.py
FastAPI 应用入口。注册所有路由，配置 CORS（允许 PyQt6 客户端跨域调用）。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.api import auth, user, agent, materials, dashboard, schedule
except Exception as e:
    # If optional dependencies like pydantic_ai are missing, load only essential routers
    from backend.api import auth, user, materials, dashboard, schedule

    # Log the missing optional module for debugging
    import logging

    logging.warning(f"Optional router 'agent' not loaded due to: {e}")
from backend.database.postgres import ensure_tables_exist

app = FastAPI(
    title="Student Productivity Agent API",
    version="0.1.0",
    description="Backend for SUSTech Student Productivity Agent",
)

# CORS：允许本地 PyQt6 客户端和浏览器调试工具访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境改为具体域名/端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(materials.router)
app.include_router(dashboard.router)
app.include_router(schedule.router)
# Optional agent router, included if available
if "agent" in globals():
    app.include_router(agent.router)


@app.on_event("startup")
async def ensure_runtime_schema() -> None:
    """启动时补齐缺失的数据库表，避免新增功能依赖的表在本地缺失。"""
    await ensure_tables_exist()


@app.get("/health")
async def health_check() -> dict:
    """健康检查接口，PyQt6 启动时可轮询此接口确认后端就绪。"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from backend.config import settings

    # NOTE: Using reload=True on Windows can cause frequent restarts and transient
    # connection failures (WinError 10061) for the desktop client. Keep reload off
    # for a stable local run; developers can enable it manually when needed.
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=False)
