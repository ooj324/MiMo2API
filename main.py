"""Mimo2API Python版本 - 主程序入口"""

import os
import uvicorn
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from pathlib import Path
from app.routes import router, _do_discover
from app.config import config_manager
from app.anthropic_routes import router as anthropic_router
from app.batch import init_batch_storage as init_anthropic_batches
from app.auth import verify_admin

# 创建FastAPI应用
app = FastAPI(
    title="Mimo2API",
    description="Mimo AI 2 API",
    version="2.3.6",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_discover_models():
    import os as _anthropic_os
    from app.batch import init_batch_storage as _mimo_init_batch_storage
    _mimo_init_batch_storage(_anthropic_os.path.join(_anthropic_os.path.dirname(_anthropic_os.path.abspath(__file__)), ".anthropic_batches"))
    """服务启动时预探测模型，避免首次请求返回3个硬编码模型"""
    try:
        await _do_discover()
        print("✅ 模型预探测完成")
    except Exception as e:
        print(f"⚠️ 模型预探测失败（不影响服务）: {e}")

    # 后台清理过期会话（避免风控）
    print("[启动] 后台清理过期会话...")
    import threading
    threading.Thread(target=_cleanup_old_sessions, daemon=True).start()


def _cleanup_old_sessions():
    """后台启动时清理：从远端拉取会话列表并全部清空。"""
    import time, asyncio
    async def _run():
        try:
            from app.mimo_client import MimoClient
            from app.config import config_manager
            from app.session_store import _store, _lock
            
            for a in config_manager.config.mimo_accounts:
                client = MimoClient(a)
                # 拉取远端列表
                resp_data = await client.get_conversations(page_num=1, page_size=50)
                data_list = resp_data.get("dataList", [])
                
                conv_ids = [item.get("conversationId") for item in data_list if item.get("conversationId")]
                
                if conv_ids:
                    print(f"[Cleanup] Found {len(conv_ids)} remote sessions for account {a.user_id}, deleting...")
                    if await client.delete_conversations(conv_ids):
                        print(f"[Cleanup] Deleted {len(conv_ids)} sessions for {a.user_id}")
                        # 同步清空本地该账号缓存
                        key = f"account_{a.user_id}"
                        with _lock:
                            if key in _store:
                                del _store[key]
                    else:
                        print(f"[Cleanup] Failed to delete remote sessions for {a.user_id}")
                    # 避免风控，加点延时
                    time.sleep(2)
        except Exception as e:
            print(f"[Cleanup] Failed: {e}")
    asyncio.run(_run())


# 注册路由
app.include_router(router)
app.include_router(anthropic_router)

# 初始化 Anthropic batch 存储
import os
_anthropic_batch_dir = os.path.join(os.path.dirname(__file__), ".anthropic_batches")
init_anthropic_batches(_anthropic_batch_dir)

# 静态文件目录
web_dir = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=web_dir), name="static")

# 管理页面由 routes.py 中的 router 处理（/ 和 /admin）

@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(username: str = Depends(verify_admin)):
    return JSONResponse(get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes))

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html(username: str = Depends(verify_admin)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title + " - Swagger UI")

@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html(username: str = Depends(verify_admin)):
    return get_redoc_html(openapi_url="/openapi.json", title=app.title + " - ReDoc")

@app.get("/health", tags=["System"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok"}


def main():
    """主函数"""
    # 获取端口配置
    port = int(os.getenv("PORT", "8080"))

    print(f"""
╔══════════════════════════════════════════════════════════╗
║                    Mimo2API Python                       ║
║          将小米 Mimo AI 转换为 OpenAI 兼容 API           ║
╚══════════════════════════════════════════════════════════╝

🚀 服务器启动中...
📍 地址: http://localhost:{port}
📊 管理界面: http://localhost:{port}
📡 API端点: http://localhost:{port}/v1/chat/completions
📖 API文档: http://localhost:{port}/docs

配置信息:
  - API Keys: {len(config_manager.config.api_keys.split(','))} 个
  - Mimo账号: {len(config_manager.config.mimo_accounts)} 个

按 Ctrl+C 停止服务器
""")

    # 启动服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
