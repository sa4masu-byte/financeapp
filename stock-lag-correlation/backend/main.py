"""
FastAPI アプリケーションエントリポイント
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from api import router

# ログ設定
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル"""
    # 起動時
    logger.info("Starting application...")
    init_db()
    logger.info("Database initialized")

    yield

    # 終了時
    logger.info("Shutting down application...")


# FastAPIアプリケーション
app = FastAPI(
    title=settings.app_name,
    description="日本株タイムラグ相関分析システム API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切に制限
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """ヘルスチェック（詳細）"""
    return {
        "status": "healthy",
        "database": "connected",
        "cache": "active"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
