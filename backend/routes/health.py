"""Health Check API 라우터.

서비스 상태 확인을 위한 엔드포인트들을 제공합니다.
"""

from fastapi import APIRouter

from modules import get_db_manager, get_redis_manager

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health_check():
    """전체 서비스 상태를 확인합니다.

    Returns:
        dict: 모든 서비스 연결 상태 정보
    """
    db = get_db_manager()
    redis_mgr = get_redis_manager()

    db_status = "ok"
    redis_status = "ok"

    # Check DB
    if not db.is_initialized:
        db_status = "not_initialized"
    else:
        try:
            await db.fetchval("SELECT 1")
        except Exception:
            db_status = "error"

    # Check Redis
    if not redis_mgr.is_initialized:
        redis_status = "not_initialized"
    else:
        try:
            if not await redis_mgr.ping():
                redis_status = "error"
        except Exception:
            redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return {
        "status": overall,
        "services": {
            "database": db_status,
            "redis": redis_status,
        }
    }


@router.get("/db")
async def db_health_check():
    """PostgreSQL 데이터베이스 상태를 확인합니다.

    Returns:
        dict: DB 연결 상태 정보
    """
    db = get_db_manager()
    if not db.is_initialized:
        return {"status": "error", "message": "Database not initialized"}
    try:
        result = await db.fetchval("SELECT 1")
        return {"status": "ok", "connected": result == 1}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/redis")
async def redis_health_check():
    """Redis 상태를 확인합니다.

    Returns:
        dict: Redis 연결 상태 정보
    """
    redis_mgr = get_redis_manager()
    if not redis_mgr.is_initialized:
        return {"status": "error", "message": "Redis not initialized"}
    try:
        pong = await redis_mgr.ping()
        return {"status": "ok", "connected": pong}
    except Exception as e:
        return {"status": "error", "message": str(e)}
