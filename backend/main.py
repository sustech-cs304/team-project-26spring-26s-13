"""
backend/main.py
FastAPI 应用入口。注册所有路由，配置 CORS（允许 PyQt6 客户端跨域调用）。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import auth, user, agent, materials, dashboard, schedule

app = FastAPI(
    title="Student Productivity Agent API",
    version="0.1.0",
    description="Backend for SUSTech Student Productivity Agent",
)

# CORS：允许本地 PyQt6 客户端和浏览器调试工具访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 生产环境改为具体域名/端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(agent.router)
app.include_router(materials.router)
app.include_router(dashboard.router)
app.include_router(schedule.router)


@app.get("/health")
async def health_check() -> dict:
    """健康检查接口，PyQt6 启动时可轮询此接口确认后端就绪。"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from backend.config import settings
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
