"""프론트엔드 로그 수집 API 라우터.

프론트엔드에서 발생하는 로그를 수집하여 파일로 저장합니다.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/logs", tags=["logs"])

logger = logging.getLogger(__name__)

# 환경 설정
ENV = os.getenv("ENV", "development")
FRONTEND_LOG_DIR = "logs/frontend"


class FrontendLogEntry(BaseModel):
    """프론트엔드 로그 엔트리."""
    level: str  # DEBUG, INFO, WARN, ERROR
    message: str
    timestamp: str  # ISO 8601 format
    context: Optional[Dict[str, Any]] = None


class FrontendLogRequest(BaseModel):
    """프론트엔드 로그 요청."""
    logs: List[FrontendLogEntry]


@router.post("/frontend")
async def receive_frontend_logs(request: FrontendLogRequest):
    """프론트엔드 로그를 수신하여 파일로 저장합니다.

    Args:
        request: 로그 엔트리 목록

    Returns:
        dict: 처리 결과
    """
    # 개발 환경에서만 허용
    if ENV == "production":
        raise HTTPException(status_code=403, detail="Frontend logging disabled in production")

    if not request.logs:
        return {"status": "ok", "count": 0}

    # 로그 디렉토리 생성
    os.makedirs(FRONTEND_LOG_DIR, exist_ok=True)

    # 오늘 날짜의 로그 파일
    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(FRONTEND_LOG_DIR, f"frontend_{today}.log")

    # 로그 기록
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            for entry in request.logs:
                # 포맷: timestamp [LEVEL] message {context}
                context_str = ""
                if entry.context:
                    context_str = f" {json.dumps(entry.context, ensure_ascii=False)}"
                line = f"{entry.timestamp} [{entry.level.upper()}] {entry.message}{context_str}\n"
                f.write(line)

        logger.debug(f"프론트엔드 로그 수신: {len(request.logs)}개")
        return {"status": "ok", "count": len(request.logs)}
    except Exception as e:
        logger.error(f"프론트엔드 로그 저장 실패: {e}")
        raise HTTPException(status_code=500, detail="Failed to write logs")
