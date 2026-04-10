"""
HydroAgent 主入口 — FastAPI 服务器
启动后端 API 服务并提供独立前后端部署所需的接口能力
"""
import sys
import os
import logging
import asyncio
import schedule
import threading
import time

# 确保 src 包可被导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.logger_config import logger
from src.config import config
from src.database.models import SessionLocal, init_db
from src.api import router as api_router
from src.routers.alert_router import router as alert_router
from src.routers.analytics_router import router as analytics_router
from src.routers.asset_router import router as asset_router
from src.routers.auth_router import router as auth_router
from src.routers.knowledge_router import router as knowledge_router
from src.routers.report_router import router as report_router
from src.routers.user_router import router as user_router
from src.services import bootstrap_default_zones
from src.services.alert_service import ensure_alert_rules
from src.services.asset_service import ensure_sensor_devices
from src.services.auth_service import ensure_auth_seed
from src.services.system_settings_service import ensure_system_settings, get_collection_interval_minutes

# ============================================================
#  FastAPI 应用配置
# ============================================================

app = FastAPI(
    title="HydroAgent — 水利灌溉智能体",
    description="基于 Deep Agent + MCP 协议的水利灌溉智能决策平台",
    version="4.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS —— 允许前端开发模式下的跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(asset_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(alert_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(report_router, prefix="/api")


# ============================================================
#  生命周期事件
# ============================================================

@app.on_event("startup")
async def startup_event():
    """服务启动时：初始化数据库 + 预热 Agent"""
    logger.info("=" * 60)
    logger.info("🌊 HydroAgent v4.0.0 启动中...")
    
    # 初始化数据库（自动建表）
    try:
        init_db()
        db = SessionLocal()
        try:
            ensure_system_settings(db)
            bootstrap_default_zones(db)
            ensure_sensor_devices(db)
            ensure_auth_seed(db)
            ensure_alert_rules(db)
        finally:
            db.close()
        logger.info(f"✅ 数据库初始化完成 ({config.DB_TYPE})")
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")

    try:
        from src.llm.persistence import get_hydro_persistence

        await get_hydro_persistence().initialize()
        logger.info("✅ LangGraph SQLite persistence 已初始化")
    except Exception as e:
        logger.error(f"❌ LangGraph persistence 初始化失败: {e}")
    
    # 异步预热 Agent（非阻塞）
    async def _warmup():
        try:
            from src.llm.langchain_agent import get_hydro_agent
            agent = get_hydro_agent()
            await agent.initialize()
            logger.info("✅ HydroAgent 预热完成")
        except Exception as e:
            logger.warning(f"⚠️ HydroAgent 预热失败（将在首次请求时重试）: {e}")
    
    asyncio.create_task(_warmup())
    
    # 启动定时自动检查任务
    _start_auto_check_scheduler()
    
    logger.info(f"✅ HydroAgent 服务已启动: http://{config.APP_HOST}:{config.APP_PORT}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时：清理资源"""
    logger.info("🛑 HydroAgent 关闭中...")
    try:
        from src.llm.langchain_agent import get_hydro_agent
        agent = get_hydro_agent()
        await agent.cleanup()
    except Exception:
        pass
    try:
        from src.llm.persistence import get_hydro_persistence

        await get_hydro_persistence().close()
    except Exception:
        pass
    logger.info("👋 HydroAgent 已关闭")


# ============================================================
#  定时自动检查任务
# ============================================================

def _run_auto_check():
    """在独立线程中运行异步的自动灌溉检查"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        from src.llm.langchain_agent import get_hydro_agent
        agent = get_hydro_agent()
        
        result = loop.run_until_complete(agent.auto_check())
        logger.info(f"[AutoCheck] 完成: {result[:100]}...")
        loop.close()
    except Exception as e:
        logger.error(f"[AutoCheck] 失败: {e}")


def _start_auto_check_scheduler():
    """启动定时任务调度器（每小时检查一次）"""
    db = SessionLocal()
    try:
        interval_minutes = get_collection_interval_minutes(db)
    finally:
        db.close()
    
    def scheduler_thread():
        schedule.every(interval_minutes).minutes.do(_run_auto_check)
        logger.info(f"📅 自动灌溉检查已启动（每 {interval_minutes} 分钟）")
        while True:
            schedule.run_pending()
            time.sleep(30)
    
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()


@app.get("/")
async def index():
    from fastapi.responses import HTMLResponse
    origins = ", ".join(config.FRONTEND_ORIGINS)
    return HTMLResponse(f"""
    <html>
    <head><title>HydroAgent API</title></head>
    <body style="font-family:sans-serif;background:#0f172a;color:#e2e8f0;text-align:center;padding:50px">
        <h1>HydroAgent API</h1>
        <p>后端 API 已启动，前端请通过独立的 Next.js / Vercel 应用访问。</p>
        <p>允许的前端来源: <code>{origins}</code></p>
        <p><a href="/api/docs" style="color:#38bdf8">API 文档</a></p>
        <p><a href="/api/status" style="color:#38bdf8">系统状态</a></p>
        <p><a href="/api/health" style="color:#38bdf8">健康检查</a></p>
    </body>
    </html>
    """)


# ============================================================
#  入口
# ============================================================

def main():
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=config.APP_HOST,
        port=config.APP_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
